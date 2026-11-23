"""Classificador único das linhas do extrato (Fase 0 do plano de automações)."""

import pytest

from controllers import baixa_contas_pagar, baixa_energia
from controllers import classificador_extrato as ce
from controllers.conciliador import Conciliador
from controllers.exportador import Exportador


def tx(descricao, valor, historico=""):
    return {"data": "10/10/2026", "descricao": descricao, "valor": valor, "historico": historico}


# Descrições no formato dos extratos reais do Sicredi e do Sicoob (dados fictícios)
CASOS = [
    ("RECEBIMENTO PIX-PIX_CRED 12345678900", 50.0, ce.OFERTA),
    ("RECEBIMENTO PIX-CX123 99", 20.0, ce.OFERTA),
    ("DEP DINHEIRO CAIXA", 300.0, ce.DEPOSITO),
    ("DEP DINHEIRO ATM-AB12", 150.0, ce.DEPOSITO),
    ("RESG.APLIC.FIN.AVISO PREV-CAPTACAO", 1000.0, ce.RESGATE),
    ("APLICACAO FINANCEIRA-CAPTACAO", -1000.0, ce.APLICACAO),
    ("RENDIMENTOS", 12.34, ce.RENDIMENTO),
    ("DEBITO CONVENIOS-ENERGI 70 ID 1234567890 ENERGISA MS", -210.0, ce.ENERGIA),
    ("DEBITO CONVENIOS-SANESUL 22", -80.0, ce.CONVENIO),
    ("LIQUIDACAO BOLETO-  12345678000199 FORNECEDOR LTDA", -500.0, ce.BOLETO),
    ("LIQUIDACAO BOLETO SICREDI-123", -90.0, ce.BOLETO),
    ("PAGAMENTO PIX-PIX_DEB 12345678000199 FORNECEDOR LTDA", -75.0, ce.PIX_FORNECEDOR),
    ("DEB.CTA.FATURA-123", -400.0, ce.FATURA_CARTAO),
    ("CESTA DE RELACIONAMENTO", -45.0, ce.TARIFA),
    ("INTEGR.CAPITAL SUBSCRITO-1", -10.0, ce.COTA_CAPITAL),
    ("DEBITO ARRECADACAO-DARFC0190 12345678000199 DARFC0190", -33.0, ce.GUIA),
    ("TRANSF ENTRE CONTAS-SI123", -700.0, ce.DESCONHECIDA),
    ("TRANSFERENCIA RECEBIDA", 700.0, ce.TRANSFERENCIA),
    ("DEBITO TED-IB 123", -1500.0, ce.TRANSFERENCIA),
    ("ALGO QUE NINGUEM CONHECE", -1.0, ce.DESCONHECIDA),
]


@pytest.mark.parametrize("descricao,valor,esperada", CASOS)
def test_classifica_linhas_tipicas(descricao, valor, esperada):
    assert ce.classificar(tx(descricao, valor)).categoria == esperada


def test_pagador_congregacao_no_historico_e_transferencia():
    """No Sicoob o pagador fica só no histórico: repasse de outra administração não é oferta."""
    assert ce.classificar(tx("PIX RECEBIDO", 900.0, "CONGREGACAO CRISTA NO BRASIL")).categoria == ce.TRANSFERENCIA


def test_acentos_e_espacos_nao_atrapalham():
    assert ce.classificar(tx("  aplicação   financeira ", -10.0)).categoria == ce.APLICACAO


def test_boleto_a_fundo_de_investimento_nao_e_aplicacao():
    """A palavra-chave antiga 'INVEST' fazia o boleto de um FIDC parecer aplicação."""
    c = ce.classificar(tx("LIQUIDACAO BOLETO- 12345678000199 BMA FUNDO DE INVESTIMENTO", -300.0))
    assert c.categoria == ce.BOLETO and not c.eh_investimento


def test_primeira_regra_que_casa_decide():
    regras = ce.montar_regras([{"categoria": "a", "padrao": "X"}, {"categoria": "b", "padrao": "X"}])
    assert ce.classificar(tx("X", -1.0), regras).categoria == "a"


@pytest.mark.parametrize("ruim", [
    {"padrao": "X"},
    {"categoria": "a", "padrao": "("},
    {"categoria": "a", "padrao": "X", "sinal": "*"},
    {"categoria": "a", "padrao": "X", "campo": "memo"},
])
def test_regra_invalida_e_recusada(ruim):
    with pytest.raises(ValueError):
        ce.montar_regras([ruim])


def test_concorda_com_a_extracao_de_energia_e_pagamentos():
    """Energia, boleto e PIX ainda extraem ID e CNPJ pelas próprias regex; a categoria tem de bater."""
    for descricao, valor, esperada in CASOS:
        linha = tx(descricao, valor)
        energia = bool(baixa_energia._RE_DEBITO_ENERGIA.search(descricao)) and valor < 0
        pagamento = bool(baixa_contas_pagar.ler_pagamentos([linha]))
        assert energia == (esperada == ce.ENERGIA), descricao
        if pagamento:
            assert esperada in (ce.BOLETO, ce.PIX_FORNECEDOR), descricao


def test_conciliador_so_olha_investimentos():
    linhas = [tx(d, v) for d, v, _ in CASOS]
    a_lancar = Conciliador.conciliar(linhas, [])
    assert {ce.classificar(t).categoria for t in a_lancar} == set(ce.INVESTIMENTOS)


def test_txt_de_ofertas_so_leva_ofertas():
    linhas = [tx(d, v) for d, v, _ in CASOS]
    ofertas, descartadas = Exportador.filtrar_ofertas(linhas)
    assert [t["descricao"] for t in ofertas] == [d for d, _, cat in CASOS if cat == ce.OFERTA]
    assert descartadas == len(CASOS) - len(ofertas)
