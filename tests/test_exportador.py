import os
import pytest
from controllers.exportador import Exportador

def test_gerar_txt_ofertas_vazio():
    success, validas, descartadas = Exportador.gerar_txt_ofertas([], "dummy_path.txt")
    assert not success
    assert validas == 0
    assert descartadas == 0

def test_gerar_txt_ofertas_descarte_negativos_e_palavras_bloqueadas(tmp_path):
    transacoes = [
        {"valor": -50.00, "descricao": "TARIFA BANCARIA", "data": "12/05/2026"},
        {"valor": 150.00, "descricao": "APLICACAO AUTOMATICA", "data": "12/05/2026"},
        {"valor": 300.00, "descricao": "TRANSFERENCIA RECEBIDA", "data": "13/05/2026"},
        {"valor": 200.00, "descricao": "OFERTA DE CULTO ESP", "data": "14/05/2026"}
    ]
    
    filepath = tmp_path / "ofertas_teste.txt"
    success, validas, descartadas = Exportador.gerar_txt_ofertas(transacoes, str(filepath))
    
    # -50.00 (negativo), APLICACAO (palavra bloqueada), TRANSFERENCIA (palavra bloqueada) -> descartados (3)
    # OFERTA DE CULTO ESP -> válida (1)
    assert success
    assert validas == 1
    assert descartadas == 3
    
    # Verifica o conteúdo do arquivo
    content = filepath.read_text(encoding='utf-8')
    assert "14/05/2026;OFERTA DE CULTO ESP;200,00" in content

def test_gerar_excel_lote(tmp_path):
    telemetria = {
        "total_contas": 2,
        "ofx_itens": 10,
        "siga_itens": 8,
        "injecoes": 2,
        "pendentes": 1,
        "volume_financeiro": 1500.50
    }
    
    dados_lote = [
        {
            "tipo_adm": "ADMINISTRACAO",
            "nome_adm": "CONTA PRINCIPAL",
            "tipo_extrato": "CONTA CORRENTE",
            "conta_id": "12345-6",
            "transacoes": [{"valor": 100.00}],
            "extrato_siga": [{"valor": 100.00}],
            "pendentes": []
        }
    ]
    
    filepath = tmp_path / "lote_resumo.xlsx"
    Exportador.gerar_excel_lote(telemetria, dados_lote, str(filepath))
    
    assert filepath.exists()
    assert filepath.stat().st_size > 0
