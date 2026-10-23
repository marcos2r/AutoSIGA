"""Extrato de conta corrente do Sicredi em XLS (dados fictícios)."""

from typing import Any

from test_xls_reader import _ler

from controllers.catalogo_contas import mesmo_extrato
from models.xls_conta_corrente import montar_memo

# A descrição do banco tem no máximo 48 caracteres; esta chega ao limite e corta o código da UC
ENERGIA_CORTADA = "DEBITO CONVENIOS 12345678901234 ENERGISA MS ID 0"
ENERGIA_INTEIRA = "DEBITO CONVENIOS 12345678901234 ENERGIA ID 77"


def _extrato(movimentos: list[list[Any]], saldo_anterior: float = 100.0) -> list[list[Any]]:
    return [
        [""],
        ["Associado:", "IGREJA EXEMPLO"],
        ["Cooperativa:", "0101"],
        ["Conta:", "12345-6"],
        [""],
        ["Extrato"],
        ["Dados referentes ao período de 01/09/2026 a 30/09/2026."],
        [""],
        ["Data", "Descrição", "Documento", "Valor (R$)", "Saldo (R$)"],
        ["", "Saldo Anterior", "", "", saldo_anterior],
        *movimentos,
        ["", "", "", "", ""],
        ["Saldo da Conta em 23/10/2026"],
        ["Saldo atual (disponível em conta)", "", 0.0],
        ["Lançamentos Futuros (Próximos 30 dias)"],
        ["Data", "Descrição", "Valor (R$)"],
        ["26/10/2026", "DÉBITO AUTOMÁTICO ENERGISA MS", -725.1],
    ]


MOVIMENTOS = [
    ["01/09/2026", "DEBITO CONVENIOS 12345678901234 SANESUL ID 20804", "SANESUL  ", -31.7, 68.3],
    ["01/09/2026", ENERGIA_CORTADA, "ENERGI 70", -81.41, -13.11],
    ["01/09/2026", "RESG.APLIC.FIN.AVISO PREV", "CAPTACAO", 13.11, 0.0],
]


def test_le_no_formato_do_ofx_e_para_antes_dos_lancamentos_futuros(monkeypatch, tmp_path):
    dados = _ler(monkeypatch, tmp_path, _extrato(MOVIMENTOS), aba="Extrato")

    assert "tipo_extrato" not in dados  # conta corrente, como o OFX
    assert (dados["banco"], dados["conta_id"]) == ("748", "12345-6")
    assert (dados["data_inicial"], dados["data_final"]) == ("01/09/2026", "30/09/2026")
    assert (dados["saldo_atual"], dados["data_saldo"]) == (0.0, "30/09/2026")
    assert [(t["data"], t["valor"], t["tipo"]) for t in dados["transacoes"]] == [
        ("01/09/2026", -31.7, "debit"), ("01/09/2026", -81.41, "debit"), ("01/09/2026", 13.11, "credit")]
    assert [t["descricao"] for t in dados["transacoes"]] == [
        # As duas descrições chegam aos 48 caracteres: o número final pode estar cortado e é descartado
        "DEBITO CONVENIOS-SANESUL   12345678901234 SANESUL ID",
        "DEBITO CONVENIOS-ENERGI 70 12345678901234 ENERGISA MS ID",
        "RESG.APLIC.FIN.AVISO PREV-CAPTACAO",
    ]


def test_saldo_que_nao_fecha_fica_sem_conferencia(monkeypatch, tmp_path):
    dados = _ler(monkeypatch, tmp_path, _extrato(MOVIMENTOS, saldo_anterior=90.0), aba="Extrato")

    assert dados["saldo_atual"] is None and dados["data_saldo"] is None
    assert len(dados["transacoes"]) == 3


def test_montar_memo_como_o_ofx():
    assert montar_memo(ENERGIA_INTEIRA, "ENERGI 70") == "DEBITO CONVENIOS-ENERGI 70 12345678901234 ENERGIA ID 77"
    assert montar_memo("LIQUIDACAO BOLETO 12345678901234 FORNECEDOR", " ") == \
        "LIQUIDACAO BOLETO-          12345678901234 FORNECEDOR"
    assert montar_memo("CESTA DE RELACIONAMENTO", "") == "CESTA DE RELACIONAMENTO"


def test_mesmo_extrato_em_ofx_e_xls_e_descartado():
    ofx = {"conta_id": "0101000000123456", "data_inicial": "01/09/2026", "data_final": "30/09/2026"}
    xls = dict(ofx, conta_id="12345-6")

    assert mesmo_extrato(ofx, xls)
    assert not mesmo_extrato(ofx, dict(xls, data_inicial="01/10/2026", data_final="31/10/2026"))
    assert not mesmo_extrato(ofx, dict(xls, conta_id="65432-1"))
