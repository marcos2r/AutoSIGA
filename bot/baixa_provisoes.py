"""
Aprovação (TES01508) e baixa (TES01506) das provisões de energia na Contas a Pagar.

O bot só executa decisões BAIXAR já tomadas por `controllers.baixa_energia`. Antes de
gravar, cada tela é conferida (número da fatura e valor); depois de gravar, o status é
relido na TES01501. Qualquer diferença interrompe aquela fatura sem gravar.
"""

import logging
import time
from urllib.parse import urljoin

from bot.descoberta_contas import _JS_LER_CONTAS_TES
from bot.extratos import MesFechadoError
from controllers.baixa_energia import (
    APROVADA_SEM_BAIXA,
    APROVADO,
    BAIXADA,
    BAIXAR,
    FALHOU,
    PAGO,
    ResultadoBaixa,
    guid_valido,
    mesmo_documento,
    provisoes_da_grade,
    valor_siga,
)
from controllers.catalogo_contas import escolher_opcao_conta
from controllers.prova_real import valor_br

FORMA_DEBITO_AUTOMATICO = "9"
HISTORICO_NF = "021"

# Linhas da grade #grid1 da TES01501, inclusive as das outras páginas do DataTable
_JS_LER_PROVISOES = '''() => {
    const $ = window.jQuery;
    const linhas = ($ && $.fn.dataTable && $.fn.dataTable.isDataTable('#grid1'))
        ? $('#grid1').DataTable().rows().nodes().toArray()
        : Array.from(document.querySelectorAll('#grid1 tbody tr'));
    return linhas.map(tr => {
        const tds = tr.querySelectorAll('td');
        if (tds.length < 12) return null;
        const ref = tr.querySelector('a[data-codigo]');
        const link = Array.from(tr.querySelectorAll('a')).find(a => /codigo=/i.test(a.getAttribute('href') || ''));
        let guid = ref ? ref.getAttribute('data-codigo') : '';
        if (!guid && link) guid = (link.getAttribute('href').split('codigo=')[1] || '').split('&')[0];
        return {vencimento: tds[2].innerText.trim(), numero: tds[4].innerText.trim(),
                fornecedor: tds[5].innerText.trim(), valor: tds[8].innerText.trim(),
                status: tds[11].innerText.trim(), guid: guid};
    }).filter(Boolean);
}'''

# Filtro por vencimento na TES01501 e envio do formulário (o botão pode estar num modal fechado)
_JS_FILTRAR_VENCIMENTO = '''([inicio, fim]) => {
    const tipo = document.getElementById('f_tipodata');
    if (tipo) {
        const opt = Array.from(tipo.options).find(o => /vcto|venc/i.test(o.text));
        if (opt) tipo.value = opt.value;
    }
    for (const [id, valor] of [['f_data1', inicio], ['f_data2', fim]]) {
        const campo = document.getElementById(id);
        if (campo) { campo.value = valor; if (window.jQuery) window.jQuery(campo).trigger('change'); }
    }
    const botao = document.querySelector('form#f_main button[type="submit"]');
    if (!botao) return false;
    botao.click();
    return true;
}'''

# Cabeçalho da TES01508/TES01506, para conferir a fatura antes de gravar
_JS_LER_CABECALHO = '''() => ({
    documento: (document.getElementById('f_documento') || {}).value || '',
    valor: (document.getElementById('f_valor') || {}).value || '',
    apagar: (document.getElementById('f_valorapagar') || {}).value || ''
})'''

_JS_PREENCHER_DATA = '''(data) => {
    const campo = document.getElementById('f_datapagamento');
    if (!campo) return false;
    campo.value = data;
    if (window.jQuery) window.jQuery(campo).trigger('input').trigger('change').trigger('blur');
    return true;
}'''

_JS_MODAL_PAGAMENTO_ABERTO = '''() => {
    const m = document.getElementById('modal-formapagamento');
    return !!(m && m.classList.contains('in'));
}'''

_JS_ESCOLHER = '''([id, valor]) => {
    const campo = document.getElementById(id);
    if (!campo || !Array.from(campo.options).some(o => o.value === valor)) return false;
    window.jQuery('#' + id).val(valor).trigger('change');
    return true;
}'''

_JS_QTD_CONTAS = "() => document.querySelectorAll('select#f_conta option').length"

# Valor do histórico cujo rótulo começa pelo código ("021 - NF")
_JS_VALOR_HISTORICO = '''(codigo) => {
    const opt = Array.from(document.querySelectorAll('select#f_historicobaixa option'))
        .find(o => o.textContent.trim().startsWith(codigo + ' '));
    return opt ? opt.value : null;
}'''

