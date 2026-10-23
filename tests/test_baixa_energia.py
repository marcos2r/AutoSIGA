"""Decisão de baixa das faturas de energia pelo extrato (dados fictícios)."""

import pytest

from controllers.baixa_energia import (
    APROVADO,
    BAIXAR,
    EMPATE,
    ESTORNADO,
    JA_BAIXADA,
    LANCADO,
    PAGO,
    SEM_FATURA,
    SEM_PROVISAO,
    VALOR_DIFERENTE,
    ProvisaoSiga,
    decidir_baixas,
    ler_debitos,
    resumo_decisao,
)
from models.indice_faturas_energia import FaturaEnergia

COD_A = "00012345678"
COD_B = "00087654321"


def _debito(data, valor, codigo=COD_A):
    return {"data": data, "valor": -valor,
            "descricao": f"DEBITO CONVENIOS-ENERGI 70 ID {codigo} ENERGISA MS 00000000000100"}


def _fatura(numero, valor, vencimento="26/08/2026", codigo=COD_A, uc="1.234.567.051-00"):
    return FaturaEnergia(numero, uc, valor, vencimento, codigo)


def _prov(numero, valor, status=LANCADO, guid=None):
    return ProvisaoSiga(numero, valor, status, guid or f"G-{numero}-{status}")


INDICE = {
    COD_A: [_fatura("017000001", 133.48), _fatura("017000000", 120.00, vencimento="26/07/2026")],
    COD_B: [_fatura("017000002", 133.48, codigo=COD_B, uc="9.876.543.051-00")],
}


def _acoes(decisoes):
    return [(d.acao, d.provisao.numero if d.provisao else None) for d in decisoes]


def test_ler_debitos_ignora_outros_movimentos():
    transacoes = [_debito("26/08/2026", 133.48), {"data": "26/08/2026", "valor": -50.0, "descricao": "PAGAMENTO PIX"}]
    debitos, estornos = ler_debitos(transacoes)
    assert [(d.data, d.valor, d.codigo) for d in debitos] == [("26/08/2026", 133.48, COD_A)]
    assert estornos == []


def test_baixa_quando_codigo_valor_e_numero_apontam_uma_provisao():
    decisoes = decidir_baixas([_debito("26/08/2026", 133.48)], INDICE, [_prov("017000001", 133.48)])

    assert _acoes(decisoes) == [(BAIXAR, "017000001")]
    assert decisoes[0].precisa_aprovar


def test_provisao_ja_aprovada_so_precisa_baixar():
    decisoes = decidir_baixas([_debito("26/08/2026", 133.48)], INDICE, [_prov("017000001", 133.48, APROVADO)])
    assert decisoes[0].acao == BAIXAR and not decisoes[0].precisa_aprovar


def test_mesmo_valor_em_duas_ucs_e_o_codigo_que_desempata():
    provisoes = [_prov("017000001", 133.48), _prov("017000002", 133.48)]

    decisoes = decidir_baixas([_debito("26/08/2026", 133.48, COD_B), _debito("26/08/2026", 133.48)],
                              INDICE, provisoes)

    assert _acoes(decisoes) == [(BAIXAR, "017000002"), (BAIXAR, "017000001")]


def test_numero_sem_zeros_a_esquerda_no_siga_tambem_casa():
    decisoes = decidir_baixas([_debito("26/08/2026", 133.48)], INDICE, [_prov("17000001", 133.48)])
    assert decisoes[0].acao == BAIXAR


@pytest.mark.parametrize("debito, provisoes, acao", [
    (_debito("26/08/2026", 133.48, "00000000001"), [], SEM_FATURA),                  # código desconhecido
    (_debito("26/12/2026", 133.48), [], SEM_FATURA),                                 # nenhum vencimento perto
    (_debito("26/08/2026", 140.15), [_prov("017000001", 133.48)], VALOR_DIFERENTE),  # multa ou juros
    (_debito("26/08/2026", 133.48), [], SEM_PROVISAO),                               # fatura não lançada
    (_debito("26/08/2026", 133.48), [_prov("017000001", 133.48, PAGO)], JA_BAIXADA),
    (_debito("26/08/2026", 133.48), [_prov("017000001", 150.00)], VALOR_DIFERENTE),  # provisão com outro valor
    (_debito("26/08/2026", 133.48), [_prov("017000001", 133.48, guid="X"),
                                     _prov("017000001", 133.48, APROVADO, guid="Y")], EMPATE),
])
def test_casos_em_que_nada_e_baixado(debito, provisoes, acao):
    decisoes = decidir_baixas([debito], INDICE, provisoes)
    assert decisoes[0].acao == acao
    assert decisoes[0].motivo


def test_duas_faturas_da_mesma_uc_com_o_mesmo_valor_e_empate():
    indice = {COD_A: [_fatura("017000001", 133.48, "26/08/2026"), _fatura("017000009", 133.48, "22/08/2026")]}
    decisoes = decidir_baixas([_debito("26/08/2026", 133.48)], indice, [_prov("017000001", 133.48)])
    assert decisoes[0].acao == EMPATE


def test_vencimento_no_limite_da_janela():
    # 40 dias antes do débito ainda vale; 41 não
    indice = {COD_A: [_fatura("017000001", 133.48, "17/07/2026")]}
    assert decidir_baixas([_debito("26/08/2026", 133.48)], indice, [_prov("017000001", 133.48)])[0].acao == BAIXAR
    indice = {COD_A: [_fatura("017000001", 133.48, "16/07/2026")]}
    assert decidir_baixas([_debito("26/08/2026", 133.48)], indice, [_prov("017000001", 133.48)])[0].acao == SEM_FATURA


def test_debito_estornado_nao_e_baixado():
    estorno = dict(_debito("27/08/2026", 133.48), valor=133.48)

    decisoes = decidir_baixas([_debito("26/08/2026", 133.48), estorno], INDICE, [_prov("017000001", 133.48)])

    assert [d.acao for d in decisoes] == [ESTORNADO]


def test_debito_repetido_nao_baixa_a_mesma_provisao_duas_vezes():
    decisoes = decidir_baixas([_debito("26/08/2026", 133.48), _debito("26/08/2026", 133.48)],
                              INDICE, [_prov("017000001", 133.48)])
    assert [d.acao for d in decisoes] == [BAIXAR, VALOR_DIFERENTE]


def test_resumo_da_decisao():
    baixar = decidir_baixas([_debito("26/08/2026", 133.48)], INDICE, [_prov("017000001", 133.48)])[0]
    assert resumo_decisao(baixar) == (
        "ok", "⚡ 26/08/2026 · R$ 133,48 · aprovar e baixar fatura 017000001 da UC 1.234.567.051-00")
    multa = decidir_baixas([_debito("26/08/2026", 140.15)], INDICE, [_prov("017000001", 133.48)])[0]
    nivel, texto = resumo_decisao(multa)
    assert nivel == "alerta" and "possível multa ou juros" in texto
