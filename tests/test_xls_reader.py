import os
from dataclasses import dataclass
from typing import Any

import pytest
import xlrd

from models import xls_reader
from models.xls_reader import ExtratoNaoSuportadoError, XlsReader


def test_parse_xls_sucesso():
    # Caminho para a fixture sample_sicredi.xls
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sicredi.xls")

    dados = XlsReader.parse_file(fixture_path)

    assert dados["banco"] == "748"
    assert dados["conta_id"] == "58308-2"
    assert dados["tipo_extrato"] == "APLICACAO"
    assert dados["produto"] == "SICREDINVEST AUTOMATICO"
    assert dados["data_inicial"] == "01/05/2026"
    # Maio tem 31 dias: o rendimento do dia 31 não pode ficar fora do período
    assert dados["data_final"] == "31/05/2026"

    # Apenas a transação com histórico "RENDIMENTOS" é classificada como rendimento
    # O "RESGATE" é filtrado e ignorado
    assert len(dados["transacoes"]) == 1

    tx = dados["transacoes"][0]
    assert tx["data"] == "12/05/2026"
    assert tx["valor"] == 78.41
    assert tx["descricao"] == "RENDIMENTOS"
    assert tx["documento"] == "0"

    # Sem linhas de saldo na planilha não há o que conferir
    assert dados["saldo_anterior"] is None
    assert dados["saldo_atual"] is None
    assert [m["tipo"] for m in dados["movimentos"]] == ["RENDIMENTO", "RESGATE"]

def test_parse_xls_inexistente():
    with pytest.raises(FileNotFoundError) as excinfo:
        XlsReader.parse_file("caminho_inexistente_qualquer.xls")
    assert "não foi encontrado no disco" in str(excinfo.value)

