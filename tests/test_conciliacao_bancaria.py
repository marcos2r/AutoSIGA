"""Conciliação no modelo do FOR.TES.02 a partir da prova real."""

import openpyxl
import pytest
from openpyxl.styles import Font, PatternFill

from controllers import conciliacao_bancaria as cb
from controllers.prova_real import (
    CONFERE,
    DIVERGE,
    NAO_CONFERIDO,
    MovimentoBanco,
    MovimentoSiga,
    ResultadoExtrato,
    ResultadoSaldo,
)


def resultado(saldo_banco, saldo_siga, sobras=(), faltas=(), status=DIVERGE):
    return ResultadoExtrato(
        conta_id="12345-6", conta_siga="10130", localidade="ADM - DOURADOS", tipo="CORRENTE",
        situacao="ok", saldo=ResultadoSaldo(status, saldo_banco, saldo_siga,
                                              0.0 if saldo_banco is None else round(saldo_siga - saldo_banco, 2)),
        sobras=list(sobras), faltas=list(faltas), periodo="01/10/2026 a 31/10/2026")


@pytest.mark.parametrize("historico,valor,linha", [
    ("CHEQUE 000123", -200.0, 2),
    ("CH 55 FORNECEDOR", -10.0, 2),
    ("DEP. COLETA CASA DE ORACAO", 300.0, 3),
    ("RENDAS BANCARIAS", 5.0, 6),
    ("PGTO.NF 123", -80.0, 7),
])
def test_linha_da_sobra(historico, valor, linha):
    assert cb.linha_da_sobra(MovimentoSiga("10/10/2026", valor, historico)) == linha


@pytest.mark.parametrize("descricao,valor,linha", [
    ("DEP DINHEIRO CAIXA", 300.0, 4),
    ("RECEBIMENTO PIX-PIX_CRED 1", 50.0, 8),
    ("CESTA DE RELACIONAMENTO", -45.0, 5),
])
def test_linha_da_falta(descricao, valor, linha):
    assert cb.linha_da_falta(MovimentoBanco("10/10/2026", valor, descricao)) == linha


def test_itens_explicam_a_diferenca_ao_centavo():
    # Banco 1.000,00; SIGA tem um depósito de 300 que o banco não tem e não tem a tarifa de 45
    r = resultado(1000.00, 1345.00,
                  sobras=[MovimentoSiga("31/10/2026", 300.0, "DEP. COLETA")],
                  faltas=[MovimentoBanco("15/10/2026", -45.0, "CESTA DE RELACIONAMENTO")])
    c = cb.montar(r)
    assert c is not None
    assert [i.efeito for i in c.itens[3]] == [300.0]
    assert [i.efeito for i in c.itens[5]] == [45.0]
    assert c.sem_explicacao == 0.0 and c.conciliado


def test_resto_sem_explicacao_aparece_na_linha_10():
    c = cb.montar(resultado(1000.00, 1010.50))
    assert c is not None and c.sem_explicacao == 10.50 and not c.conciliado


def test_um_centavo_e_tolerado():
    c = cb.montar(resultado(1000.00, 1000.01, status=CONFERE))
    assert c is not None and c.conciliado


def test_sem_saldo_conferido_nao_monta():
    assert cb.montar(resultado(None, None, status=NAO_CONFERIDO)) is None


def test_aba_do_excel_tem_as_10_linhas(tmp_path):
    wb = openpyxl.Workbook()
    c = cb.montar(resultado(1000.00, 1300.00, sobras=[MovimentoSiga("31/10/2026", 300.0, "DEP. COLETA")]))
    estilo = PatternFill(start_color="D9EDF7", end_color="D9EDF7", fill_type="solid")
    ws = cb.escrever_aba(wb, [c], estilo, Font(bold=True), Font())
    textos = [str(ws.cell(row=i, column=1).value or "") for i in range(1, ws.max_row + 1)]
    for numero in range(1, 11):
        assert any(t.startswith(f"{numero} - ") for t in textos), numero
    assert "Conciliado" in textos
    wb.save(tmp_path / "conciliacao.xlsx")
