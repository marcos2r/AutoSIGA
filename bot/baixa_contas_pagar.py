"""
Baixa das outras provisões da Contas a Pagar (boletos e PIX) pagas no extrato.

O bot só executa as decisões BAIXAR de `controllers.baixa_contas_pagar`. Cada parcela
Lançado é aprovada na TES01508 (a mesma rotina da energia), porque a baixa em lote só
aceita Aprovado. Depois todas as parcelas do pagamento são baixadas juntas pela Baixa em
Lote Agrupada (TES01519), aberta pelo menu Manutenções da TES01501, que serve também para
uma parcela só. Antes de Confirmar, a tela é conferida (parcelas, total e data); depois, a
data gravada em cada parcela e o status relido na TES01501.
"""

import logging
import re
import time

from bot.baixa_provisoes import _JS_AVISOS_ABERTOS, _JS_LER_DATA, BaixaNaoConferidaError
from bot.descoberta_contas import _JS_LER_CONTAS_TES
from bot.extratos import MesFechadoError
from controllers.baixa_contas_pagar import (
    APROVADA_SEM_BAIXA,
    BAIXADA,
    BAIXAR,
    BOLETO,
    FALHOU,
    PIX,
    ResultadoPagamento,
    decidir_pagamentos,
    ler_pagamentos,
    motivo_aprovacao,
    parcelas_da_grade,
    periodo_de_vencimento,
    resultados_sem_execucao,
    resumo_decisao,
)
from controllers.baixa_energia import APROVADO, PAGO, valor_siga
from controllers.catalogo_contas import escolher_opcao_conta
from controllers.prova_real import valor_br

# Formas da TES01519: 8 Pgto. Eletrônico para boleto, 14 PIX; histórico 021 - NF, como nas baixas manuais
FORMAS = {BOLETO: "8", PIX: "14"}
HISTORICO_NF = "021"
_ESPERA_LOTE_S = 15

# A seleção da grade fica em `listaSelecionados` (GUIDs); o clique em Manutenções › Baixar em
# Lote Agrupado valida a lista no servidor e abre a TES01519 com ela, como as caixas marcadas fariam
_JS_ABRIR_LOTE = '''(guids) => {
    const botao = document.getElementById('baixar_agrupado');
    if (!botao) return false;
    window.listaSelecionados = guids;
    botao.click();
    return true;
}'''

_JS_LOTE_ABERTO = "() => !!document.querySelector('.modal.in #f_formapagamento')"

_JS_LER_LOTE = '''() => {
    const m = document.querySelector('.modal.in');
    if (!m) return null;
    return {guids: Array.from(m.querySelectorAll('input[name="f_codigo"]')).map(e => e.value.toUpperCase()),
            total: (m.querySelector('input[name="f_total"]') || {}).value || ''};
}'''

# Valor do histórico cujo rótulo começa pelo código ("021 - NF")
_JS_VALOR_HISTORICO = '''(codigo) => {
    const opt = Array.from(document.querySelectorAll('.modal.in select#f_historico option'))
        .find(o => o.textContent.trim().startsWith(codigo + ' '));
    return opt ? opt.value : null;
}'''

# Na TES01519 o Select2 abre a lista quando recebe foco (o Tab depois da data cai na forma de
# pagamento), e a máscara dele cobre o Confirmar. Devolve verdadeiro se nenhuma lista ficou aberta.
_JS_FECHAR_SELECT2 = '''() => {
    if (window.jQuery) {
        jQuery('.modal.in select').each(function () { try { jQuery(this).select2('close'); } catch (e) {} });
    }
    const mask = document.getElementById('select2-drop-mask');
    return !(mask && getComputedStyle(mask).display !== 'none');
}'''

# Na TES01519 o campo da data deixa em branco algumas datas digitadas em campo vazio (05/10 e
# 20/10 somem; 26/10 fica), sem aviso. Pôr o valor e disparar o change roda a mesma validação
# do SIGA (Siga.UTIL.ValidaData), e a data gravada é conferida depois em cada parcela.
_JS_DEFINIR_DATA = '''(data) => {
    const campo = document.querySelector('.modal.in #f_datapagamento');
    if (!campo || !window.jQuery) return false;
    jQuery(campo).val(data).trigger('change');
    try { jQuery(campo).datepicker('hide'); } catch (e) {}
    return true;
}'''

_SUBMIT_LOTE = '.modal.in form button[type="submit"].btn-success'


