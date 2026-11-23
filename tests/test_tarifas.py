"""Planejamento das tarifas do extrato (Fase 2, parte pura)."""

from controllers.prova_real import MovimentoBanco
from controllers.tarifas import PADRAO, RegraTarifa, planejar

FALTAS = [
    MovimentoBanco("05/11/2026", -45.0, "CESTA DE RELACIONAMENTO"),
    MovimentoBanco("06/11/2026", -12.5, "TARIFA PIX  ENVIADO"),
    MovimentoBanco("06/11/2026", 45.0, "CESTA DE RELACIONAMENTO"),   # estorno: crédito não é despesa
    MovimentoBanco("07/11/2026", -300.0, "LIQUIDACAO BOLETO- 12345678000199 X LTDA"),
]


def test_ligado_por_padrao_e_desligavel_pelo_config():
    assert PADRAO["ativo"] is True  # contas confirmadas pelo usuário em 23/11/2026
    assert planejar(FALTAS, RegraTarifa.da_config({"ativo": False})) == []


def test_ligado_planeja_uma_despesa_por_tarifa():
    regra = RegraTarifa.da_config({"ativo": True})
    lancamentos = planejar(FALTAS, regra)
    assert [(lc.data, lc.valor, lc.documento) for lc in lancamentos] == [
        ("05/11/2026", 45.0, "05112026"), ("06/11/2026", 12.5, "06112026")]
    assert lancamentos[1].descricao == "TARIFA PIX ENVIADO"


def test_config_do_usuario_sobrepoe_padrao_e_ignora_chave_estranha():
    regra = RegraTarifa.da_config({"ativo": True, "despesa": "3031", "qualquer": 1})
    assert regra.despesa == "3031" and regra.historico == PADRAO["historico"]


def test_sem_faltas():
    assert planejar(None, RegraTarifa.da_config({"ativo": True})) == []
