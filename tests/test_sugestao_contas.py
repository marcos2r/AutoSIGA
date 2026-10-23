"""Tabela de decisão da sugestão: tipo de extrato × candidatos × produto × localidade preferida."""

from controllers.catalogo_contas import Catalogo, ContaSiga
from controllers.sugestao_contas import ESCOLHA, NAO_ENCONTRADO, SUGERIDO, sugerir

ADM = "ADM - CENTRAL - SP"
DR = "DR - CENTRAL"
PIA = "PIA - CENTRAL"
CC_ADM = "123456"
CC_DR = "222222"
CC_PIA = "333333"
OFX_ADM = "0101000000123456"   # agência + zeros + CC, como no OFX da Sicredi


def _c(codigo, localidade, cc, finalidade, ativa=True):
    return ContaSiga(codigo, codigo[:3], localidade, "SICREDI", "101", cc, finalidade, ativa)


CATALOGO = Catalogo([
    _c("10130", ADM, CC_ADM, "CAPTAÇÃO"),
    _c("10396", ADM, CC_ADM, "APLICACAO"),
    _c("10315", ADM, CC_ADM, "POUPANÇA"),
    _c("10127", DR, CC_DR, "DR"),
    _c("10304", DR, CC_DR, "APLICACAO"),
    _c("10116", PIA, CC_PIA, "PIA"),
    _c("10303", PIA, CC_PIA, "APLICACAO"),
    _c("10399", PIA, CC_PIA, "ANTIGA", ativa=False),
], lido_em="2026-10-23T10:00:00", fonte="CTB00301")


def test_corrente_com_aplicacao_unica_vem_sugerida():
    s = sugerir(CATALOGO, "22222-2", aplicacao=False)
    assert s.status == SUGERIDO
    assert s.localidade == DR
    assert s.corrente.escolhida.codigo == "10127"
    assert s.aplicacao.escolhida.codigo == "10304"
    assert "CC igual" in s.motivo


def test_conta_inativa_nao_entra_na_disputa():
    s = sugerir(CATALOGO, CC_PIA, aplicacao=False)
    assert s.status == SUGERIDO
    assert s.aplicacao.escolhida.codigo == "10303"
    assert [c.codigo for c in s.aplicacao.opcoes] == ["10303"]


def test_corrente_com_duas_aplicacoes_sem_pista_pede_escolha():
    s = sugerir(CATALOGO, OFX_ADM, aplicacao=False)
    assert s.status == ESCOLHA
    assert s.corrente.escolhida.codigo == "10130"
    assert s.aplicacao.escolhida is None
    assert [c.codigo for c in s.aplicacao.opcoes] == ["10315", "10396"]
    assert s.localidade == ADM


def test_xls_poupanca_escolhe_a_conta_de_poupanca():
    s = sugerir(CATALOGO, "12345-6", aplicacao=True, produto="POUPANCA TRADICIONAL")
    assert s.status == SUGERIDO
    assert s.aplicacao.escolhida.codigo == "10315"
    # A outra continua disponível no combo
    assert [c.codigo for c in s.aplicacao.opcoes] == ["10315", "10396"]
    assert "POUPANCA" in s.motivo


def test_xls_sicredinvest_escolhe_a_aplicacao():
    s = sugerir(CATALOGO, "12345-6", aplicacao=True, produto="SICREDINVEST AUTOMATICO")
    assert s.status == SUGERIDO
    assert s.aplicacao.escolhida.codigo == "10396"
    assert s.corrente.opcoes == []


def test_xls_produto_sem_pista_pede_escolha():
    s = sugerir(CATALOGO, "12345-6", aplicacao=True, produto="RDC DIST. RESULTADOS")
    assert s.status == ESCOLHA
    assert s.aplicacao.escolhida is None


def test_localidade_ja_usada_desempata():
    cat = Catalogo([
        _c("10127", ADM, CC_DR, "DR"),
        _c("10127", DR, CC_DR, "DR"),
        _c("10304", DR, CC_DR, "APLICACAO"),
    ])
    sem_pista = sugerir(cat, CC_DR, aplicacao=False)
    assert sem_pista.status == ESCOLHA

    com_pista = sugerir(cat, CC_DR, aplicacao=False, localidade_preferida="DR - CENTRAL")
    assert com_pista.status == SUGERIDO
    assert com_pista.localidade == DR
    assert "localidade já usada" in com_pista.motivo


def test_conta_desconhecida_nao_e_encontrada():
    s = sugerir(CATALOGO, "999999", aplicacao=False)
    assert s.status == NAO_ENCONTRADO
    assert "Nenhuma conta corrente" in s.motivo


def test_corrente_sem_aplicacao_na_localidade():
    cat = Catalogo([_c("10130", ADM, CC_ADM, "CAPTAÇÃO"), _c("10303", PIA, CC_ADM, "APLICACAO")])
    s = sugerir(cat, CC_ADM, aplicacao=False)
    assert s.status == NAO_ENCONTRADO
    assert s.corrente.escolhida.codigo == "10130"
    assert s.aplicacao.opcoes == []


def test_catalogo_vazio_orienta_a_buscar_no_siga():
    s = sugerir(Catalogo(), CC_ADM, aplicacao=True)
    assert s.status == NAO_ENCONTRADO
    assert "Buscar no SIGA" in s.motivo


def test_motivo_cita_localidades_sem_acesso():
    cat = Catalogo([_c("10130", ADM, CC_ADM, "X")], localidades_sem_acesso=["PIA - CENTRAL"])
    s = sugerir(cat, "999999", aplicacao=True)
    assert "Sem acesso a: PIA - CENTRAL" in s.motivo


def test_extrato_de_corrente_nunca_recebe_103_na_corrente():
    # Só há uma 103 com a CC: o campo corrente não pode recebê-la (inversão impossível)
    cat = Catalogo([_c("10396", ADM, CC_ADM, "APLICACAO")])
    s = sugerir(cat, CC_ADM, aplicacao=False)
    assert s.status == NAO_ENCONTRADO
    assert s.corrente.escolhida is None
