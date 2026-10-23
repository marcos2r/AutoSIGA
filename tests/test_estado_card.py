import pytest

from controllers.catalogo_contas import Catalogo, ContaSiga
from controllers.estado_card import (
    CONFIRMADO,
    EDITADO,
    ESCOLHA,
    NAO_ENCONTRADO,
    PENDENTE,
    REVISAR,
    SUGERIDO,
    avaliar_card,
    checar_codigo,
    codigo_do_combo,
)

ADM = "ADM - CENTRAL - SP"
CATALOGO = Catalogo([
    ContaSiga("10130", "101", ADM, cc="123456"),
    ContaSiga("10396", "103", ADM, cc="123456"),
    ContaSiga("10116", "101", "PIA - CENTRAL", cc="333333"),
    ContaSiga("10199", "101", ADM, cc="999999", ativa=False),
], lido_em="2026-10-23T10:00:00")


def test_codigo_do_combo():
    assert codigo_do_combo("10130 · CAPTAÇÃO") == "10130"
    assert codigo_do_combo(" 10130 ") == "10130"
    assert codigo_do_combo("") == ""


@pytest.mark.parametrize("codigo, grupo, localidade, trecho", [
    ("10396", "101", ADM, "não é de conta corrente"),      # inversão corrente/aplicação
    ("10130", "103", ADM, "não é de aplicação"),
    ("101", "101", ADM, "não é de conta corrente"),         # só o grupo
    ("ABC", "101", ADM, "não é de conta corrente"),
    ("10155", "101", ADM, "não existe"),
    ("10199", "101", ADM, "não existe"),                    # inativa
    ("10116", "101", ADM, "é da localidade PIA - CENTRAL"),
])
def test_codigo_recusado(codigo, grupo, localidade, trecho):
    assert trecho in checar_codigo(CATALOGO, codigo, grupo, localidade)


def test_codigo_aceito_com_nome_curto_da_localidade():
    assert checar_codigo(CATALOGO, "10130", "101", "ADM - CENTRAL") is None


def test_sem_catalogo_confere_so_o_grupo():
    assert checar_codigo(Catalogo(), "10155", "101", ADM) is None
    assert checar_codigo(Catalogo(), "10396", "101", ADM) is not None


def test_localidade_sem_acesso_nao_e_conferida():
    cat = Catalogo(CATALOGO.contas, localidades_sem_acesso=["DR - CENTRAL"])
    assert checar_codigo(cat, "10127", "101", "DR - CENTRAL") is None


def _avaliar(**kw):
    base = dict(catalogo=CATALOGO, aplicacao=False, localidade=ADM, corrente="10130", aplic="10396",
                confirmado=False)
    base.update(kw)
    return avaliar_card(**base)


@pytest.mark.parametrize("kw, chave, valido", [
    (dict(confirmado=True), CONFIRMADO, True),
    (dict(confirmado=True, corrente="10155"), REVISAR, False),
    (dict(confirmado=True, aplic=""), PENDENTE, False),
    (dict(origem_sugestao=True, motivo_sugestao="CC igual"), SUGERIDO, False),
    (dict(), EDITADO, False),
    (dict(corrente="10396"), NAO_ENCONTRADO, False),
    (dict(localidade="CENTRAL"), NAO_ENCONTRADO, False),
    (dict(aplic="", tem_opcoes=True), ESCOLHA, False),
    (dict(aplic=""), NAO_ENCONTRADO, False),
    (dict(aplic="", catalogo=Catalogo()), PENDENTE, False),
    (dict(aplicacao=True, corrente="", confirmado=True), CONFIRMADO, True),
])
def test_tabela_de_estados(kw, chave, valido):
    estado = _avaliar(**kw)
    assert estado.chave == chave
    assert estado.valido is valido
    assert estado.texto  # todo estado tem ícone + palavra


def test_so_confirmado_libera_conciliacao():
    assert not _avaliar(origem_sugestao=True).valido
    assert _avaliar(confirmado=True).valido


def test_mensagem_de_codigo_invalido_explica_o_motivo():
    estado = _avaliar(corrente="10396")
    assert "não é de conta corrente" in estado.mensagem
