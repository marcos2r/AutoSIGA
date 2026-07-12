import os
import pytest
from models.ofx_reader import OfxReader

def test_parse_ofx_sucesso():
    # Caminho para a fixture sample.ofx
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample.ofx")
    
    dados = OfxReader.parse_file(fixture_path)
    
    assert dados["conta_id"] == "12345-6"
    assert dados["moeda"].upper() == "BRL"
    assert dados["saldo_atual"] == 10450.75
    assert dados["data_inicial"] == "01/07/2026"
    assert dados["data_final"] == "10/07/2026"
    
    assert len(dados["transacoes"]) == 3
    
    # Valida uma das transações
    tx_resgate = dados["transacoes"][2]
    assert tx_resgate["valor"] == 50.25
    assert tx_resgate["descricao"] == "RESGATE AUTOMATICO"
    assert tx_resgate["data"] == "04/07/2026"

def test_parse_ofx_inexistente():
    with pytest.raises(ValueError) as excinfo:
        OfxReader.parse_file("caminho_inexistente_qualquer.ofx")
    assert "não é um extrato OFX válido ou está corrompido" in str(excinfo.value)

def test_parse_ofx_invalido(tmp_path):
    arquivo_invalido = tmp_path / "invalido.ofx"
    arquivo_invalido.write_text("SOU UM OFX TOTALMENTE INVALIDO", encoding="utf-8")
    
    with pytest.raises(ValueError) as excinfo:
        OfxReader.parse_file(str(arquivo_invalido))
    assert "não é um extrato OFX válido ou está corrompido" in str(excinfo.value)
