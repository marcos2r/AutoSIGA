import os
import pytest
from models.xls_reader import XlsReader

def test_parse_xls_sucesso():
    # Caminho para a fixture sample_sicredi.xls
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sicredi.xls")
    
    dados = XlsReader.parse_file(fixture_path)
    
    assert dados["banco"] == "748"
    assert dados["conta_id"] == "58308-2"
    assert dados["tipo_extrato"] == "APLICACAO"
    assert dados["produto"] == "SICREDINVEST AUTOMATICO"
    assert dados["data_inicial"] == "01/05/2026"
    assert dados["data_final"] == "30/05/2026"
    
    # Apenas a transação com histórico "RENDIMENTOS" é classificada como rendimento
    # O "RESGATE" é filtrado e ignorado
    assert len(dados["transacoes"]) == 1
    
    tx = dados["transacoes"][0]
    assert tx["data"] == "12/05/2026"
    assert tx["valor"] == 78.41
    assert tx["descricao"] == "RENDIMENTOS"
    assert tx["documento"] == "0"

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
