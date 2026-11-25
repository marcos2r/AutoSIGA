"""
Gravações de um extrato decididas pela matriz em memória e a conferência única no final.

A grade da TES01701 é lida no começo do extrato (`fluxo_extratos`). Daqui em diante cada
gravação entra na matriz `dados["extrato_siga"]` como linha projetada
(`controllers/matriz_extrato.py`) e as etapas seguintes (recebimentos, transferências,
tarifas) decidem por ela, sem reconsultar o SIGA entre uma e outra. No fim, uma releitura
real substitui a matriz e roda a prova real; só ela pode pedir uma nova tentativa dos
lançamentos que faltaram. Antes eram de 2 a 7 consultas por extrato; agora são até 2.
"""

import logging

from bot.extratos import MesFechadoError
from controllers.conciliador import Conciliador
from controllers.exportador import Exportador
from controllers.matriz_extrato import projetar
from controllers.prova_real import (
    CONFERE,
    DIVERGE,
    conferir_saldo,
    movimentos_do_banco,
    nao_conferido,
    parear,
    valor_br,
)
from controllers.transferencias_internas import a_lancar as a_lancar_transferencias

_LIMITE_TENTATIVAS = 3


class ConferenciaExtratoMixin:
    """Lança sem reler a grade a cada etapa e confere o extrato uma vez, no final."""

    def _gravar_investimentos(self, page, pendentes, is_aplicacao, telemetria_lote, dados):
        """Grava aplicações e resgates (ou rendimentos) e projeta na matriz o que o SIGA confirmou.

        Só projeta quando todos foram gravados: numa falha no meio não dá para saber quais
        entraram, e quem decide a nova tentativa é a releitura do final.

        Returns:
            int: Quantos o SIGA confirmou.

        Raises:
            MesFechadoError: O SIGA recusou a data (mês fechado).
        """
        self._qtd_injecoes_efetuadas = 0
        with self._medir("Lançamentos de aplicação, resgate e rendimento"):
            if is_aplicacao:
                self.inserir_rendimentos_siga(page, pendentes)
            else:
                self.inserir_lancamentos_siga(page, pendentes)
        gravados = self._qtd_injecoes_efetuadas
        telemetria_lote["injecoes"] += gravados
        if gravados and gravados == len(pendentes):
            dados["extrato_siga"] = projetar(dados.get("extrato_siga"),
                                             [(t.get("data", ""), t.get("valor", 0.0), t.get("descricao", ""))
                                              for t in pendentes])
        return gravados

    def _etapas_conta_corrente(self, page, dados, conta_alvo, chave_competencia, telemetria_lote):
        """Recebimentos de outras administrações, transferências entre contas e tarifas.

        Cada etapa decide pela matriz em memória, já com o que a anterior gravou.

        Returns:
            bool: True se alguma etapa gravou (ou pode ter gravado) e a conferência final
            precisa reler o SIGA.
        """
        gravou = False
        try:
            with self._medir("Recebimentos de outras administrações"):
                gravou = self._confirmar_recebimentos(page, dados, conta_alvo, telemetria_lote) or gravou
            transf = a_lancar_transferencias(getattr(self, "_pares_transf", []), conta_alvo, dados.get("extrato_siga"))
            if transf:
                with self._medir("Transferências entre contas"):
                    gravou = self._lancar_transferencias(page, transf, conta_alvo, dados, telemetria_lote) or gravou
            faltas = self._faltas_na_matriz(dados)
            if faltas:
                with self._medir("Tarifas bancárias"):
                    gravou = self._lancar_tarifas(page, dados, conta_alvo, faltas, telemetria_lote) or gravou
        except MesFechadoError:
            self.competencias_fechadas.add(chave_competencia)
            self.update_status(f"⛔ [{self.localidade_selecionada}] Mês fechado: transferências e tarifas "
                               "ficaram pendentes.", "#D9534F")
            return True  # o que veio antes do aviso pode ter sido gravado: a releitura confere
        return gravou

    def _faltas_na_matriz(self, dados):
        """Movimentos do banco sem lançamento na matriz, nas mesmas condições da prova real.

        Returns:
            list | None: None quando o saldo do extrato é de outra data ou o extrato não traz
            os movimentos completos (aí as tarifas não são apontadas, como antes).
        """
        saldo_banco, data_saldo = dados.get("saldo_atual"), dados.get("data_saldo")
        if saldo_banco is not None and data_saldo and data_saldo != dados.get("data_final"):
            return None
        movimentos = movimentos_do_banco(dados)
        return parear(movimentos, dados.get("extrato_siga"))[1] if movimentos is not None else None

    def _conferencia_final(self, page, dados, consulta, pendentes, relancar, releitura, is_aplicacao,
                           chave_competencia, telemetria_lote):
        """Relê o SIGA uma vez no fim do extrato e, se faltar lançamento, tenta de novo só o que faltou.

        A releitura refaz o filtro (conta e período do extrato): depois de gravar, a TES01701 volta
        com o filtro padrão (mês atual), e reaproveitá-lo fazia um extrato de outro mês parecer não
        lançado. Se a releitura não acha nenhum dos itens gravados, o bot não tenta de novo: lançar
        outra vez duplicaria tudo o que já foi gravado.

        Args:
            consulta: (conta, data inicial, data final) do extrato, para refazer o filtro.
            pendentes: Lançamentos de investimento tentados (ou recusados na prévia).
            relancar: True se `pendentes` foram tentados e podem ser tentados de novo.
            releitura: True se algo foi gravado neste extrato; sem isso a leitura do começo vale.

        Returns:
            tuple: (lançamentos que continuaram sem par, True se a matriz é a leitura real do
            SIGA, True se o mês fechou numa nova tentativa).
        """
        if not releitura:
            return pendentes, True, False
        tentativa, ultima_qtd = 1, self._qtd_injecoes_efetuadas if relancar else 0
        while True:
            self.update_status("Realizando conferência final no SIGA...", "#428BCA")
            self.esperar_loading(page)
            try:
                grade = self._abrir_consulta_tes01701(page, *consulta)
                if grade is None:
                    raise RuntimeError(f"conta {consulta[0]} não encontrada no filtro")
            except Exception as e:
                logging.error(f"Erro na conferência final: {e}")
                self.update_status(f"✅ [{self.localidade_selecionada}] Finalizado sem prova real.", "#3C763D")
                return pendentes, False, False
            dados["extrato_siga"] = grade
            if not relancar or not pendentes:
                return pendentes, True, False
            restantes = Conciliador.conciliar(dados.get("transacoes", []), grade)
            if not restantes:
                self.update_status(f"✅ [{self.localidade_selecionada}] Conferência 100%: Nenhum item para trás!",
                                   "#3C763D")
                return [], True, False
            if ultima_qtd and len(restantes) >= len(pendentes):
                logging.error(f"Conferência não achou nenhum dos {ultima_qtd} lançamento(s) "
                              "gravado(s); re-tentativa cancelada para não duplicar.")
                self.update_status(f"⛔ [{self.localidade_selecionada}] A conferência não encontrou os "
                                   f"{ultima_qtd} lançamento(s) gravado(s). Confira no SIGA "
                                   "antes de rodar de novo: o robô não lançou outra vez.", "#D9534F")
                return restantes, True, False
            if tentativa >= _LIMITE_TENTATIVAS:
                return restantes, True, False
            tentativa, pendentes = tentativa + 1, restantes
            self.update_status(f"🔄 Re-tentativa {tentativa}/{_LIMITE_TENTATIVAS}: Injetando "
                               f"{len(pendentes)} lançamentos restantes...", "#F89406")
            try:
                ultima_qtd = self._gravar_investimentos(page, pendentes, is_aplicacao, telemetria_lote, dados)
            except MesFechadoError:
                self.competencias_fechadas.add(chave_competencia)
                self.update_status(f"⛔ [{self.localidade_selecionada}] Mês {chave_competencia[1]} fechado no "
                                   f"SIGA. {len(pendentes)} lançamento(s) ficaram pendentes.", "#D9534F")
                return pendentes, False, True

    def _prova_real(self, dados, grade_atual):
        """Confere o saldo final da última leitura com o do banco e procura lançamentos sem par.

        Usa o saldo lido junto com a grade (`_saldo_tes01701`); nunca lança nem corrige nada.

        Returns:
            tuple: (ResultadoSaldo, sobras do SIGA, faltas no SIGA); as listas são None quando não
            dá para apontá-las.
        """
        saldo_banco = dados.get("saldo_atual")
        if not grade_atual:
            return nao_conferido("a grade do SIGA não foi relida depois dos lançamentos", saldo_banco), None, None
        data_saldo = dados.get("data_saldo")
        if saldo_banco is not None and data_saldo and data_saldo != dados.get("data_final"):
            return nao_conferido(f"o saldo do extrato é de {data_saldo}", saldo_banco), None, None

        texto = getattr(self, "_saldo_tes01701", None)
        saldo = conferir_saldo(saldo_banco, valor_br(texto) if texto is not None else None)

        movimentos = movimentos_do_banco(dados)
        sobras, faltas = parear(movimentos, dados.get("extrato_siga")) if movimentos is not None else (None, None)

        if saldo.status == CONFERE:
            self.update_status(f"🧾 Prova real: saldo confere ({Exportador.formatar_moeda(saldo.saldo_siga)}).", "#3C763D")
        elif saldo.status == DIVERGE:
            extra = f" · {len(sobras)} lançamento(s) no SIGA sem par no extrato" if sobras else ""
            self.update_status(f"⚠️ Prova real: SIGA {Exportador.formatar_moeda(saldo.saldo_siga)} × banco "
                               f"{Exportador.formatar_moeda(saldo.saldo_banco)} (diferença "
                               f"{Exportador.formatar_moeda(saldo.diferenca)}){extra}.", "#F89406")
        return saldo, sobras, faltas
