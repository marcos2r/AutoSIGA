import pytest
from controllers.conciliador import Conciliador

def test_conciliar_ofx_vazio():
    assert Conciliador.conciliar([], [{"data": "12/05/2026", "entrada": "100,00"}]) == []

def test_conciliar_sem_transacoes_investimento():
    # Descrições que não batem com investimentos
    ofx_txs = [
        {"data": "12/05/2026", "valor": 100.00, "descricao": "COMPRA SUPERMERCADO"},
        {"data": "12/05/2026", "valor": -50.00, "descricao": "PIX ENVIADO"}
    ]
    # Siga vazio
    assert Conciliador.conciliar(ofx_txs, []) == []

def test_conciliar_sucesso_par_perfeito():
    ofx_txs = [
        {"data": "12/05/2026", "valor": 500.00, "descricao": "RESGATE AUTOMATICO"}
    ]
    siga_txs = [
        {"data": "12/05/2026", "entrada": "500,00", "saida": "-"}
    ]
    # Deve conciliar (retorna vazio pois não há pendências)
    assert Conciliador.conciliar(ofx_txs, siga_txs) == []

def test_conciliar_com_diferenca_um_centavo():
    ofx_txs = [
        {"data": "12/05/2026", "valor": 500.01, "descricao": "RESGATE AUTOMATICO"}
    ]
    siga_txs = [
        {"data": "12/05/2026", "entrada": "500,00", "saida": "-"}
    ]
    # Diferença de 1 centavo entra na tolerância, então concilia
    assert Conciliador.conciliar(ofx_txs, siga_txs) == []

def test_conciliar_com_diferenca_maior_que_um_centavo():
    ofx_txs = [
        {"data": "12/05/2026", "valor": 500.02, "descricao": "RESGATE AUTOMATICO"}
    ]
    siga_txs = [
        {"data": "12/05/2026", "entrada": "500,00", "saida": "-"}
    ]
    # Diferença de 2 centavos não concilia, retorna como pendência (a lançar)
    resultado = Conciliador.conciliar(ofx_txs, siga_txs)
    assert len(resultado) == 1
    assert resultado[0]["valor"] == 500.02

def test_conciliar_pendencia_nao_encontrada():
    ofx_txs = [
        {"data": "12/05/2026", "valor": 500.00, "descricao": "RESGATE AUTOMATICO"},
        {"data": "13/05/2026", "valor": -100.00, "descricao": "APLICACAO FINANCEIRA"}
    ]
    siga_txs = [
        {"data": "12/05/2026", "entrada": "500,00", "saida": "-"}
    ]
    # Apenas a aplicação de -100.00 no dia 13/05/2026 está pendente
    resultado = Conciliador.conciliar(ofx_txs, siga_txs)
    assert len(resultado) == 1
    assert resultado[0]["valor"] == -100.00
    assert resultado[0]["data"] == "13/05/2026"

def test_conciliar_conversao_valores_siga():
    ofx_txs = [
        {"data": "12/05/2026", "valor": -1500.50, "descricao": "APLICACAO AUTOMATICA"}
    ]
    # Formato brasileiro com pontos de milhar e vírgula decimal
    siga_txs = [
        {"data": "12/05/2026", "entrada": "-", "saida": "1.500,50"}
    ]
    assert Conciliador.conciliar(ofx_txs, siga_txs) == []
