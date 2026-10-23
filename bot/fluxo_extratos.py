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
from controllers.exportador import Exportador
from controllers.prova_real import (
    CONCILIADO,
    CONFERE,
    CONTA_NAO_ENCONTRADA,
    DIVERGE,
    MES_FECHADO,
    PENDENTE,
    RECUSADO,
    ResultadoExtrato,
    conferir_saldo,
    movimentos_do_banco,
    nao_conferido,
    sobras_no_siga,
    valor_br,
)

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

# Saldo final da conta no período: coluna Saldo da linha "Total" do rodapé da grade
_JS_LER_SALDO = '''() => {
    const celulas = document.querySelectorAll('#grid1 tfoot tr:first-child th, #grid1 tfoot tr:first-child td');
    return celulas.length > 7 ? celulas[7].innerText.trim() : null;
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
        is_aplicacao = dados.get("tipo_extrato") == "APLICACAO"
        conta_alvo = dados.get("conta_siga_aplicacao" if is_aplicacao else "conta_siga_corrente", "")
        qtd = len(dados.get("transacoes", []))
        if self._pular_competencia_fechada(chave_competencia, telemetria_lote, idx):
            self._registrar_resultado(telemetria_lote, dados, conta_alvo, MES_FECHADO, pendentes=qtd,
                                      saldo=nao_conferido("mês fechado no SIGA", dados.get("saldo_atual")))
            return False

        # Só troca de localidade e competência se for diferente do extrato anterior
        if localidade_atual != contexto["localidade"] or mes_ano_alvo != contexto["competencia"]:
            if not self._ajustar_localidade_competencia(page, self.tipo_alvo, self.nome_alvo, mes_ano_alvo):
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
        baixas, fechado = self._etapa_baixas_energia(page, dados, conta_alvo)
        if fechado:
            self.competencias_fechadas.add(chave_competencia)
            telemetria_lote["pendentes"] += qtd
            self._registrar_resultado(telemetria_lote, dados, conta_alvo, MES_FECHADO, pendentes=qtd,
                                      saldo=nao_conferido("mês fechado no SIGA", dados.get("saldo_atual")),
                                      baixas=baixas)
            return True

        extrato_siga = self._abrir_consulta_tes01701(page, conta_alvo, dados.get("data_inicial", ""), data_final)
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

        pendentes, grade_atual, recusado = [], True, False
        injecoes_antes = telemetria_lote["injecoes"]
        if novos_lancamentos and not self._pedir_autorizacao(novos_lancamentos, conta_alvo):
            pendentes, recusado = novos_lancamentos, True
            telemetria_lote["pendentes"] += len(pendentes)
            self.update_status(f"⏭️ [{self.localidade_selecionada}] Lançamentos não autorizados: "
                               f"{len(pendentes)} item(ns) ficaram pendentes.", "#F89406")
        elif novos_lancamentos:
            consulta = (conta_alvo, dados.get("data_inicial", ""), data_final)
            pendentes, grade_atual = self._lancar_com_conferencia(page, novos_lancamentos, is_aplicacao,
                                                                  chave_competencia, telemetria_lote, consulta)
            if pendentes:
                telemetria_lote["pendentes"] += len(pendentes)
                if chave_competencia not in self.competencias_fechadas:
                    self.update_status(f"⚠️ [{self.localidade_selecionada}] Alerta: {len(pendentes)} itens não "
                                       f"bateram após {_LIMITE_TENTATIVAS} tentativas.", "#D9534F")
        else:
            self.update_status(f"✅ [{self.localidade_selecionada}] Tudo conciliado! Nenhum lançamento novo faltando.", "#3C763D")

        if chave_competencia in self.competencias_fechadas:
            situacao, saldo, sobras = MES_FECHADO, nao_conferido("mês fechado no SIGA", dados.get("saldo_atual")), None
        else:
            situacao = RECUSADO if recusado else (PENDENTE if pendentes else CONCILIADO)
            saldo, sobras = self._prova_real(page, dados, grade_atual)
        self._registrar_resultado(telemetria_lote, dados, conta_alvo, situacao,
                                  telemetria_lote["injecoes"] - injecoes_antes, len(pendentes), saldo, sobras, baixas)
        return True

    def _pedir_autorizacao(self, pendentes, conta_siga, tipo="lancamentos"):
        """Com a prévia ligada, mostra os lançamentos (ou as baixas) e espera a resposta do usuário.

        A espera é em fatias de 1 s para terminar como recusa se o navegador for fechado.

        Args:
            pendentes: Itens da prévia ({"data", "valor", "historico"/"descricao"}).
            conta_siga: Conta do extrato, mostrada no topo da prévia.
            tipo: "lancamentos" (prévia `revisar_antes_de_lancar`) ou "baixas" (`revisar_baixas`).

        Returns:
            bool: True para gravar; False se o usuário recusou ou o navegador foi fechado.
        """
        revisar = self.revisar_baixas if tipo == "baixas" else self.revisar_antes_de_lancar
        if not revisar or "request_authorization" not in self.callbacks:
            return True
        self._autorizado = False
        self._evento_autorizacao.clear()
        rotulo = "baixa(s) de energia" if tipo == "baixas" else "lançamento(s)"
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

    def _prova_real(self, page, dados, grade_atual):
        """Confere o saldo final da grade com o do banco e procura lançamentos sem par.

        Só lê a grade que já está na tela; nunca lança nem corrige nada.

        Returns:
            tuple: (ResultadoSaldo, sobras ou None quando não dá para apontá-las).
        """
        saldo_banco = dados.get("saldo_atual")
        if dados.get("periodo_filtrado"):
            return nao_conferido("período filtrado à mão", saldo_banco), None
        if not grade_atual:
            return nao_conferido("a grade do SIGA não foi relida depois dos lançamentos", saldo_banco), None
        data_saldo = dados.get("data_saldo")
        if saldo_banco is not None and data_saldo and data_saldo != dados.get("data_final"):
            return nao_conferido(f"o saldo do extrato é de {data_saldo}", saldo_banco), None

        try:
            texto = page.evaluate(_JS_LER_SALDO)
        except Exception as e:
            logging.warning(f"Saldo da TES01701 ilegível: {e}")
            texto = None
        saldo = conferir_saldo(saldo_banco, valor_br(texto) if texto is not None else None)

        movimentos = movimentos_do_banco(dados)
        sobras = sobras_no_siga(movimentos, dados.get("extrato_siga")) if movimentos is not None else None

        if saldo.status == CONFERE:
            self.update_status(f"🧾 Prova real: saldo confere ({Exportador.formatar_moeda(saldo.saldo_siga)}).", "#3C763D")
        elif saldo.status == DIVERGE:
            extra = f" · {len(sobras)} lançamento(s) no SIGA sem par no extrato" if sobras else ""
            self.update_status(f"⚠️ Prova real: SIGA {Exportador.formatar_moeda(saldo.saldo_siga)} × banco "
                               f"{Exportador.formatar_moeda(saldo.saldo_banco)} (diferença "
                               f"{Exportador.formatar_moeda(saldo.diferenca)}){extra}.", "#F89406")
        return saldo, sobras

    def _registrar_resultado(self, telemetria_lote, dados, conta_siga, situacao, lancados=0, pendentes=0,
                             saldo=None, sobras=None, baixas=None):
        """Guarda o resultado do extrato em `telemetria_lote["extratos"]` para o painel e o Excel."""
        resultado = ResultadoExtrato(
            conta_id=str(dados.get("conta_id", "")), conta_siga=conta_siga or "",
            localidade=dados.get("localidade_selecionada", ""), tipo=dados.get("tipo_extrato", ""),
            situacao=situacao, lancados=lancados, pendentes=pendentes, sobras=sobras, baixas=baixas)
        if saldo is not None:
            resultado.saldo = saldo
        telemetria_lote.setdefault("extratos", []).append(resultado)

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

    def _lancar_com_conferencia(self, page, pendentes, is_aplicacao, chave_competencia, telemetria_lote, consulta):
        """Lança os pendentes e relê a grade até tudo bater, em até 3 tentativas.

        A releitura refaz o filtro (conta e período do extrato): depois de gravar, a TES01701 volta
        com o filtro padrão (mês atual), e reaproveitá-lo fazia um extrato de outro mês parecer não
        lançado. Se a releitura não acha nenhum dos itens gravados, o bot não tenta de novo: lançar
        outra vez duplicaria tudo o que já foi gravado.

        Args:
            consulta: (conta, data inicial, data final) do extrato, para refazer o filtro.

        Returns:
            tuple: (transações que continuaram sem par no SIGA, True se a grade na tela
            é a relida depois do último lançamento).
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
                return pendentes, False

            telemetria_lote["injecoes"] += self._qtd_injecoes_efetuadas

            self.update_status("Realizando conferência pós-lançamento...", "#428BCA")
            time.sleep(2.5)
            try:
                extrato_recente = self._abrir_consulta_tes01701(page, *consulta)
                if extrato_recente is None:
                    raise RuntimeError(f"conta {consulta[0]} não encontrada no filtro")
                self.dados_processados["extrato_siga"] = extrato_recente
                restantes = Conciliador.conciliar(self.dados_processados.get("transacoes", []), extrato_recente)
                if not restantes:
                    self.update_status(f"✅ [{self.localidade_selecionada}] Conferência 100%: Nenhum item para trás!", "#3C763D")
                    return [], True
                if self._qtd_injecoes_efetuadas and len(restantes) >= len(pendentes):
                    logging.error(f"Conferência não achou nenhum dos {self._qtd_injecoes_efetuadas} lançamento(s) "
                                  "gravado(s); re-tentativa cancelada para não duplicar.")
                    self.update_status(f"⛔ [{self.localidade_selecionada}] A conferência não encontrou os "
                                       f"{self._qtd_injecoes_efetuadas} lançamento(s) gravado(s). Confira no SIGA "
                                       "antes de rodar de novo: o robô não lançou outra vez.", "#D9534F")
                    return restantes, True
                pendentes = restantes
            except Exception as e:
                logging.error(f"Erro na conferência final: {e}")
                self.update_status(f"✅ [{self.localidade_selecionada}] Finalizado sem prova real.", "#3C763D")
                return pendentes, False
        return pendentes, True
