"""Planejamento das tarifas do extrato (Fase 2, parte pura)."""

from controllers.prova_real import MovimentoBanco
from controllers.tarifas import (
    PADRAO,
    RegraTarifa,
    cidade_da_localidade,
    escolher_fornecedor,
    planejar,
    termos_do_banco,
)

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


def test_termos_por_banco_e_config_na_frente():
    assert termos_do_banco("0748") == ["SICREDI"]
    assert termos_do_banco("748", {"748": "SICREDI CENTRO-SUL"}) == ["SICREDI CENTRO-SUL", "SICREDI"]
    assert termos_do_banco("999") == []


# Resultados como o SIGA de Dourados devolve para "SICREDI" (23/11/2026)
RESULTADOS = [
    "BANCO COOPERATIVO SICREDI S.A. Fornecedor AVENIDA ASSIS BRASIL, 3940 - PORTO ALEGRE - RS",
    "SICREDI CENTRO-SUL MS/BA COOPERATIVA DE CRÉDITO Fornecedor AVENIDA WEIMAR GONÇALVES TORRES - DOURADOS - MS",
]


def test_escolhe_o_fornecedor_da_cidade_da_administracao():
    assert escolher_fornecedor(RESULTADOS, "SICREDI", "DOURADOS") == 1
    assert escolher_fornecedor(RESULTADOS, "SICREDI", "CAMPO GRANDE") == 0   # sem o da cidade: o primeiro
    assert escolher_fornecedor(RESULTADOS, "SICOOB", "DOURADOS") is None


def test_cidade_e_config_de_fornecedores():
    assert cidade_da_localidade("DOURADOS - MS") == "DOURADOS"
    regra = RegraTarifa.da_config({"fornecedores": {"0748": "SICREDI CENTRO-SUL"}})
    assert dict(regra.fornecedores) == {"748": "SICREDI CENTRO-SUL"}