# Pagamentos que o "Inserir" pôs na grade (a linha #row-vazia é o aviso de grade vazia)
_JS_LER_PAGAMENTOS = '''() => ({
    linhas: Array.from(document.querySelectorAll('#t_pagamentos tbody tr'))
        .filter(tr => tr.id !== 'row-vazia')
        .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())),
    restante: (document.getElementById('f_valorrestante') || {}).value || ''
})'''

_SUBMIT_FORMULARIO = 'form#f_main button[type="submit"].btn-success'
_ESPERA_CONTAS_S = 10


class BaixaNaoConferidaError(Exception):
    """A tela do SIGA não mostra o que se esperava; a fatura fica sem gravar."""


class BaixaProvisoesMixin:
    """Lê, aprova e baixa provisões de energia, conferindo cada passo."""

    def _ler_provisoes_energisa(self, page, periodo):
        """Provisões da Energisa com vencimento no período, lidas da TES01501.

        Args:
            page: Página do Playwright.
            periodo: (início, fim) do vencimento, "dd/mm/aaaa".

        Returns:
            list[ProvisaoSiga]: Todas as situações (Lançado, Aprovado, Pago).
        """
        self.update_status("Lendo as faturas de energia na Contas a Pagar...", "#428BCA")
        self._executar_programa(page, "TES01501")
        if page.evaluate(_JS_FILTRAR_VENCIMENTO, list(periodo)):
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            self.esperar_loading(page)
        return provisoes_da_grade(page.evaluate(_JS_LER_PROVISOES))

    def _executar_baixas(self, page, decisoes, conta_codigo, periodo):
        """Aprova (se preciso) e baixa cada decisão BAIXAR e confere o status no fim.

        Mês fechado interrompe tudo (propaga `MesFechadoError`); outro problema só
        interrompe a fatura em que aconteceu.

        Args:
            page: Página do Playwright.
            decisoes: Decisões de `decidir_baixas`; só as BAIXAR são executadas.
            conta_codigo: Código da conta do extrato (ex.: "10123"), onde a baixa cai.
            periodo: Período de vencimento para reler a TES01501.

        Returns:
            list[ResultadoBaixa]: Um por decisão BAIXAR.
        """
        resultados = []
        for decisao in [d for d in decisoes if d.acao == BAIXAR]:
            if not self.browser_aberto:
                break
            aprovou = False
            try:
                if decisao.precisa_aprovar:
                    self._aprovar_provisao(page, decisao.provisao)
                    aprovou = True
                self._baixar_provisao(page, decisao.provisao, decisao.debito.data, decisao.debito.valor,
                                      conta_codigo)
                resultados.append(ResultadoBaixa(decisao, BAIXADA))
            except MesFechadoError:
                raise
            except Exception as e:
                logging.error(f"Baixa da fatura {decisao.provisao.numero} interrompida: {e}", exc_info=True)
                self._capturar_tela_e_log(page, f"baixa_{decisao.provisao.numero}")
                resultados.append(ResultadoBaixa(decisao, APROVADA_SEM_BAIXA if aprovou else FALHOU, str(e)))
        return self._conferir_status(page, resultados, periodo) if resultados else resultados

    def _aprovar_provisao(self, page, provisao):
        """Aprova a provisão na TES01508, depois de conferir número e valor na tela."""
        self.update_status(f"Aprovando a fatura {provisao.numero}...", "#428BCA")
        self._abrir_parcela(page, "TES01508", provisao)
        page.locator(_SUBMIT_FORMULARIO).first.click()
        self._depois_de_gravar(page)

    def _baixar_provisao(self, page, provisao, data, valor, conta_codigo):
        """Baixa a provisão na TES01506: débito automático, na conta do extrato, histórico 021.

        Só clica em Confirmar se a grade de pagamentos tiver exatamente um pagamento
        do valor do débito e nada restar a pagar.
        """
        self.update_status(f"Baixando a fatura {provisao.numero} ({valor_siga(valor)})...", "#428BCA")
        tela = self._abrir_parcela(page, "TES01506", provisao)
        if valor_br(tela.get("apagar")) != round(valor, 2):
            raise BaixaNaoConferidaError(f"valor a pagar na tela é {tela.get('apagar')}")
        if not page.evaluate(_JS_PREENCHER_DATA, data):
            raise BaixaNaoConferidaError("campo da data de pagamento não encontrado")

        page.locator('#btn-novo-pagamento').click()
        time.sleep(1)
        if not page.evaluate(_JS_MODAL_PAGAMENTO_ABERTO):
            raise BaixaNaoConferidaError("o modal Novo Pagamento não abriu")
        self._escolher(page, "f_codigoFormaPgto", FORMA_DEBITO_AUTOMATICO, "forma de pagamento")
        self._esperar_contas(page)
        conta = escolher_opcao_conta(page.evaluate(_JS_LER_CONTAS_TES) or [], conta_codigo)
        if not conta:
            raise BaixaNaoConferidaError(f"conta {conta_codigo} não aparece na baixa")
        self._escolher(page, "f_conta", conta, "conta")
        historico = page.evaluate(_JS_VALOR_HISTORICO, HISTORICO_NF)
        if not historico:
            raise BaixaNaoConferidaError(f"histórico {HISTORICO_NF} não encontrado")
        self._escolher(page, "f_historicobaixa", historico, "histórico")
        self._preencher_campos(page, {"f_valorpagamento": valor_siga(valor)})
        page.locator('#btn-confirmar').click()
        time.sleep(1)

        pagamentos = page.evaluate(_JS_LER_PAGAMENTOS) or {}
        linhas = pagamentos.get("linhas") or []
        if len(linhas) != 1 or not any(valor_br(c) == round(valor, 2) for c in linhas[0]):
            raise BaixaNaoConferidaError(f"grade de pagamentos inesperada: {linhas}")
        if valor_br(pagamentos.get("restante")) != 0:
            raise BaixaNaoConferidaError(f"ainda restam {pagamentos.get('restante')} a pagar")

        page.locator(_SUBMIT_FORMULARIO).first.click()
        self._depois_de_gravar(page)

    def _conferir_status(self, page, resultados, periodo):
        """Relê a TES01501 e rebaixa para FALHOU o que não ficou Pago (ou Aprovado)."""
        status = {p.guid: p.status for p in self._ler_provisoes_energisa(page, periodo)}
        conferidos = []
        for r in resultados:
            atual = status.get(r.decisao.provisao.guid, "?")
            if r.situacao == BAIXADA and atual != PAGO:
                r = ResultadoBaixa(r.decisao, FALHOU, f"gravada, mas a fatura está {atual} no SIGA")
            elif r.situacao == APROVADA_SEM_BAIXA and atual != APROVADO:
                r = ResultadoBaixa(r.decisao, FALHOU, f"{r.detalhe}; status no SIGA: {atual}")
            conferidos.append(r)
        return conferidos

    def _executar_programa(self, page, codigo):
        campo = page.locator('#f_executar_programa')
        campo.fill(codigo)
        page.locator('#btn_executar_programa').click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)
        self.esperar_loading(page)

    def _abrir_parcela(self, page, programa, provisao):
        """Abre a tela da parcela e confere o número da fatura e o valor.

        Returns:
            dict: Cabeçalho lido (documento, valor, apagar).
        """
        if not guid_valido(provisao.guid):
            raise BaixaNaoConferidaError(f"código de parcela inválido: {provisao.guid!r}")
        page.goto(urljoin(page.url, f"/TES/{programa}.aspx?codigo={provisao.guid}"))
        page.wait_for_load_state("domcontentloaded")
        self.esperar_loading(page)
        tela = page.evaluate(_JS_LER_CABECALHO) or {}
        if not mesmo_documento(tela.get("documento", ""), provisao.numero):
            raise BaixaNaoConferidaError(f"{programa} abriu o documento {tela.get('documento')!r}")
        if valor_br(tela.get("valor")) != round(provisao.valor, 2):
            raise BaixaNaoConferidaError(f"{programa} mostra o valor {tela.get('valor')!r}")
        return tela

    def _escolher(self, page, campo, valor, nome):
        if not page.evaluate(_JS_ESCOLHER, [campo, valor]):
            raise BaixaNaoConferidaError(f"{nome} {valor} não disponível")
        time.sleep(0.5)

    def _esperar_contas(self, page):
        """As contas da baixa só carregam depois de escolher a forma de pagamento."""
        for _ in range(_ESPERA_CONTAS_S * 2):
            if (page.evaluate(_JS_QTD_CONTAS) or 0) > 1:
                return
            time.sleep(0.5)
        raise BaixaNaoConferidaError("as contas de pagamento não carregaram")

    def _depois_de_gravar(self, page):
        """Trata o aviso de mês fechado e fecha o "Informações armazenadas com sucesso"."""
        time.sleep(1)
        if self._mes_fechado_na_tela(page):
            raise MesFechadoError("baixa")
        self._confirmar_gravacao(page, 15000)
        if self._mes_fechado_na_tela(page):
            raise MesFechadoError("baixa")