def test_parse_xls_invalido(tmp_path):
    arquivo_invalido = tmp_path / "invalido.xls"
    arquivo_invalido.write_text("SOU UMA PLANILHA TOTALMENTE INVALIDA", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        XlsReader.parse_file(str(arquivo_invalido))
    assert "não pôde ser aberto como planilha Excel" in str(excinfo.value)


# --- Planilhas sintéticas -------------------------------------------------------
# O xlwt não faz parte das dependências, então as planilhas abaixo imitam a API do
# xlrd (cell, cell_value, nrows, ncols) com o layout real dos extratos do Sicredi.

@dataclass
class _Celula:
    value: Any
    ctype: int


class _AbaFalsa:
    def __init__(self, linhas: list[list[Any]]):
        self._linhas = linhas
        self.nrows = len(linhas)
        self.ncols = max(len(linha) for linha in linhas)

    def cell(self, r: int, c: int) -> _Celula:
        linha = self._linhas[r]
        valor = linha[c] if c < len(linha) else ""
        if isinstance(valor, float):
            return _Celula(valor, xlrd.XL_CELL_NUMBER)
        return _Celula(valor, xlrd.XL_CELL_TEXT if valor != "" else xlrd.XL_CELL_EMPTY)

    def cell_value(self, r: int, c: int) -> Any:
        return self.cell(r, c).value


class _PlanilhaFalsa:
    def __init__(self, linhas: list[list[Any]], aba: str = "Relatorio"):
        self._aba = _AbaFalsa(linhas)
        self._nome = aba

    def sheet_names(self) -> list[str]:
        return [self._nome]

    def sheet_by_index(self, _i: int) -> _AbaFalsa:
        return self._aba


def _ler(monkeypatch, tmp_path, linhas: list[list[Any]], aba: str = "Relatorio") -> dict[str, Any]:
    arquivo = tmp_path / "extrato.xls"
    arquivo.write_bytes(b"")  # parse_file confere se o arquivo existe
    monkeypatch.setattr(xls_reader.xlrd, "open_workbook", lambda _c: _PlanilhaFalsa(linhas, aba))
    return XlsReader.parse_file(str(arquivo))


def _cdb(mes_ano: str, movimentos: list[list[Any]], saldo_atual: list[Any] | None = None) -> list[list[Any]]:
    """Extrato Sicredinvest (sem coluna de saldo), conta fictícia 12345-6."""
    linhas: list[list[Any]] = [
        [""],
        ["Associado:", "IGREJA FICTICIA"],
        ["Cooperativa:", "0101"],
        ["Conta Corrente:", "12345-6"],
        [""],
        ["Extrato de Aplicação - Depósito a Prazo - Simplificado - Consolidado"],
        [f"Dados referentes ao período {mes_ano} a {mes_ano}."],
        ["Produto: ", "SICREDINVEST AUTOMATICO"],
        [""],
        ["Movimentação"],
        ["Data", "Histórico", "Valor (R$)"],
        *movimentos,
    ]
    if saldo_atual:
        linhas.append(saldo_atual)
    linhas += [[""], ["Posição para Saque"], ["Saldo Atual:", "", "999,99"]]
    return linhas


MOVIMENTOS_MAIO = [
    ["30/04/2026", "Saldo Anterior", "1.000,00"],
    ["04/05/2026", "Aplicacoes", "500,00"],
    ["06/05/2026", "Resgates", "200,00"],
    ["06/05/2026", "Rendimentos", "3,21"],
]


@pytest.mark.parametrize(
    ("mes_ano", "data_final"),
    [
        ("05/2026", "31/05/2026"),  # mês de 31 dias
        ("04/2026", "30/04/2026"),  # mês de 30 dias
        ("02/2026", "28/02/2026"),  # fevereiro
        ("02/2028", "29/02/2028"),  # fevereiro bissexto
    ],
)
def test_data_final_e_ultimo_dia_real_do_mes(monkeypatch, tmp_path, mes_ano, data_final):
    dados = _ler(monkeypatch, tmp_path, _cdb(mes_ano, [["10/" + mes_ano, "Rendimentos", "1,00"]]))

    assert dados["data_inicial"] == "01/" + mes_ano
    assert dados["data_final"] == data_final


def test_data_do_saldo_atual_prevalece(monkeypatch, tmp_path):
    linhas = _cdb("05/2026", MOVIMENTOS_MAIO, ["29/05/2026", "Saldo Atual", "1.303,21"])

    dados = _ler(monkeypatch, tmp_path, linhas)

    assert dados["data_final"] == "29/05/2026"
    assert dados["data_saldo"] == "29/05/2026"


def test_saldos_que_fecham(monkeypatch, tmp_path):
    # 1.000,00 - 200,00 + 500,00 + 3,21 = 1.303,21
    linhas = _cdb("05/2026", MOVIMENTOS_MAIO, ["31/05/2026", "Saldo Atual", "1.303,21"])

    dados = _ler(monkeypatch, tmp_path, linhas)

    assert dados["conta_id"] == "12345-6"
    assert dados["saldo_anterior"] == 1000.0
    assert dados["saldo_atual"] == 1303.21
    assert dados["data_saldo"] == "31/05/2026"
    assert dados["movimentos"] == [
        {"data": "04/05/2026", "tipo": "APLICACAO", "valor": 500.0},
        {"data": "06/05/2026", "tipo": "RESGATE", "valor": 200.0},
        {"data": "06/05/2026", "tipo": "RENDIMENTO", "valor": 3.21},
    ]
    # O bot continua recebendo só os rendimentos
    assert [tx["valor"] for tx in dados["transacoes"]] == [3.21]


def test_saldos_que_nao_fecham_ficam_none_mas_arquivo_e_aceito(monkeypatch, tmp_path, caplog):
    linhas = _cdb("05/2026", MOVIMENTOS_MAIO, ["31/05/2026", "Saldo Atual", "1.400,00"])

    with caplog.at_level("WARNING"):
        dados = _ler(monkeypatch, tmp_path, linhas)

    assert dados["saldo_anterior"] is None
    assert dados["saldo_atual"] is None
    assert "não fecham" in caplog.text
    assert len(dados["transacoes"]) == 1


def test_soma_dos_movimentos_bate_com_a_diferenca_dos_saldos(monkeypatch, tmp_path):
    # Propriedade: para movimentos gerados, anterior + Σ(sinal × valor) = atual
    tipos = [("Aplicacoes", 1), ("Resgates", -1), ("Rendimentos", 1)]
    movimentos: list[list[Any]] = [["30/04/2026", "Saldo Anterior", "10.000,00"]]
    saldo = 10000.0
    for i in range(30):
        historico, sinal = tipos[i % 3]
        valor = round(1.07 * (i + 1) ** 2, 2)
        saldo += sinal * valor
        movimentos.append([f"{i + 1:02d}/05/2026", historico, f"{valor:.2f}".replace(".", ",")])
    saldo_txt = f"{saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    linhas = _cdb("05/2026", movimentos, ["31/05/2026", "Saldo Atual", saldo_txt])

    dados = _ler(monkeypatch, tmp_path, linhas)

    assert dados["saldo_atual"] == pytest.approx(saldo)
    delta = sum(-m["valor"] if m["tipo"] == "RESGATE" else m["valor"] for m in dados["movimentos"])
    assert dados["saldo_anterior"] + delta == pytest.approx(dados["saldo_atual"], abs=0.01)


def test_poupanca_usa_coluna_saldo_e_ignora_resumo(monkeypatch, tmp_path):
    linhas: list[list[Any]] = [
        [""],
        ["Associado:", "IGREJA FICTICIA"],
        ["Cooperativa:", "0101"],
        ["Conta Corrente:", "12345-6"],
        [""],
        ["Extrato de Aplicação - Movimento Poupança"],
        ["Dados referentes ao período 05/2026 a 05/2026."],
        ["Produto: ", "", "POUPANCA TRADICIONAL"],
        ["Conta Poupança: ", "", "12345-6"],
        [""],
        ["Movimentação"],
        ["Data", "Histórico", "Valor (R$)", "Saldo"],
        ["30/04/2026", "SALDO ANTERIOR", "100,00", "100,00"],
        ["04/05/2026", "CAPITALIZ. REND. JR", "0,50", "100,50"],
        ["05/05/2026", "CRED. TRANSF. C/C", "20,00", "120,50"],
        ["20/05/2026", "DEB. TRANSF. C/C - MOBI", "120,50", "0,00"],
        ["31/05/2026", "SALDO ATUAL", "0,00", "0,00"],
        [""],
        ["Resumo por Período"],
        ["Aniversário", "Saldo Anterior", "Aplicações", "Resgates", "Rendimentos"],
        ["01", "206,72", "0,00", "208,11", "1,39"],
    ]

    dados = _ler(monkeypatch, tmp_path, linhas)

    assert dados["conta_id"] == "12345-6"
    assert dados["produto"] == "POUPANCA TRADICIONAL"
    assert [m["tipo"] for m in dados["movimentos"]] == ["RENDIMENTO", "APLICACAO", "RESGATE"]
    assert dados["saldo_anterior"] == 100.0
    assert dados["saldo_atual"] == 0.0
    assert dados["data_final"] == "31/05/2026"


def test_conta_sem_rotulo_usa_regex_generica(monkeypatch, tmp_path):
    linhas = _cdb("05/2026", MOVIMENTOS_MAIO)
    linhas[3] = ["Conta:", "AG 0101 / 54321-0"]

    dados = _ler(monkeypatch, tmp_path, linhas)

    assert dados["conta_id"] == "54321-0"


@pytest.mark.parametrize(
    ("aba", "titulo"),
    [
        ("Extrato Capital Social", "Qualquer título"),
        ("Relatorio", "Saldo e Extrato Capital Social"),
    ],
)
def test_capital_social_nao_suportado(monkeypatch, tmp_path, aba, titulo):
    linhas: list[list[Any]] = [
        ["Associado:", "IGREJA FICTICIA"],
        ["Cooperativa:", "0101"],
        ["Conta:", "12345-6"],
        [""],
        [titulo],
        ["Dados referentes ao período de 18/06/2025 a 18/06/2026."],
        ["Data", "Descrição", "Documento", "Valor (R$)", "Saldo (R$)"],
    ]

    with pytest.raises(ExtratoNaoSuportadoError) as excinfo:
        _ler(monkeypatch, tmp_path, linhas, aba)

    assert str(excinfo.value) == "Extrato de Capital Social ainda não é suportado. Retire este arquivo do lote."
    # A UI trata os erros de leitura como ValueError
    assert isinstance(excinfo.value, ValueError)
