import pytest

from controllers.catalogo_contas import (
    Catalogo,
    ContaSiga,
    cc_bate,
    consolidar,
    escolher_opcao_conta,
    ler_linha_plano_contas,
    ler_rotulo_tesouraria,
    mascarar_cc,
    mesma_localidade,
    separar_localidade,
    so_digitos,
)

# Dados sintéticos: nenhuma conta real

@pytest.mark.parametrize("rotulo, agencia, cc, finalidade", [
    ("10130 - SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO", "101", "123456", "CAPTAÇÃO"),
    ("10130 - SICREDI - AG:0101 CC:12345-6 CAPTAÇÃO", "101", "123456", "CAPTAÇÃO"),
    ("10130 - SICREDI - AG: 0101  CC: 123456  CAPTAÇÃO", "101", "123456", "CAPTAÇÃO"),
    ("10396 - SICREDI - AG: 0101 CC: 12345-6 APLICACAO", "101", "123456", "APLICACAO"),
    ("10315 - SICREDI - AG: 0101 CC: 12.345-6 - POUPANÇA", "101", "123456", "POUPANÇA"),
    ("10140 - SICREDI - AG: 0101 CC: CONTA CAPITAL", "101", "", ""),
])
def test_rotulo_tesouraria_tolera_formatos(rotulo, agencia, cc, finalidade):
    conta = ler_rotulo_tesouraria(rotulo, "ADM - CENTRAL - SP")
    assert conta is not None
    assert conta.codigo == rotulo[:5]
    assert conta.grupo == rotulo[:3]
    assert conta.banco == "SICREDI"
    assert conta.agencia == agencia
    assert conta.cc == cc
    assert conta.finalidade == finalidade
    assert conta.localidade == "ADM - CENTRAL - SP"
    assert conta.ativa


@pytest.mark.parametrize("rotulo", [
    "1000 - CAIXA GERAL",           # caixa, fora dos grupos bancários
    "20010 - FORNECEDORES",         # outro grupo
    "Selecione...",                 # opção vazia do select
    "",
])
def test_rotulo_que_nao_e_conta_bancaria_e_ignorado(rotulo):
    assert ler_rotulo_tesouraria(rotulo, "ADM - CENTRAL - SP") is None


def test_rotulo_do_optgroup_inativo_fica_inativo():
    conta = ler_rotulo_tesouraria("10199 - SICREDI - AG: 0101 CC: 99999-9 ANTIGA", "DR - CENTRAL", inativa=True)
    assert conta is not None and not conta.ativa


def test_linha_do_plano_de_contas():
    conta = ler_linha_plano_contas("101 30", "SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO", "ADM - CENTRAL - SP", "Ativo")
    assert conta == ContaSiga("10130", "101", "ADM - CENTRAL - SP", "SICREDI", "101", "123456", "CAPTAÇÃO", True)


@pytest.mark.parametrize("codigo, localidade", [
    ("102 01", "ADM - CENTRAL - SP"),        # grupo fora de 101/103
    ("101 30", "ADM, SET, PIA, DR"),          # conta genérica, várias localidades
    ("", "ADM - CENTRAL - SP"),
])
def test_linha_do_plano_fora_do_escopo_e_ignorada(codigo, localidade):
    assert ler_linha_plano_contas(codigo, "SICREDI - AG: 0101 CC: 12345-6 X", localidade) is None


def test_linha_do_plano_inativa():
    conta = ler_linha_plano_contas("103 99", "SICREDI CC: 12345-6 X", "PIA - CENTRAL", "Inativo")
    assert conta is not None and not conta.ativa


@pytest.mark.parametrize("catalogo, extrato, esperado", [
    ("123456", "12345-6", True),                 # XLS com hífen
    ("123456", "0101000000123456", True),        # OFX: agência + zeros + CC
    ("123456", "000123456", True),               # zeros à esquerda
    ("123456", "123457", False),                 # DV diferente
    ("123456", "23456", True),                   # extrato sem o primeiro dígito
    ("123456", "456", False),                    # trecho curto demais
    ("", "123456", False),
])
def test_cc_bate(catalogo, extrato, esperado):
    assert cc_bate(catalogo, extrato) is esperado


@pytest.mark.parametrize("formatado", ["12345-6", " 12.345-6 ", "0012345 6", "123456"])
def test_formatacao_da_cc_nao_muda_o_resultado(formatado):
    assert so_digitos(formatado) == "123456"
    assert cc_bate("12345-6", formatado)


def test_separar_localidade():
    assert separar_localidade("ADM - CENTRAL - SP") == ("ADM", "CENTRAL - SP")
    assert separar_localidade("dr  -  central") == ("DR", "CENTRAL")
    assert separar_localidade("CENTRAL") == ("", "CENTRAL")


