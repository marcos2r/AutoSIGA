"""Testes unitários para extratos e relatórios PIX do Sicoob (.xlsx e .xls)."""

from typing import Any

import openpyxl
import pytest
from test_xls_reader import _ler

from controllers.catalogo_contas import mesmo_extrato
from controllers.exportador import Exportador
from controllers.prova_real import movimentos_do_banco
from models.xls_reader import XlsReader
from models.xls_sicoob import montar_historico_sicoob


def _extrato_sicoob(saldo_anterior: float = 70325.43, saldo_dia_30: float = 74297.97) -> list[list[Any]]:
    """Extrato de conta corrente no layout real do Sicoob (dias em ordem decrescente)."""
    return [
        ["EXTRATO CONTA CORRENTE", "", "", "", ""],
        ["DATA", "DOCUMENTO", "HISTÓRICO", "INFORMAÇÕES COMPLEMENTARES", "VALOR"],
        ["30/10/2026", "20    ", "DEPOSITO EM DINHEIRO AG", "CPF: 111.222.333-44\nENVELOPE: 1208508398", 3000.0],
        [
            "30/10/2026",
            "Pix",
            "PIX RECEBIDO - OUTRA IF",
            "Recebimento Pix\nMaria da Silva\n***.771.821-**\nOferta",
            972.54,
        ],
        ["30/10/2026", "", "SALDO DO DIA", "", saldo_dia_30],
        [
            "14/10/2026",
            "8387803",
            "DÉB.TRANSF.CONTAS MESMA TITULARIDADE",
            "FAV.: CONGREGACAO CRISTA NO BRASIL\nColetas dinheiro",
            -1000.0,
        ],
        ["14/10/2026", "", "SALDO DO DIA", "", 70325.43],
        ["01/10/2026", "376863", "CRÉD.TED-STR", "JOAO PEREIRA\n123.456.789-00\nCODIGO TED: T109", 650.0],
        ["01/10/2026", "Pix", "PIX RECEBIDO - OUTRA IF", "Recebimento Pix\nJose Santos\n***.242.061-**", 350.0],
        ["01/10/2026", "", "SALDO DO DIA", "", 71325.43],
        ["30/09/2026", "", "SALDO BLOQUEADO ANTERIOR", "", 0],
        ["30/09/2026", "", "SALDO ANTERIOR", "", saldo_anterior],
    ]


def _relatorio_pix_sicoob(valor_total: str = "R$\xa01.385,00", qtd: int = 3) -> list[list[Any]]:
    """Relatório de recebimentos PIX no layout do SISBR / Sicoob."""
    return [
        ["SICOOB"],
        ["SICOOB - SISTEMA DE COOPERATIVAS DE CRÉDITO DO BRASIL"],
        ["SISBR - SISTEMA DE INFORMÁTICA DO SICOOB"],
        ["Movimentação - Recebimentos"],
        [""],
        ["Data/Hora de emissão: 02/11/2026 09:07:43"],
        ["Cooperativa: 3209", "", "Conta Corrente: 601.134-9 - CONGREGACAO CRISTA NO BRASIL"],
        ["Período: 01/10/2026 até 31/10/2026", "", "Tipo de movimentação: Recebimentos"],
        [""],
        ["EXTRATO PIX"],
        ["Data Movimento", "Histórico", "Pagador", "CPF/CNPJ do Pagador", "Instituição", "Valor"],
        [
            "01/10/2026",
            "Recebimento - Pix copia e cola",
            "Fulano de Tal",
            "***.111.222-**",
            "COOP SICREDI",
            "R$\xa01.200,00",
        ],
        [
            "02/10/2026",
            "Recebimento - Pix via chave",
            "Beltrano Silva",
            "***.333.444-**",
            "BCO DO BRASIL S.A.",
            "R$\xa0185,00",
        ],
        [
            "03/10/2026",
            "Recebimento - Pix via manual",
            "Ciclano Souza",
            "***.555.666-**",
            "CAIXA ECONOMICA FEDERAL",
            "R$\xa00,00",
        ],
        [""],
        ["Resumo"],
        [f"Valor total: {valor_total}"],
        [f"Quantidade de registros: {qtd}"],
        ["Ouvidoria Bancoob: 08007250996"],
    ]