class BaixaContasPagarMixin:
    """Lê a Contas a Pagar, decide e baixa os boletos e PIX pagos no extrato."""

    def _etapa_baixas_contas_pagar(self, page, dados, conta_codigo):
        """Baixa as provisões pagas por boleto ou PIX num extrato de conta corrente, antes da conciliação.

        Usa a mesma opção da baixa de energia ("baixar o que o extrato pagou").

        Returns:
            tuple: (list[ResultadoPagamento] ou None se não há boleto nem PIX ou a opção está
            desligada, True se o SIGA avisou mês fechado).
        """
        if not self.baixar_energia or dados.get("tipo_extrato") == "APLICACAO":
            return None, False
        pagamentos = ler_pagamentos(dados.get("transacoes", []))
        if not pagamentos:
            return None, False
        periodo = periodo_de_vencimento(dados.get("data_inicial", ""), dados.get("data_final", ""))
        if periodo is None:
            logging.warning("Extrato sem período: baixas de boletos e PIX não verificadas.")
            return None, False
        try:
            self.update_status("Lendo os boletos e PIX na Contas a Pagar...", "#428BCA")
            parcelas = parcelas_da_grade(self._ler_contas_a_pagar(page, periodo))
        except Exception as erro:  # só leitura: sem a grade não se baixa nada, mas a conciliação segue
            logging.exception("Falha ao ler a Contas a Pagar para os boletos e PIX.")
            self._capturar_tela_e_log(page, "erro_ler_contas_a_pagar")
            self.update_status(f"⚠️ Baixas de boletos e PIX puladas: não consegui ler a Contas a Pagar ({erro}).",
                               "#F89406")
            return None, False

        decisoes = decidir_pagamentos(pagamentos, parcelas)
        a_baixar = [d for d in decisoes if d.acao == BAIXAR]
        if not a_baixar:
            return resultados_sem_execucao(decisoes), False
        previa = [{"data": d.pagamento.data, "valor": -d.pagamento.valor, "historico": resumo_decisao(d)[1][2:]}
                  for d in a_baixar]
        if not self._pedir_autorizacao(previa, conta_codigo, tipo="baixas_cp"):
            self.update_status(f"⏭️ Baixas de boletos e PIX não autorizadas: {len(a_baixar)} pendente(s).",
                               "#F89406")
            return resultados_sem_execucao(decisoes), False

        executados, mes_fechado = self._executar_baixas_cp(page, a_baixar, conta_codigo, periodo)
        por_decisao = {id(r.decisao): r for r in executados}
        motivo = "mês fechado no SIGA" if mes_fechado else "navegador fechado"
        resultados = [por_decisao.get(id(d)) or ResultadoPagamento(d, FALHOU if d.acao == BAIXAR else d.acao,
                                                                       motivo if d.acao == BAIXAR else d.motivo)
                      for d in decisoes]
        baixadas = sum(1 for r in resultados if r.situacao == BAIXADA)
        self.update_status(f"💳 {baixadas} de {len(a_baixar)} boleto(s)/PIX baixado(s) na Contas a Pagar.",
                           "#3C763D" if baixadas == len(a_baixar) else "#F89406")
        return resultados, mes_fechado

    def _executar_baixas_cp(self, page, decisoes, conta_codigo, periodo):
        """Aprova o que está Lançado e baixa cada pagamento em lote; confere o status no fim.

        Mês fechado interrompe os pagamentos seguintes; outro problema só o pagamento em que aconteceu.

        Returns:
            tuple: (list[ResultadoPagamento] executados, True se o SIGA avisou mês fechado).
        """
        resultados, mes_fechado = [], False
        for decisao in decisoes:
            if not self.browser_aberto:
                break
            aprovou = False
            try:
                for parcela in decisao.a_aprovar:
                    self._aprovar_provisao(page, parcela, motivo_aprovacao(decisao, conta_codigo))
                    aprovou = True
                self._baixar_em_lote(page, decisao, conta_codigo)
                resultados.append(ResultadoPagamento(decisao, BAIXADA))
            except MesFechadoError:
                resultados.append(ResultadoPagamento(decisao, APROVADA_SEM_BAIXA if aprovou else FALHOU,
                                                     "mês fechado no SIGA"))
                mes_fechado = True
                break
            except Exception as e:
                numeros = ", ".join(p.numero for p in decisao.parcelas)
                logging.error(f"Baixa da provisão {numeros} interrompida: {e}", exc_info=True)
                self._capturar_tela_e_log(page, f"baixa_cp_{decisao.parcelas[0].numero}")
                self._fechar_modais(page)
                resultados.append(ResultadoPagamento(decisao, APROVADA_SEM_BAIXA if aprovou else FALHOU, str(e)))
        if resultados:
            try:
                resultados = self._conferir_status_cp(page, resultados, periodo)
            except Exception as e:  # só leitura: o resultado fica como gravado, mas o lote segue
                logging.error(f"Não consegui reler o status dos boletos e PIX na TES01501: {e}", exc_info=True)
                self._capturar_tela_e_log(page, "erro_conferir_baixas_cp")
                resultados = [ResultadoPagamento(r.decisao, r.situacao,
                                                 "; ".join(filter(None, [r.detalhe, "status não relido no SIGA"])))
                              for r in resultados]
        return resultados, mes_fechado

    def _baixar_em_lote(self, page, decisao, conta_codigo):
        """Baixa as parcelas do pagamento na TES01519: data do extrato, forma, conta e histórico 021.

        Só clica em Confirmar se a tela trouxer exatamente as parcelas da decisão, o total
        do pagamento e a data do extrato.
        """
        pg = decisao.pagamento
        guids = [p.guid.upper() for p in decisao.parcelas]
        numeros = ", ".join(p.numero for p in decisao.parcelas)
        self.update_status(f"Baixando a provisão {numeros} ({valor_siga(pg.valor)})...", "#428BCA")
        self._executar_programa(page, "TES01501")
        if not page.evaluate(_JS_ABRIR_LOTE, guids):
            raise BaixaNaoConferidaError("o menu Baixar em Lote Agrupado não está na Contas a Pagar")
        if not self._esperar_condicao(page, _JS_LOTE_ABERTO, _ESPERA_LOTE_S):
            avisos = page.evaluate(_JS_AVISOS_ABERTOS) or []
            raise BaixaNaoConferidaError(f"a baixa em lote não abriu{': ' + avisos[0] if avisos else ''}")
        self._conferir_lote(page, guids, pg.valor)

        self._preencher_data_lote(page, pg.data)
        self._escolher(page, "f_formapagamento", FORMAS[pg.tipo], "forma de pagamento")
        self._esperar_contas(page)
        conta = escolher_opcao_conta(page.evaluate(_JS_LER_CONTAS_TES) or [], conta_codigo)
        if not conta:
            raise BaixaNaoConferidaError(f"conta {conta_codigo} não aparece na baixa")
        self._escolher(page, "f_conta", conta, "conta")
        historico = page.evaluate(_JS_VALOR_HISTORICO, HISTORICO_NF)
        if not historico:
            raise BaixaNaoConferidaError(f"histórico {HISTORICO_NF} não encontrado")
        self._escolher(page, "f_historico", historico, "histórico")
        # O Documento é obrigatório e só aceita dígitos: vai o número da nota, como nas baixas manuais
        documento = re.sub(r"\D", "", decisao.parcelas[0].numero)[:20] or pg.documento[:20]
        self._preencher_campos(page, {"f_documento": documento})

        self._conferir_lote(page, guids, pg.valor)
        data_na_tela = page.evaluate(_JS_LER_DATA)
        if data_na_tela != pg.data:
            raise BaixaNaoConferidaError(f"a data de pagamento na tela é {data_na_tela!r}, não {pg.data}")
        if not page.evaluate(_JS_FECHAR_SELECT2):
            raise BaixaNaoConferidaError("uma lista da baixa em lote ficou aberta sobre o Confirmar")
        page.locator(_SUBMIT_LOTE).first.click()
        self._depois_de_gravar(page)
        for parcela in decisao.parcelas:
            self._conferir_data_gravada(page, parcela, pg.data, parcela.valor)

    def _preencher_data_lote(self, page, data):
        """Digita a data de pagamento; se a TES01519 deixar o campo vazio, põe o valor pelo jQuery."""
        try:
            self._digitar_data(page, data)
            return
        except BaixaNaoConferidaError:
            if page.evaluate(_JS_AVISOS_ABERTOS) or page.evaluate(_JS_LER_DATA):
                raise  # aviso do SIGA ou outra data na tela: não é o campo que ficou vazio
        if not page.evaluate(_JS_DEFINIR_DATA, data):
            raise BaixaNaoConferidaError("campo da data de pagamento não encontrado")
        time.sleep(1)  # a validação do SIGA roda no change
        avisos = page.evaluate(_JS_AVISOS_ABERTOS) or []
        if avisos:
            raise BaixaNaoConferidaError(f"o SIGA avisou: {avisos[0]}")
        if page.evaluate(_JS_LER_DATA) != data:
            raise BaixaNaoConferidaError(f"a data de pagamento ficou {page.evaluate(_JS_LER_DATA)!r}, não {data}")

    @staticmethod
    def _conferir_lote(page, guids, valor):
        """A TES01519 abriu com as parcelas da decisão, e o total é o valor pago no extrato."""
        tela = page.evaluate(_JS_LER_LOTE) or {}
        if sorted(tela.get("guids") or []) != sorted(guids):
            raise BaixaNaoConferidaError(f"a baixa em lote abriu {len(tela.get('guids') or [])} parcela(s), "
                                         f"não as {len(guids)} do pagamento")
        if valor_br(tela.get("total")) != round(valor, 2):
            raise BaixaNaoConferidaError(f"o total da baixa em lote é {tela.get('total')!r}, não {valor_siga(valor)}")

    def _conferir_status_cp(self, page, resultados, periodo):
        """Relê a TES01501 e rebaixa para FALHOU o pagamento cujas parcelas não ficaram Pago (ou Aprovado)."""
        status = {p.guid.upper(): p.status for p in parcelas_da_grade(self._ler_contas_a_pagar(page, periodo))}
        conferidos = []
        for r in resultados:
            atuais = {status.get(p.guid.upper(), "?") for p in r.decisao.parcelas}
            if r.situacao == BAIXADA and atuais != {PAGO}:
                r = ResultadoPagamento(r.decisao, FALHOU, f"gravada, mas a provisão está {', '.join(sorted(atuais))}")
            elif r.situacao == APROVADA_SEM_BAIXA and not atuais <= {APROVADO}:
                r = ResultadoPagamento(r.decisao, FALHOU, f"{r.detalhe}; status no SIGA: {', '.join(sorted(atuais))}")
            conferidos.append(r)
        return conferidos
