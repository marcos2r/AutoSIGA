"""Etapa de transferências entre contas do robô, sem navegador: só a orquestração."""

from bot.transferencias_internas import TransferenciasInternasMixin
from controllers.transferencias_internas import MOTIVO_SEM_PAR, PontaSolta, TransferenciaInterna

T = TransferenciaInterna("SI00119", "26/10/2026", 45922.43, "10130", "10123", "TRANSF ENTRE CONTAS-SI00119")


class RoboFalso(TransferenciasInternasMixin):
    def __init__(self, autoriza=True, grava=1, lote=()):
        self._autoriza, self._grava, self.lote_processados = autoriza, grava, list(lote)
        self.gravou, self.status = [], []

    def _pedir_autorizacao(self, itens, conta, tipo="lancamentos"):
        self.previa = (itens, tipo)
        return self._autoriza

    def inserir_transferencias_siga(self, page, transferencias):
        self.gravou = transferencias
        return self._grava

    def _abrir_consulta_tes01701(self, page, *consulta):
        return ["linha"]

    def update_status(self, texto, cor=None):
        self.status.append(texto)


def rodar(robo, transferencias):
    telemetria, dados = {"injecoes": 0}, {}
    r = robo._lancar_transferencias(None, transferencias, "10130", ("10130", "", ""), dados, telemetria)
    return r, telemetria, dados


def test_grava_e_rele_a_grade():
    robo = RoboFalso()
    r, telemetria, dados = rodar(robo, [T])
    assert r is True and telemetria["injecoes"] == 1 and dados["extrato_siga"] == ["linha"]
    assert robo.previa[1] == "transferencias" and "10130 → 10123" in robo.previa[0][0]["descricao"]


def test_sem_transferencia_ou_recusada_nao_grava():
    assert rodar(RoboFalso(), [])[0] is False
    robo = RoboFalso(autoriza=False)
    assert rodar(robo, [T])[0] is False and robo.gravou == []


def test_prepara_pares_do_lote_e_avisa_pontas_soltas():
    lote = [{"conta_siga_corrente": "10130", "tipo_adm": "ADM", "nome_adm": "DOURADOS",
             "transacoes": [{"data": "22/10/2026", "valor": -55000.0,
                             "descricao": "TRANSF ENTRE CONTAS-SI00825 03617925000174 X"}]}]
    robo = RoboFalso(lote=lote)
    robo._preparar_transferencias()
    assert robo._pares_transf == []
    assert robo._soltas_transf == [PontaSolta("10130", "22/10/2026", -55000.0,
                                              "TRANSF ENTRE CONTAS-SI00825 03617925000174 X", MOTIVO_SEM_PAR)]
    avisos = robo.avisos_transferencias("10130")
    assert len(avisos) == 1 and "55.000,00" in avisos[0]
    assert robo.avisos_transferencias("10123") == []