def test_extrato_conta_corrente_sicoob_xlsx_real(tmp_path):
    """Abre um arquivo .xlsx real (via openpyxl) com o layout de conta corrente do Sicoob."""
    caminho = tmp_path / "extrato-conta-corrente_202610_20261103150803.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LANÇAMENTOS"
    for linha in _extrato_sicoob():
        ws.append(linha)
    wb.save(caminho)

    dados = XlsReader.parse_file(str(caminho))

    assert dados["banco"] == "756"
    assert dados["conta_id"] == "SICOOB"
    assert dados["data_inicial"] == "01/10/2026"
    assert dados["data_final"] == "30/10/2026"
    assert dados["saldo_atual"] == 74297.97
    assert dados["data_saldo"] == "30/10/2026"

    # Os dias vêm invertidos na planilha, mas saem em ordem cronológica crescente
    assert [(t["data"], t["valor"], t["tipo"]) for t in dados["transacoes"]] == [
        ("01/10/2026", 650.0, "credit"),
        ("01/10/2026", 350.0, "credit"),
        ("14/10/2026", -1000.0, "debit"),
        ("30/10/2026", 3000.0, "credit"),
        ("30/10/2026", 972.54, "credit"),
    ]
    # Descrição guarda só o HISTÓRICO; o histórico completo junta o nome sem quebras de linha
    assert dados["transacoes"][0]["descricao"] == "CRÉD.TED-STR"
    assert dados["transacoes"][0]["historico"] == "CRÉD.TED-STR - JOAO PEREIRA"
    assert dados["transacoes"][1]["descricao"] == "PIX RECEBIDO - OUTRA IF"
    assert dados["transacoes"][1]["historico"] == "PIX RECEBIDO - OUTRA IF - Recebimento Pix Jose Santos"
    assert "\n" not in dados["transacoes"][4]["historico"]


def test_extrato_sicoob_extrai_conta_do_nome_do_arquivo_quando_presente(tmp_path):
    caminho = tmp_path / "extrato-conta-corrente_601.134-9_202610_20261103150803.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for linha in _extrato_sicoob():
        ws.append(linha)
    wb.save(caminho)

    dados = XlsReader.parse_file(str(caminho))

    assert dados["conta_id"] == "601.134-9"


def test_extrato_sicoob_saldo_divergente_fica_none(monkeypatch, tmp_path):
    dados = _ler(monkeypatch, tmp_path, _extrato_sicoob(saldo_anterior=50000.0), aba="LANÇAMENTOS")

    assert dados["saldo_atual"] is None
    assert dados["data_saldo"] is None
    assert len(dados["transacoes"]) == 5


def test_extrato_sicoob_filtra_ofertas_e_bloqueia_transf_e_congregacao(monkeypatch, tmp_path):
    linhas = _extrato_sicoob()
    # Simula transferência recebida ("TRANSF."), PIX de outra Administração e TED da Congregação (com acento)
    linhas.insert(3, ["30/10/2026", "99", "CRÉD.TRANSF.CONTAS MESMA TITULARIDADE", "FAV.: CCB", 500.0])
    linhas.insert(
        4,
        [
            "30/10/2026",
            "Pix",
            "PIX RECEBIDO - OUTRA IF",
            "Recebimento Pix\nCONGREGACAO CRISTA NO BRASIL\n03.573.250 0001-09\nRepasse RRM",
            1500.0,
        ],
    )
    linhas.insert(5, ["30/10/2026", "100", "CRÉD.TED-STR", "Congregação Cristã no Brasil", 800.0])
    dados = _ler(monkeypatch, tmp_path, linhas, aba="LANÇAMENTOS")

    ofertas, descartadas = Exportador.filtrar_ofertas(dados["transacoes"])

    # Ficam apenas os 2 PIX de irmãos e a TED de pessoa física; depósito, débito, TRANSF e Congregação saem
    assert [t["valor"] for t in ofertas] == [650.0, 350.0, 972.54]
    assert descartadas == 5


def test_relatorio_pix_sicoob_ignora_pix_da_congregacao_nas_ofertas(monkeypatch, tmp_path):
    linhas = _relatorio_pix_sicoob(valor_total="R$\xa03.385,00", qtd=4)
    linhas.insert(
        14,
        [
            "04/10/2026",
            "Recebimento - Pix via chave",
            "CONGREGACAO CRISTA NO BRASIL",
            "03.573.250/0001-09",
            "COOP SICREDI",
            "R$\xa02.000,00",
        ],
    )
    dados = _ler(monkeypatch, tmp_path, linhas, aba="Extrato Pix")

    ofertas, descartadas = Exportador.filtrar_ofertas(dados["transacoes"])

    assert [t["valor"] for t in ofertas] == [1200.0, 185.0]
    assert descartadas == 2


def test_relatorio_pix_sicoob_le_cabecalho_e_valida_resumo(monkeypatch, tmp_path):
    dados = _ler(monkeypatch, tmp_path, _relatorio_pix_sicoob(), aba="Extrato Pix")

    assert dados["banco"] == "756"
    assert dados["conta_id"] == "601.134-9"
    assert (dados["data_inicial"], dados["data_final"]) == ("01/10/2026", "31/10/2026")
    assert dados["saldo_atual"] is None
    assert dados["movimentos_completos"] is False
    # Relatório parcial de PIX não pode apontar falsas sobras na prova real da TES01701
    assert movimentos_do_banco(dados) is None
    assert [(t["data"], t["valor"], t["historico"]) for t in dados["transacoes"]] == [
        ("01/10/2026", 1200.0, "Recebimento - Pix copia e cola - Fulano de Tal"),
        ("02/10/2026", 185.0, "Recebimento - Pix via chave - Beltrano Silva"),
        ("03/10/2026", 0.0, "Recebimento - Pix via manual - Ciclano Souza"),
    ]


