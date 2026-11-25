"""Fatura do cartão: leitura do XLS e decisão da baixa das compras (Fase 4)."""

import pytest

from controllers import baixa_cartao as bc
from controllers.baixa_contas_pagar import BAIXAR, EMPATE, SEM_PROVISAO, ParcelaSiga
from models.xls_fatura_cartao import TIPO_FATURA_CARTAO, eh_fatura_cartao, ler_fatura_cartao


class PlanilhaFalsa:
    """Imita a aba do xlrd (nrows e row_values)."""

    def __init__(self, linhas):
        self._linhas = linhas
        self.nrows = len(linhas)
        self.ncols = max(len(linha) for linha in linhas)

    def cell_value(self, r, c):
        linha = self._linhas[r]
        return linha[c] if c < len(linha) else ""


# Formato do XLS real do Sicredi (dados fictícios)
LINHAS = [
    ["", "", "", ""],
    ["Associado:", "CONGREGACAO CRISTA NO BRASIL", "", ""],
    ["Conta Corrente:", "58416-3", "", ""],
    ["Cartão Sicredi Visa Empresarial - Extrato Mensal", "", "", ""],
    ["Data de Vencimento:", "13/10/2026", "", ""],
    ["Valor Total(R$):", "1.172,12", "", ""],
    ["Histórico de Despesas", "", "", ""],
    ["Cartão: 4960.45XX.XXXX.0119 - PORTADOR TESTE", "", "", ""],
    ["Data", "Descrição", "Parcela", "Valor (R$)"],
    ["24/09/2026", "DELICATESSEN PANIFIC", "01/01", "182,12"],
    ["19/09/2026", "PAIVINHA COMERCIO DE", "01/01", "990,00"],
    ["13/09/2026", "Pag Fat Deb Cc", "01/01", "-3.747,26"],
    ["Total R$:", "1.172,12", "", ""],
]


def fatura():
    return ler_fatura_cartao(PlanilhaFalsa(LINHAS), "fatura.xls")


def test_le_a_fatura_e_ignora_o_pagamento_anterior():
    assert eh_fatura_cartao(PlanilhaFalsa(LINHAS))
    f = fatura()
    assert (f["tipo_extrato"], f["conta_id"], f["vencimento"], f["total"]) == (TIPO_FATURA_CARTAO, "58416-3",
                                                                               "13/10/2026", 1172.12)
    assert [(c["descricao"], c["valor"], c["portador"]) for c in f["compras"]] == [
        ("DELICATESSEN PANIFIC", 182.12, "PORTADOR TESTE"), ("PAIVINHA COMERCIO DE", 990.0, "PORTADOR TESTE")]


def test_compras_que_nao_somam_o_total_recusam_o_arquivo():
    linhas = [list(linha) for linha in LINHAS]
    linhas[5][1] = "2.000,00"
    with pytest.raises(ValueError):
        ler_fatura_cartao(PlanilhaFalsa(linhas))


def parcela(numero, fornecedor, valor, vencimento="13/10/2026", status="Lançado"):
    return ParcelaSiga(numero, fornecedor, valor, status, f"{numero:0>8}-0000-0000-0000-000000000000", vencimento)


DEBITO = bc.debitos_de_fatura([{"data": "13/10/2026", "valor": -1172.12, "descricao": "DEB.CTA.FATURA-123"}])[0]


def test_reconhece_o_debito_e_a_fatura():
    assert (DEBITO.valor, DEBITO.tipo) == (1172.12, bc.CARTAO)
    assert bc.fatura_do_debito(DEBITO, [fatura()]) is not None
    assert bc.fatura_do_debito(DEBITO, [{**fatura(), "total": 10.0}]) is None


def test_todas_as_compras_com_provisao_baixam_juntas():
    parcelas = [parcela("101", "DELICATESSEN PANIFICADORA LTDA", 182.12),
                parcela("102", "PAIVINHA COMERCIO DE MOVEIS", 990.0),
                parcela("103", "OUTRO", 990.0, vencimento="13/12/2026")]   # fora da janela
    d = bc.decidir_fatura(DEBITO, fatura(), parcelas)
    assert d.acao == BAIXAR and [p.numero for p in d.parcelas] == ["101", "102"]


def test_compra_sem_provisao_ou_empate_vira_pendencia():
    so_uma = [parcela("101", "DELICATESSEN PANIFICADORA LTDA", 182.12)]
    d = bc.decidir_fatura(DEBITO, fatura(), so_uma)
    assert d.acao == SEM_PROVISAO and "PAIVINHA" in d.motivo
    duas = so_uma + [parcela("201", "LOJA A", 990.0), parcela("202", "LOJA B", 990.0)]
    assert bc.decidir_fatura(DEBITO, fatura(), duas).acao == EMPATE


def test_sem_xls_da_fatura_avisa():
    d = bc.decidir_fatura(DEBITO, None, [])
    assert d.acao == SEM_PROVISAO and "XLS" in d.motivo
