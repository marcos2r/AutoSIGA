"""Etapa de tarifas do robô (bot/tarifas.py), sem navegador: só a orquestração."""

from bot.tarifas import TarifasMixin
from controllers.prova_real import MovimentoBanco
from controllers.tarifas import RegraTarifa

TARIFA = MovimentoBanco("05/11/2026", -45.0, "CESTA DE RELACIONAMENTO")
BOLETO = MovimentoBanco("06/11/2026", -300.0, "LIQUIDACAO BOLETO- 12345678000199 X LTDA")


class RoboFalso(TarifasMixin):
    def __init__(self, ativo=True, autoriza=True, grava=1, grade=("linha",)):
        self.regra_tarifas = RegraTarifa.da_config({"ativo": ativo})
        self._autoriza, self._grava, self._grade = autoriza, grava, grade
        self.gravou, self.status = [], []

    def _pedir_autorizacao(self, itens, conta, tipo="lancamentos"):
        self.previa = (itens, conta, tipo)
        return self._autoriza

    def inserir_tarifas_siga(self, page, plano, conta, regra, fornecedor="SICREDI"):
        self.gravou, self.fornecedor = plano, fornecedor
        return self._grava

    def _abrir_consulta_tes01701(self, page, *consulta):
        return list(self._grade) if self._grade is not None else None

    def update_status(self, texto, cor=None):
        self.status.append(texto)


def rodar(robo, faltas):
    telemetria, dados = {"injecoes": 0}, {}
    resultado = robo._lancar_tarifas(None, dados, "10130", faltas, ("10130", "01/11/2026", "30/11/2026"), telemetria)
    return resultado, telemetria, dados


def test_grava_so_as_tarifas_e_rele_a_grade():
    robo = RoboFalso()
    resultado, telemetria, dados = rodar(robo, [TARIFA, BOLETO])
    assert resultado is True and telemetria["injecoes"] == 1
    assert [lc.valor for lc in robo.gravou] == [45.0]
    assert robo.previa[2] == "tarifas" and dados["extrato_siga"] == ["linha"]


def test_sem_tarifa_nao_faz_nada():
    robo = RoboFalso()
    assert rodar(robo, [BOLETO])[0] is False and robo.gravou == []


def test_desligado_nao_grava():
    robo = RoboFalso(ativo=False)
    assert rodar(robo, [TARIFA])[0] is False and robo.gravou == []


def test_previa_recusada_nao_grava():
    robo = RoboFalso(autoriza=False)
    assert rodar(robo, [TARIFA])[0] is False and robo.gravou == []


def test_nada_gravado_nao_refaz_prova_real():
    robo = RoboFalso(grava=0)
    resultado, telemetria, _ = rodar(robo, [TARIFA])
    assert resultado is False and telemetria["injecoes"] == 0


def test_conta_sumiu_na_releitura():
    assert rodar(RoboFalso(grade=None), [TARIFA])[0] is False


def test_fornecedor_e_o_banco_do_extrato():
    robo = RoboFalso()
    robo._lancar_tarifas(None, {"banco": "756"}, "10130", [TARIFA], ("10130", "", ""), {"injecoes": 0})
    assert robo.fornecedor == "SICOOB"


class PaginaComErro:
    def __init__(self, texto):
        self.texto = texto

    def evaluate(self, js):
        return self.texto


def test_gravacao_recusada_pelo_siga_vira_erro():
    import pytest
    robo = RoboFalso()
    robo._capturar_tela_e_log = lambda page, nome: None
    with pytest.raises(RuntimeError, match="recusou"):
        robo._recusar_se_invalido(PaginaComErro("Formulário Incompleto: Fornecedor é obrigatório"))
    robo._recusar_se_invalido(PaginaComErro("Registro salvo com sucesso!"))  # sucesso não para