def test_relatorio_pix_sicoob_recusa_quando_resumo_diverge(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="Soma dos recebimentos PIX diverge"):
        _ler(monkeypatch, tmp_path, _relatorio_pix_sicoob(valor_total="R$ 9.999,00"), aba="Extrato Pix")

    with pytest.raises(ValueError, match="Quantidade de registros"):
        _ler(monkeypatch, tmp_path, _relatorio_pix_sicoob(qtd=99), aba="Extrato Pix")


def test_mesmo_extrato_distingue_contas_sem_numero_e_prioriza_ofx_e_extrato_completo(monkeypatch, tmp_path):
    from ui.lote_extratos import _herdar_conta_id, _prioridade_extrato

    ext_a = _ler(monkeypatch, tmp_path, _extrato_sicoob(), aba="LANÇAMENTOS")
    ext_b = _ler(monkeypatch, tmp_path, _extrato_sicoob(saldo_anterior=10.0, saldo_dia_30=4032.54), aba="LANÇAMENTOS")
    rel_pix_1 = _ler(monkeypatch, tmp_path, _relatorio_pix_sicoob(), aba="Extrato Pix")
    rel_pix_2 = _ler(monkeypatch, tmp_path, _relatorio_pix_sicoob(), aba="Extrato Pix")

    # Mesmo extrato sem número de conta carregado duas vezes é duplicado; outra conta (outro saldo) não é
    assert mesmo_extrato(ext_a, dict(ext_a))
    assert not mesmo_extrato(ext_a, ext_b)
    # Relatório PIX detalhado.xlsx e sintetico.xls da mesma conta e período são duplicados entre si
    assert mesmo_extrato(rel_pix_1, rel_pix_2)

    # OFX do Sicoob (com conta e data final 31/10) casa com a planilha .xlsx da mesma conta (sem número e data 30/10)
    ofx_mesma_conta = dict(ext_a, conta_id="601134-9", data_final="31/10/2026", caminho_arquivo="sicoob.ofx")
    assert mesmo_extrato(ofx_mesma_conta, ext_a)
    assert not mesmo_extrato(ofx_mesma_conta, ext_b)

    # OFX ou extrato completo da mesma conta (601.134-9) também absorve o Relatório PIX parcial da mesma conta
    assert mesmo_extrato(ofx_mesma_conta, rel_pix_1)
    assert not mesmo_extrato(dict(ofx_mesma_conta, conta_id="7000733-0"), rel_pix_1)

    # Sem número de conta na planilha .xlsx ('SICOOB'), só casa com o Relatório PIX se os PIX pertencerem ao extrato
    assert not mesmo_extrato(ext_a, rel_pix_1)
    rel_pix_do_ext_a = dict(
        rel_pix_1,
        transacoes=[
            {"data": "01/10/2026", "valor": 350.0, "tipo": "credit", "descricao": "Pix", "historico": "Pix"},
            {"data": "30/10/2026", "valor": 972.54, "tipo": "credit", "descricao": "Pix", "historico": "Pix"},
        ],
    )
    assert mesmo_extrato(ext_a, rel_pix_do_ext_a)

    # Prioridade: OFX (0) > planilha completa (1) > relatório PIX parcial (2), herdando o número da conta quando faltar
    ext_a["caminho_arquivo"] = "extrato.xlsx"
    rel_pix_do_ext_a["caminho_arquivo"] = "detalhado.xlsx"
    assert _prioridade_extrato(ofx_mesma_conta) < _prioridade_extrato(ext_a) < _prioridade_extrato(rel_pix_do_ext_a)
    _herdar_conta_id(ext_a, rel_pix_do_ext_a)
    assert ext_a["conta_id"] == "601.134-9"


def test_montar_historico_sicoob_higieniza_quebras_e_ponto_e_virgula():
    assert (
        montar_historico_sicoob("PIX RECEBIDO - OUTRA IF", "Recebimento Pix\nFulano; Silva\n***.111.222-**")
        == "PIX RECEBIDO - OUTRA IF - Recebimento Pix Fulano, Silva"
    )
    assert (
        montar_historico_sicoob("DEPOSITO EM DINHEIRO AG", "CPF: 123\nENVELOPE: 456")
        == "DEPOSITO EM DINHEIRO AG - CPF: 123 - ENVELOPE: 456"
    )
    assert montar_historico_sicoob("TED INTERNET", "") == "TED INTERNET"
