"""
Laço de conciliação de extratos: para cada extrato do lote, consulta a conta na
Caixas e Bancos (TES01701), cruza a grade com o banco e lança o que falta.

A grade é lida uma vez no começo do extrato e conferida uma vez no final; entre as duas,
as gravações são decididas pela matriz em memória (`bot/conferencia_extrato.py`).
"""

import logging
import time

from bot.conferencia_extrato import _LIMITE_TENTATIVAS
from bot.descoberta_contas import _JS_LER_CONTAS_TES
from bot.extratos import MesFechadoError
from controllers.avisos_extrato import avisos_do_extrato
from controllers.catalogo_contas import escolher_opcao_conta
from controllers.conciliador import Conciliador, fora_do_periodo
from controllers.prova_real import (
    CONCILIADO,
    CONTA_NAO_ENCONTRADA,
    MES_FECHADO,
    PENDENTE,
    RECUSADO,
    ResultadoExtrato,
    duplicidades,
    nao_conferido,
)

# Lê a grade #grid1 da TES01701 (Data, Lançto, Documento, Histórico, Origem, Entrada, Saída, Saldo)
_JS_LER_GRADE = '''() => {
    const $ = window.jQuery, grade = document.querySelector('#grid1');
    let linhas = [];
    try {
        if ($ && grade && $.fn.dataTable && $(grade).hasClass('dataTable'))
            linhas = Array.from($(grade).dataTable().fnGetNodes());
    } catch (e) { linhas = []; }
    if (!linhas.length) linhas = Array.from(document.querySelectorAll('#grid1 tbody tr'));
    return linhas.map(tr => {
        const tds = tr.querySelectorAll('td');
        if (tds.length < 8) return null;
        return {data: tds[0].innerText.trim(), lote: tds[1].innerText.trim(),
                documento: tds[2].innerText.trim(), historico: tds[3].innerText.trim(),
                origem: tds[4].innerText.trim(), entrada: tds[5].innerText.trim(),
                saida: tds[6].innerText.trim(), saldo: tds[7].innerText.trim()};
    }).filter(Boolean);
}'''

# Saldo final da conta no período: coluna Saldo da linha "Total" do rodapé da grade
_JS_LER_SALDO = '''() => {
    const celulas = document.querySelectorAll('#grid1 tfoot tr:first-child th, #grid1 tfoot tr:first-child td');
    return celulas.length > 7 ? celulas[7].innerText.trim() : null;
}'''

# Período do filtro da TES01701. Os campos têm máscara e calendário: `fill` pode não ficar,
# por isso o valor vai por JS (como na TES01704) e volta lido para conferência.
_JS_PREENCHER_PERIODO = '''([inicio, fim]) => {
    for (const [id, valor] of [['f_data1', inicio], ['f_data2', fim]]) {
        const campo = document.getElementById(id);
        if (!campo || !valor) continue;
        campo.value = valor;
        if (window.jQuery) {
            try { window.jQuery(campo).datepicker('update', valor); } catch (e) { /* sem calendário */ }
            window.jQuery(campo).trigger('change');
        }
    }
    if (window.jQuery) window.jQuery('.datepicker').hide();
    return [(document.getElementById('f_data1') || {}).value || '', (document.getElementById('f_data2') || {}).value || ''];
}'''

# Abertura da rotina e do filtro: espera a condição real e, se ela não vier, a pausa antiga
_JS_MARCAR_PAGINA = "() => { window.__autosiga_pagina_anterior = true; }"
_JS_TES01701_ABERTA = ("() => !window.__autosiga_pagina_anterior && document.readyState !== 'loading'"
                       " && /TES01701/i.test(location.pathname) && !!document.querySelector('#btn-filtro')")
_JS_FILTRO_ABERTO = ("() => !!document.querySelector('#modal-filtro.in')"
                     " && document.querySelectorAll('#f_conta option').length > 1")


class PeriodoNaoAplicadoError(Exception):
    """A grade da TES01701 não é do período do extrato: comparar com ela duplicaria lançamentos."""


