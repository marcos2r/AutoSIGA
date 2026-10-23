"""
Laço de conciliação de extratos: para cada extrato do lote, consulta a conta na
Caixas e Bancos (TES01701), cruza a grade com o banco e lança o que falta.
"""

import logging
import time

from bot.descoberta_contas import _JS_LER_CONTAS_TES
from bot.extratos import MesFechadoError
from controllers.catalogo_contas import escolher_opcao_conta
from controllers.conciliador import Conciliador

# Lê a grade #grid1 da TES01701 (Data, Lançto, Documento, Histórico, Origem, Entrada, Saída, Saldo)
_JS_LER_GRADE = '''() => {
    let r = [];
    for (let tr of document.querySelectorAll('#grid1 tbody tr')) {
        let tds = tr.querySelectorAll('td');
        if (tds.length >= 8) {
            r.push({
                data: tds[0].innerText.trim(), lote: tds[1].innerText.trim(),
                documento: tds[2].innerText.trim(), historico: tds[3].innerText.trim(),
                origem: tds[4].innerText.trim(), entrada: tds[5].innerText.trim(),
                saida: tds[6].innerText.trim(), saldo: tds[7].innerText.trim()
            });
        }
    }
    return r;
}'''

_LIMITE_TENTATIVAS = 3


class FluxoExtratosMixin:
    """Conciliação OFX/XLS × SIGA, um extrato por vez, agrupando as trocas de localidade."""

    def _fluxo_extratos(self, page, telemetria_lote):
        """Processa todos os extratos do lote e mostra o status final."""
        contexto = {"localidade": None, "competencia": None}

        for idx, dados in enumerate(self.lote_processados):
            if not self.browser_aberto:
                break
            self._verificar_sessao_ativa(page)
            if self._processar_extrato(page, dados, idx, telemetria_lote, contexto):
                self._atualizar_progresso(idx)
                time.sleep(2)

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
        if self._pular_competencia_fechada(chave_competencia, telemetria_lote, idx):
            return False

        # Só troca de localidade e competência se for diferente do extrato anterior
        if localidade_atual != contexto["localidade"] or mes_ano_alvo != contexto["competencia"]:
            if not self._ajustar_localidade_competencia(page, self.tipo_alvo, self.nome_alvo, mes_ano_alvo):
                # Não lança nada num mês/localidade diferente do extrato
                self.competencias_fechadas.add(chave_competencia)
                telemetria_lote["pendentes"] += len(dados.get("transacoes", []))
                contexto["localidade"] = contexto["competencia"] = None
                self._atualizar_progresso(idx)
                return False
            contexto["localidade"], contexto["competencia"] = localidade_atual, mes_ano_alvo

        sufixo = f" ({mes_ano_alvo})" if mes_ano_alvo else ""
        self.update_status(f"✅ Logado em: {self.localidade_selecionada}{sufixo}", "#3C763D")

        is_aplicacao = dados.get("tipo_extrato") == "APLICACAO"
        conta_alvo = dados.get("conta_siga_aplicacao" if is_aplicacao else "conta_siga_corrente", "")
        extrato_siga = self._abrir_consulta_tes01701(page, conta_alvo, dados.get("data_inicial", ""), data_final)
        if extrato_siga is None:
            # Sem a conta certa no filtro, consultar ou lançar cairia na conta que já estava selecionada
            qtd = len(dados.get("transacoes", []))
            telemetria_lote["pendentes"] += qtd
            self.update_status(f"⛔ Conta {conta_alvo or '(vazia)'} não encontrada em {self.localidade_selecionada}: "
                               f"extrato não lançado ({qtd} itens pendentes).", "#D9534F")
            self._atualizar_progresso(idx)
            return False
        dados["extrato_siga"] = extrato_siga
        telemetria_lote["siga_itens"] += len(extrato_siga)

        self.update_status(f"Cruzando {len(extrato_siga)} itens do SIGA com o OFX...", "#428BCA")
        novos_lancamentos = Conciliador.conciliar(dados.get("transacoes", []), extrato_siga)

        if novos_lancamentos:
            pendentes = self._lancar_com_conferencia(page, novos_lancamentos, is_aplicacao,
                                                     chave_competencia, telemetria_lote)
            if pendentes:
                telemetria_lote["pendentes"] += len(pendentes)
                if chave_competencia not in self.competencias_fechadas:
                    self.update_status(f"⚠️ [{self.localidade_selecionada}] Alerta: {len(pendentes)} itens não "
                                       f"bateram após {_LIMITE_TENTATIVAS} tentativas.", "#D9534F")
        else:
            self.update_status(f"✅ [{self.localidade_selecionada}] Tudo conciliado! Nenhum lançamento novo faltando.", "#3C763D")
        return True

    def _abrir_consulta_tes01701(self, page, conta_alvo, data_in, data_fim):
        """Abre a TES01701, filtra a conta e o período e devolve as linhas da grade.

        Returns:
            list | None: Linhas da grade, ou None se a conta não está na lista da localidade.
        """
        self.update_status("Acessando rotina TES01701...", "#428BCA")
        input_programa = page.locator('#f_executar_programa')
        input_programa.wait_for(state="visible", timeout=10000)
        input_programa.fill("TES01701")
        time.sleep(0.5)

        page.evaluate("document.querySelectorAll('.notificacao').forEach(e => e.remove());")
        page.locator('#btn_executar_programa').click(force=True)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)

        self.update_status("Abrindo menu do Extrato...", "#428BCA")
        btn_extrato = page.locator('#btn-filtro')
        btn_extrato.wait_for(state="visible", timeout=10000)
        btn_extrato.click()
        time.sleep(1.5)

        if not self._selecionar_conta(page, conta_alvo):
            return None

        if data_in:
            page.locator('#f_data1').fill(data_in)
        if data_fim:
            page.locator('#f_data2').fill(data_fim)
        time.sleep(0.5)

        self.update_status("Consultando movimentações no banco...", "#F89406")
        page.locator('#f_main button[type="submit"].btn-success').click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        self.update_status("Lendo dados da tabela do SIGA...", "#428BCA")
        page.locator('#grid1').wait_for(state="visible", timeout=10000)
        return self._ler_grade_tes01701(page)

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

    def _ler_grade_tes01701(self, page):
        """Linhas da grade de movimentos da TES01701 como dicionários de texto."""
        return page.evaluate(_JS_LER_GRADE)

    def _lancar_com_conferencia(self, page, pendentes, is_aplicacao, chave_competencia, telemetria_lote):
        """Lança os pendentes e relê a grade até tudo bater, em até 3 tentativas.

        Returns:
            list: Transações que continuaram sem par no SIGA.
        """
        for tentativa in range(1, _LIMITE_TENTATIVAS + 1):
            if tentativa > 1:
                self.update_status(f"🔄 Re-tentativa {tentativa}/{_LIMITE_TENTATIVAS}: Injetando "
                                   f"{len(pendentes)} lançamentos restantes...", "#F89406")
            else:
                self.update_status(f"🚀 Importando automaticamente {len(pendentes)} lançamentos em "
                                   f"{self.localidade_selecionada}...", "#428BCA")

            self._qtd_injecoes_efetuadas = 0
            try:
                if is_aplicacao:
                    self.inserir_rendimentos_siga(page, pendentes)
                else:
                    self.inserir_lancamentos_siga(page, pendentes)
            except MesFechadoError:
                # Não adianta tentar de novo: os outros extratos desta localidade e mês são pulados
                self.competencias_fechadas.add(chave_competencia)
                self.update_status(f"⛔ [{self.localidade_selecionada}] Mês {chave_competencia[1]} fechado no SIGA. "
                                   f"{len(pendentes)} lançamento(s) ficaram pendentes.", "#D9534F")
                return pendentes

            telemetria_lote["injecoes"] += self._qtd_injecoes_efetuadas

            self.update_status("Realizando conferência pós-lançamento...", "#428BCA")
            time.sleep(2.5)
            try:
                if page.locator('#btn-filtro').is_visible():
                    page.locator('#btn-filtro').click()
                    time.sleep(1)
                page.locator('#modal-filtro form#f_main button.btn-success').first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(4)

                extrato_recente = self._ler_grade_tes01701(page)
                self.dados_processados["extrato_siga"] = extrato_recente
                pendentes = Conciliador.conciliar(self.dados_processados.get("transacoes", []), extrato_recente)
                if not pendentes:
                    self.update_status(f"✅ [{self.localidade_selecionada}] Conferência 100%: Nenhum item para trás!", "#3C763D")
                    return []
            except Exception as e:
                logging.error(f"Erro na conferência final: {e}")
                self.update_status(f"✅ [{self.localidade_selecionada}] Finalizado sem prova real.", "#3C763D")
                return pendentes
        return pendentes
