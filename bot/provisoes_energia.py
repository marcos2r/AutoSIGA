"""
Provisão das faturas de energia do período, antes dos extratos.

Pelo regime de competência, toda fatura emitida no mês é provisionada, debitada ou não.
Com o e-mail conectado, o robô baixa as faturas do período do lote, confere na Contas a
Pagar (TES01501) o que já existe, mostra a prévia e lança o resto pela TES01502. Assim a
baixa de cada extrato já encontra a provisão. Sem e-mail, a etapa é pulada com aviso.
"""

import logging
from datetime import timedelta

from controllers.fatura_energia_controller import FaturaEnergiaController
from controllers.periodo_energia import janela_de_busca, meses_do_lote
from controllers.provisao_energia import (
    LANCADA,
    LANCAR,
    NAO_AUTORIZADA,
    NAO_LANCADA,
    decidir_provisoes,
    item_da_previa,
    linhas_do_painel,
)
from models.email_reader import EmailReader, mensagem_de_erro

# A fatura vence semanas depois da emissão: a leitura da Contas a Pagar vai até 60 dias além da busca
_DIAS_DE_VENCIMENTO = 60


class ProvisoesEnergiaMixin:
    """Etapa de provisões de energia no início do lote de extratos."""

    def _buscar_faturas_do_periodo(self):
        """Baixa do e-mail as faturas dos meses do lote. Roda antes de abrir o navegador, para o
        usuário ver o progresso em vez de uma tela do SIGA parada.

        Returns:
            dict | None: {"meses", "faturas": (validas, sem_localidade, sem_emissao)}; {"linhas"}
            se a leitura do e-mail falhou; None se a etapa não roda (sem e-mail ou sem período).
        """
        meses = meses_do_lote(self.lote_processados)
        if not meses:
            return None
        if not EmailReader.conectado():
            self.update_status("E-mail não conectado: provisões de energia não buscadas.", "#666666")
            return None
        try:
            faturas = FaturaEnergiaController.buscar_faturas_do_periodo(meses, self.update_status)
        except Exception as erro:
            logging.exception("Falha ao buscar as faturas de energia no e-mail.")
            motivo = mensagem_de_erro(erro)
            self.update_status(f"⚠️ Provisões de energia puladas: não consegui ler o e-mail ({motivo}).", "#F89406")
            return {"linhas": [("alerta", f"⚡ Provisões de energia não verificadas: {motivo}")]}
        return {"meses": meses, "faturas": faturas}

    def _etapa_provisoes_energia(self, page):
        """Provisiona as faturas de energia emitidas nos meses do lote.

        Usa as faturas já baixadas em `self._busca_energia` (antes de abrir o navegador) ou
        busca agora, se ninguém buscou.

        Returns:
            list[tuple[str, str]] | None: Linhas (nível, texto) para o painel; None se a
            etapa não rodou (e-mail não conectado ou lote sem período).
        """
        busca = self._busca_energia if self._busca_energia is not None else self._buscar_faturas_do_periodo()
        self._busca_energia = None
        if busca is None or "linhas" in busca:
            return busca and busca["linhas"]
        meses = busca["meses"]
        validas, sem_localidade, sem_emissao = busca["faturas"]
        if not (validas or sem_localidade or sem_emissao):
            return [("neutro", f"⚡ Provisões de energia: nenhuma fatura emitida de {meses[0]} a {meses[-1]} no e-mail")]

        # Só lê: sem a Contas a Pagar completa não dá para saber o que já existe, e nada é lançado
        inicio, fim = janela_de_busca(meses)
        periodo = (inicio.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y"))
        try:
            self._garantir_localidade_competencia(page, "", meses[-1])
            provisoes = self._ler_provisoes_energisa(page, (periodo[0], _somar_dias(fim, _DIAS_DE_VENCIMENTO)))
        except Exception as erro:
            logging.exception("Falha ao ler as provisões de energia na TES01501.")
            self._capturar_tela_e_log(page, "erro_ler_provisoes_periodo")
            self.update_status(f"⚠️ Provisões de energia puladas: não consegui ler a Contas a Pagar ({erro}).",
                               "#F89406")
            return [("alerta", f"⚡ Provisões de energia não lançadas: falha ao ler a Contas a Pagar ({erro})")]

        decisoes = decidir_provisoes(validas, sem_localidade, sem_emissao, provisoes)
        a_lancar = [d for d in decisoes if d.acao == LANCAR]
        situacoes = {}
        if a_lancar:
            previa = [item_da_previa(d) for d in a_lancar]
            if self._pedir_autorizacao(previa, "Contas a Pagar", tipo="provisoes"):
                # Cada fatura é conferida de novo na TES01501 logo antes de gravar
                self.inserir_faturas_energia_siga(page, [d.fatura for d in a_lancar])
                confirmadas = {f.get("numero_fatura") for f in self.faturas_energia_sucesso}
                for d in a_lancar:
                    numero = d.fatura["numero_fatura"]
                    situacoes[numero] = (LANCADA, "") if numero in confirmadas else (
                        NAO_LANCADA, self.motivos_energia.get(numero, "não confirmada no SIGA: veja o log"))
            else:
                situacoes = {d.fatura["numero_fatura"]: (NAO_AUTORIZADA, "provisão não autorizada na prévia")
                             for d in a_lancar}
            # Os PDFs novos entram no índice da baixa dos extratos
            self._indice_energia = None

        linhas = linhas_do_painel(decisoes, situacoes)
        self.update_status(linhas[0][1], "#3C763D" if linhas[0][0] == "ok" else "#F89406")
        return linhas


def _somar_dias(data, dias):
    return (data + timedelta(days=dias)).strftime("%d/%m/%Y")