class FluxoExtratosMixin:
    """Conciliação OFX/XLS × SIGA, um extrato por vez, agrupando as trocas de localidade."""

    def _fluxo_extratos(self, page, telemetria_lote):
        """Processa todos os extratos do lote e mostra o status final."""
        contexto = {"localidade": None, "competencia": None}
        cronometro = self._reiniciar_cronometro()
        self._preparar_transferencias()
        self._preparar_remessas()

        # As provisões de energia esperam o e-mail só quando o primeiro débito de energia precisa delas
        provisionado = False
        for idx, dados in enumerate(self.lote_processados):
            if not self.browser_aberto:
                break
            self._verificar_sessao_ativa(page)
            if not provisionado and self._precisa_das_provisoes(dados):
                with self._medir("Provisões de energia"):
                    self._provisionar_energia(page, telemetria_lote)
                provisionado = True
            with self._medir("Extrato inteiro"):
                processado = self._processar_extrato(page, dados, idx, telemetria_lote, contexto)
            if processado:
                self._atualizar_progresso(idx)

        # Regime de competência: provisiona o período mesmo sem nenhum débito de energia no lote
        if not provisionado and self.browser_aberto:
            with self._medir("Provisões de energia"):
                self._provisionar_energia(page, telemetria_lote)

        cronometro.registrar_no_log()
        telemetria_lote["tempos"] = cronometro.resumo()
        qtd_duplicidades = sum(len(r.duplicidades) for r in telemetria_lote.get("extratos", []))
        if qtd_duplicidades:
            self.update_status(f"🗑️ {qtd_duplicidades} provável(is) lançamento(s) em duplicidade no SIGA: veja "
                               "\"Excluir no SIGA\" no painel e no Excel e exclua lá, se confirmar.", "#D9534F")

        if self.competencias_fechadas:
            fechadas = ", ".join(f"{loc} {mes}" for loc, mes in sorted(self.competencias_fechadas))
            self.update_status(f"⚠️ Lote processado. Meses fechados ou indisponíveis no SIGA: {fechadas}.", "#D9534F")
        else:
            self.update_status("✅ Todos os extratos do lote foram processados!", "#3C763D")

    def _atualizar_progresso(self, idx):
        if "update_progress" in self.callbacks:
            self.callbacks["update_progress"]((idx + 1) / len(self.lote_processados))

    def _processar_extrato(self, page, dados, idx, telemetria_lote, contexto):
        """Concilia um extrato de ponta a ponta.

        Args:
            page: Página do Playwright.
            dados: Extrato mapeado (transações, contas do SIGA, localidade, período).
            idx: Posição do extrato no lote.
            telemetria_lote: Contadores do lote, atualizados aqui.
            contexto: Localidade e competência ativas no SIGA, para evitar trocas repetidas.

        Returns:
            bool: True se o extrato foi consultado no SIGA; False se foi pulado.
        """
        self.dados_processados = dados
        dados["baixas_cp"] = None  # de uma execução anterior do mesmo lote, não vale mais
        self.localidade_selecionada = dados["localidade_selecionada"]
        self.tipo_alvo = dados["tipo_adm"]
        self.nome_alvo = dados["nome_adm"]

        # Soma o valor absoluto de cada transação do extrato no volume financeiro
        for tx in dados.get("transacoes", []):
            telemetria_lote["volume_financeiro"] += abs(tx.get("valor", 0.0))

        self.update_status(f"[{idx+1}/{len(self.lote_processados)}] Processando {self.localidade_selecionada}...", "#428BCA")

        data_final = dados.get("data_final", "")
        mes_ano_alvo = data_final[3:] if len(data_final) >= 10 else ""
        localidade_atual = f"{self.tipo_alvo}-{self.nome_alvo}"
        chave_competencia = (f"{self.tipo_alvo} - {self.nome_alvo}".upper(), mes_ano_alvo)
        is_aplicacao = dados.get("tipo_extrato") == "APLICACAO"
        conta_alvo = dados.get("conta_siga_aplicacao" if is_aplicacao else "conta_siga_corrente", "")
        qtd = len(dados.get("transacoes", []))
        if self._pular_competencia_fechada(chave_competencia, telemetria_lote, idx):
            self._registrar_resultado(telemetria_lote, dados, conta_alvo, MES_FECHADO, pendentes=qtd,
                                      saldo=nao_conferido("mês fechado no SIGA", dados.get("saldo_atual")))
            return False

        # Só troca de localidade e competência se for diferente do extrato anterior
        if localidade_atual != contexto["localidade"] or mes_ano_alvo != contexto["competencia"]:
            with self._medir("Troca de localidade e mês"):
                trocou = self._ajustar_localidade_competencia(page, self.tipo_alvo, self.nome_alvo, mes_ano_alvo)
            if not trocou:
                # Não lança nada num mês/localidade diferente do extrato
                self.competencias_fechadas.add(chave_competencia)
                telemetria_lote["pendentes"] += qtd
                self._registrar_resultado(telemetria_lote, dados, conta_alvo, MES_FECHADO, pendentes=qtd,
                                          saldo=nao_conferido("localidade ou mês indisponível no SIGA",
                                                              dados.get("saldo_atual")))
                contexto["localidade"] = contexto["competencia"] = None
                self._atualizar_progresso(idx)
                return False
            contexto["localidade"], contexto["competencia"] = localidade_atual, mes_ano_alvo

        sufixo = f" ({mes_ano_alvo})" if mes_ano_alvo else ""
        self.update_status(f"✅ Logado em: {self.localidade_selecionada}{sufixo}", "#3C763D")

        # Faturas de energia debitadas: baixadas antes, para a conciliação já encontrar a saída no SIGA
        with self._medir("Baixas de energia"):
            baixas, fechado = self._etapa_baixas_energia(page, dados, conta_alvo)
        # Boletos e PIX com provisão na Contas a Pagar, pelo mesmo motivo
        if not fechado:
            with self._medir("Baixas de boletos e PIX"):
                dados["baixas_cp"], fechado = self._etapa_baixas_contas_pagar(page, dados, conta_alvo)
        if fechado:
            self.competencias_fechadas.add(chave_competencia)
            telemetria_lote["pendentes"] += qtd
            self._registrar_resultado(telemetria_lote, dados, conta_alvo, MES_FECHADO, pendentes=qtd,
                                      saldo=nao_conferido("mês fechado no SIGA", dados.get("saldo_atual")),
                                      baixas=baixas)
            return True

        try:
            extrato_siga = self._abrir_consulta_tes01701(page, conta_alvo, dados.get("data_inicial", ""), data_final)
        except PeriodoNaoAplicadoError as erro:
            logging.error(f"Período do extrato não aplicado na TES01701: {erro}")
            self._capturar_tela_e_log(page, "periodo_nao_aplicado")
            telemetria_lote["pendentes"] += qtd
            self._registrar_resultado(telemetria_lote, dados, conta_alvo, PENDENTE, pendentes=qtd,
                                      saldo=nao_conferido("período não aplicado no SIGA", dados.get("saldo_atual")),
                                      baixas=baixas)
            self.update_status(f"⛔ [{self.localidade_selecionada}] O SIGA não mostrou o período do extrato "
                               f"({erro}). Nada foi lançado ({qtd} itens pendentes).", "#D9534F")
            self._atualizar_progresso(idx)
            return False
        if extrato_siga is None:
            # Sem a conta certa no filtro, consultar ou lançar cairia na conta que já estava selecionada
            telemetria_lote["pendentes"] += qtd
            self._registrar_resultado(telemetria_lote, dados, conta_alvo, CONTA_NAO_ENCONTRADA, pendentes=qtd,
                                      saldo=nao_conferido("conta não encontrada no SIGA", dados.get("saldo_atual")),
                                      baixas=baixas)
            self.update_status(f"⛔ Conta {conta_alvo or '(vazia)'} não encontrada em {self.localidade_selecionada}: "
                               f"extrato não lançado ({qtd} itens pendentes).", "#D9534F")
            self._atualizar_progresso(idx)
            return False
        dados["extrato_siga"] = extrato_siga
        telemetria_lote["siga_itens"] += len(extrato_siga)

        self.update_status(f"Cruzando {len(extrato_siga)} itens do SIGA com o OFX...", "#428BCA")
        novos_lancamentos = Conciliador.conciliar(dados.get("transacoes", []), extrato_siga)

        # Daqui até a conferência final as etapas decidem pela matriz em memória (dados["extrato_siga"])
        pendentes, recusado, fechado = [], False, False
        injecoes_antes = telemetria_lote["injecoes"]
        consulta = (conta_alvo, dados.get("data_inicial", ""), data_final)
        if novos_lancamentos and not self._pedir_autorizacao(novos_lancamentos, conta_alvo):
            pendentes, recusado = novos_lancamentos, True
            self.update_status(f"⏭️ [{self.localidade_selecionada}] Lançamentos não autorizados: "
                               f"{len(pendentes)} item(ns) ficaram pendentes.", "#F89406")
        elif novos_lancamentos:
            pendentes = novos_lancamentos
            self.update_status(f"🚀 Importando automaticamente {len(pendentes)} lançamentos em "
                               f"{self.localidade_selecionada}...", "#428BCA")
            try:
                self._gravar_investimentos(page, pendentes, is_aplicacao, telemetria_lote, dados)
            except MesFechadoError:
                # Não adianta tentar de novo: os outros extratos desta localidade e mês são pulados
                fechado = True
                self.competencias_fechadas.add(chave_competencia)
                self.update_status(f"⛔ [{self.localidade_selecionada}] Mês {mes_ano_alvo} fechado no SIGA. "
                                   f"{len(pendentes)} lançamento(s) ficaram pendentes.", "#D9534F")
        else:
            self.update_status(f"✅ [{self.localidade_selecionada}] Tudo conciliado! Nenhum lançamento novo faltando.", "#3C763D")

        saldo = sobras = faltas = None
        if fechado:
            situacao, saldo = MES_FECHADO, nao_conferido("mês fechado no SIGA", dados.get("saldo_atual"))
        else:
            tentou = bool(novos_lancamentos) and not recusado
            # Conta corrente: recebimentos de outras administrações, transferências e tarifas
            extras = (not is_aplicacao and
                      self._etapas_conta_corrente(page, dados, conta_alvo, chave_competencia, telemetria_lote))
            pendentes, grade_atual, fechado = self._conferencia_final(
                page, dados, consulta, pendentes, tentou, tentou or extras, is_aplicacao, chave_competencia,
                telemetria_lote)
            if fechado:
                situacao, saldo = MES_FECHADO, nao_conferido("mês fechado no SIGA", dados.get("saldo_atual"))
            else:
                situacao = RECUSADO if recusado else (PENDENTE if pendentes else CONCILIADO)
                if pendentes and not recusado:
                    self.update_status(f"⚠️ [{self.localidade_selecionada}] Alerta: {len(pendentes)} itens não "
                                       f"bateram após {_LIMITE_TENTATIVAS} tentativas.", "#D9534F")
                saldo, sobras, faltas = self._prova_real(dados, grade_atual)
        telemetria_lote["pendentes"] += len(pendentes)
        self._registrar_resultado(telemetria_lote, dados, conta_alvo, situacao,
                                  telemetria_lote["injecoes"] - injecoes_antes, len(pendentes), saldo, sobras, baixas,
                                  faltas)
        return True

    def _pedir_autorizacao(self, pendentes, conta_siga, tipo="lancamentos"):
        """Com a prévia ligada, mostra os lançamentos (ou as baixas) e espera a resposta do usuário.

        A espera é em fatias de 1 s para terminar como recusa se o navegador for fechado.

        Args:
            pendentes: Itens da prévia ({"data", "valor", "historico"/"descricao"}).
            conta_siga: Conta do extrato, mostrada no topo da prévia.
            tipo: "lancamentos", "baixas" ou "provisoes" de energia, ou "baixas_cp" de boletos e PIX
                (todas pela `revisar_antes_de_gravar`).

        Returns:
            bool: True para gravar; False se o usuário recusou ou o navegador foi fechado.
        """
        if not self.revisar_antes_de_gravar or "request_authorization" not in self.callbacks:
            return True
        self._autorizado = False
        self._evento_autorizacao.clear()
        rotulo = {"baixas": "baixa(s) de energia", "provisoes": "provisão(ões) de energia",
                  "baixas_cp": "baixa(s) de boletos e PIX"}.get(tipo, "lançamento(s)")
        self.update_status(f"⏸️ Aguardando sua revisão de {len(pendentes)} {rotulo}...", "#F89406")
        self.callbacks["request_authorization"](list(pendentes), {"conta": conta_siga, "tipo": tipo,
                                                                  "localidade": self.localidade_selecionada})
        while not self._evento_autorizacao.wait(1):
            if not self.browser_aberto:
                return False
        return self._autorizado

    def responder_autorizacao(self, autorizado):
        """Resposta da prévia vinda da UI: libera o bot para lançar ou pular o extrato."""
        self._autorizado = bool(autorizado)
        self._evento_autorizacao.set()

    def _registrar_resultado(self, telemetria_lote, dados, conta_siga, situacao, lancados=0, pendentes=0,
                             saldo=None, sobras=None, baixas=None, faltas=None):
        """Guarda o resultado do extrato em `telemetria_lote["extratos"]` para o painel e o Excel."""
        resultado = ResultadoExtrato(
            conta_id=str(dados.get("conta_id", "")), conta_siga=conta_siga or "",
            localidade=dados.get("localidade_selecionada", ""), tipo=dados.get("tipo_extrato", ""),
            situacao=situacao, lancados=lancados, pendentes=pendentes, sobras=sobras, baixas=baixas, faltas=faltas,
            periodo=_periodo(dados), baixas_cp=dados.get("baixas_cp"), avisos=avisos_do_extrato(dados, faltas) + self.avisos_transferencias(conta_siga or ""),
            duplicidades=duplicidades(sobras, dados.get("extrato_siga")) if sobras else [])
        if saldo is not None:
            resultado.saldo = saldo
        telemetria_lote.setdefault("extratos", []).append(resultado)

    def _abrir_consulta_tes01701(self, page, conta_alvo, data_in, data_fim):
        """Abre a TES01701, filtra a conta e o período e devolve as linhas da grade.

        O saldo final do rodapé é lido junto e fica em `_saldo_tes01701` para a prova real
        (a tela pode sair da TES01701 antes dela).

        Returns:
            list | None: Linhas da grade, ou None se a conta não está na lista da localidade.

        Raises:
            PeriodoNaoAplicadoError: O filtro não ficou com o período do extrato ou a grade
                traz linhas de fora dele.
        """
        self._saldo_tes01701 = None
        with self._medir("Consulta da TES01701"):
            linhas = self._consultar_tes01701(page, conta_alvo, data_in, data_fim)
        if linhas is not None:
            self._saldo_tes01701 = self._ler_saldo_tes01701(page)
        return linhas

    def _ler_saldo_tes01701(self, page):
        """Texto do saldo final da grade na tela, ou None se ilegível."""
        try:
            return page.evaluate(_JS_LER_SALDO)
        except Exception as e:
            logging.warning(f"Saldo da TES01701 ilegível: {e}")
            return None

    def _esperar_ou_pausar(self, page, condicao, pausa, timeout_ms=8000):
        """Espera a condição da tela; se ela não vier no prazo, cai na pausa fixa de antes.

        Args:
            condicao: Função JS que devolve verdadeiro quando a tela está pronta.
            pausa: Segundos da pausa antiga, usada só quando a condição falha.
        """
        try:
            page.wait_for_function(condicao, timeout=timeout_ms)
        except Exception as e:
            logging.warning(f"Condição da tela não veio em {timeout_ms} ms; pausa de {pausa} s: {e}")
            time.sleep(pausa)

    def _consultar_tes01701(self, page, conta_alvo, data_in, data_fim):
        """Passo a passo da consulta (ver `_abrir_consulta_tes01701`)."""
        self.update_status("Acessando rotina TES01701...", "#428BCA")
        # Logo depois da troca de localidade o blockUI ainda cobre a tela; o clique forçado
        # caía no overlay, a rotina não abria e o lote parava sem achar o #btn-filtro.
        self.esperar_loading(page)
        input_programa = page.locator('#f_executar_programa')
        input_programa.wait_for(state="visible", timeout=10000)
        input_programa.fill("TES01701")
        time.sleep(0.5)

        page.evaluate("document.querySelectorAll('.notificacao').forEach(e => e.remove());")
        # Marca a página atual: a espera só termina quando a TES01701 nova carregar, não na antiga
        page.evaluate(_JS_MARCAR_PAGINA)
        page.locator('#btn_executar_programa').click(force=True)
        page.wait_for_load_state("domcontentloaded")
        self._esperar_ou_pausar(page, _JS_TES01701_ABERTA, pausa=2)
        self.esperar_loading(page)
        self.fechar_modais_erro_siga(page)

        self.update_status("Abrindo menu do Extrato...", "#428BCA")
        btn_extrato = page.locator('#btn-filtro')
        btn_extrato.wait_for(state="visible", timeout=10000)
        btn_extrato.click()
        self._esperar_ou_pausar(page, _JS_FILTRO_ABERTO, pausa=1.5)

        if not self._selecionar_conta(page, conta_alvo):
            return None

        if data_in or data_fim:
            aplicado = page.evaluate(_JS_PREENCHER_PERIODO, [data_in, data_fim]) or ["", ""]
            if (data_in and aplicado[0] != data_in) or (data_fim and aplicado[1] != data_fim):
                raise PeriodoNaoAplicadoError(f"filtro ficou {aplicado[0]} a {aplicado[1]}")
        time.sleep(0.5)

        self.update_status("Consultando movimentações no banco...", "#F89406")
        page.locator('#f_main button[type="submit"].btn-success').click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(1.5)
        # O Consultar da TES01701 pode levar mais de 3s; espera o loading e o DataTable terminarem.
        self.esperar_loading(page)
        self._esperar_grade_pronta(page)
        self.fechar_modais_erro_siga(page)

        self.update_status("Lendo dados da tabela do SIGA...", "#428BCA")
        page.locator('#grid1').wait_for(state="visible", timeout=10000)
        linhas = self._ler_grade_tes01701(page)
        fora = fora_do_periodo(linhas, data_in, data_fim)
        if fora:
            raise PeriodoNaoAplicadoError(f"a grade traz {len(fora)} linha(s) fora de {data_in} a {data_fim} "
                                          f"(ex.: {fora[0]})")
        return linhas

    def _selecionar_conta(self, page, codigo):
        """Seleciona no filtro a conta ativa de código exatamente igual ao do card.

        Returns:
            bool: False se a conta não está na lista da localidade (nada é selecionado).
        """
        valor = escolher_opcao_conta(page.evaluate(_JS_LER_CONTAS_TES) or [], codigo)
        if not valor:
            return False
        page.evaluate('v => $("#f_conta").val(v).trigger("change")', valor)
        return True

    def _esperar_grade_pronta(self, page, timeout_ms=15000):
        """Aguarda o modal de filtro fechar e o DataTables da TES01701 terminar de desenhar."""
        try:
            page.wait_for_function(
                "() => { const m = document.querySelector('#modal-filtro.in'); if (m) return false;"
                " const $ = window.jQuery, g = document.querySelector('#grid1');"
                " if ($ && g && $.fn.dataTable && $(g).hasClass('dataTable'))"
                " return !$(g).dataTable().fnSettings().bDrawing;"
                " return true; }",
                timeout=timeout_ms)
        except Exception as e:
            logging.debug(f"[TES01701] Espera da grade encerrada: {e}")

    def _ler_grade_tes01701(self, page):
        """Linhas da grade de movimentos da TES01701 como dicionários de texto."""
        return page.evaluate(_JS_LER_GRADE)


def _periodo(dados):
    """Período do extrato ("01/10/2026 a 23/10/2026"), ou vazio se faltar alguma data."""
    inicio, fim = dados.get("data_inicial"), dados.get("data_final")
    return f"{inicio} a {fim}" if inicio and fim else ""