@pytest.mark.parametrize("a, b, esperado", [
    ("ADM - CENTRAL - SP", "ADM - CENTRAL - SP", True),
    ("ADM - CENTRAL", "ADM - CENTRAL - SP", True),          # nome curto dos mapeamentos antigos
    ("ADM - SÃO PAULO", "adm - sao paulo", True),           # acento e caixa
    ("DR - CENTRAL", "ADM - CENTRAL - SP", False),
    ("ADM - CENTRAL", "ADM - CENTRALINA", False),
    ("", "ADM - CENTRAL", False),
])
def test_mesma_localidade(a, b, esperado):
    assert mesma_localidade(a, b) is esperado


def _conta(codigo, localidade, cc="123456", finalidade="X"):
    return ContaSiga(codigo, codigo[:3], localidade, "SICREDI", "101", cc, finalidade)


def test_consolidar_mantem_a_localidade_dona_da_conta_repetida():
    # A ADM também lista a corrente da DR; a DR tem a aplicação da mesma CC
    lidas = [
        _conta("10130", "ADM - CENTRAL - SP", cc="111111"),
        _conta("10127", "ADM - CENTRAL - SP", cc="222222"),
        _conta("10127", "DR - CENTRAL", cc="222222"),
        _conta("10304", "DR - CENTRAL", cc="222222"),
    ]
    resultado = consolidar(lidas)
    assert [(c.codigo, c.localidade) for c in resultado] == [
        ("10130", "ADM - CENTRAL - SP"), ("10127", "DR - CENTRAL"), ("10304", "DR - CENTRAL")]


def test_consolidar_sem_desempate_mantem_as_duas():
    lidas = [_conta("10127", "ADM - CENTRAL - SP"), _conta("10127", "DR - CENTRAL")]
    assert len(consolidar(lidas)) == 2


def test_catalogo_filtra_por_grupo_e_localidade():
    cat = Catalogo([
        _conta("10130", "ADM - CENTRAL - SP"),
        _conta("10396", "ADM - CENTRAL - SP"),
        _conta("10116", "PIA - CENTRAL"),
        ContaSiga("10199", "101", "ADM - CENTRAL - SP", ativa=False),
    ])
    assert [c.codigo for c in cat.contas_de("101")] == ["10130", "10116"]
    assert [c.codigo for c in cat.contas_de("101", "ADM - CENTRAL")] == ["10130"]
    assert cat.localidades() == ["ADM - CENTRAL - SP", "PIA - CENTRAL"]
    assert cat.buscar("10199") is None


def test_conta_ida_e_volta_pelo_dict():
    conta = _conta("10396", "ADM - CENTRAL - SP", finalidade="APLICACAO")
    assert ContaSiga.de_dict(conta.para_dict()) == conta
    assert conta.rotulo_curto == "10396 · APLICACAO"


def test_mascarar_cc_nao_expoe_o_numero():
    assert mascarar_cc("12345-6") == "12xxx6"
    assert mascarar_cc("12") == "xx"


def test_grade_do_plano_localiza_colunas_pelo_titulo():
    from controllers.catalogo_contas import ler_grade_plano_contas
    cabecalho = ["Status", "Localidade", "Nome", "Cód. Reduzido"]
    linhas = [["Ativo", "PIA - CENTRAL", "SICREDI CC: 33333-3 X", "101 16"],
              ["Nenhum registro encontrado"]]
    contas = ler_grade_plano_contas(cabecalho, linhas)
    assert [(c.codigo, c.localidade, c.cc) for c in contas] == [("10116", "PIA - CENTRAL", "333333")]
    assert ler_grade_plano_contas(["Nome"], linhas) == []


@pytest.mark.parametrize("codigo, esperado", [
    ("10130", "a"),        # código exato
    (" 10130 ", "a"),      # espaços em volta do código do card
    ("1013", None),        # trecho de um código maior
    ("110130", "c"),       # código que contém outro
    ("10199", None),       # só existe no INATIVO
    ("", None),
])
def test_escolher_opcao_conta_compara_o_codigo_inteiro(codigo, esperado):
    opcoes = [
        {"texto": "10130 - SICREDI - AG: 0101 CC: 12345-6", "valor": "a", "inativa": False},
        {"texto": "10199 - SICREDI - AG: 0101 CC: 99999-9", "valor": "b", "inativa": True},
        {"texto": " 110130 -SICREDI - AG: 0101 CC: 22222-2", "valor": "c", "inativa": False},
    ]
    assert escolher_opcao_conta(opcoes, codigo) == esperado


def test_escolher_opcao_conta_sem_opcoes():
    assert escolher_opcao_conta([], "10130") is None
