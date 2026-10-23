"""Prova real: saldo do banco × SIGA e lançamentos do SIGA sem par no extrato."""

import pytest

from controllers.prova_real import (
    CONFERE,
    DIVERGE,
    NAO_CONFERIDO,
    conferir_saldo,
    movimentos_do_banco,
    normalizar_linhas_siga,
    sobras_no_siga,
    valor_br,
)


def _linha(data, entrada="-", saida="-", historico=""):
    return {"data": data, "entrada": entrada, "saida": saida, "historico": historico, "saldo": ""}


@pytest.mark.parametrize("texto, esperado", [
    ("10.977,40", 10977.40), ("-27,50", -27.50), ("1,00", 1.0), ("-", 0.0), ("", 0.0),
    (None, 0.0), ("abc", None),
])
def test_valor_br(texto, esperado):
    assert valor_br(texto) == esperado


@pytest.mark.parametrize("banco, siga, status, diferenca", [
    (1.00, 1.00, CONFERE, 0.0),
    (1.00, 1.01, CONFERE, 0.0),       # limite da tolerância
    (1.00, 1.02, DIVERGE, 0.02),
    (78772.25, 78730.15, DIVERGE, -42.10),
    (0.0, 0.0, CONFERE, 0.0),
])
def test_conferir_saldo(banco, siga, status, diferenca):
    resultado = conferir_saldo(banco, siga)
    assert resultado.status == status
    assert resultado.diferenca == pytest.approx(diferenca)


@pytest.mark.parametrize("banco, siga", [(None, 1.0), (1.0, None)])
def test_saldo_ausente_nao_e_conferido(banco, siga):
    resultado = conferir_saldo(banco, siga)
    assert resultado.status == NAO_CONFERIDO
    assert resultado.motivo


def test_normalizar_ignora_saldo_anterior_e_da_sinal():
    linhas = [_linha("-", historico="Saldo Anterior"),
              _linha("04/05/2026", saida="20.582,25"),
              _linha("04/05/2026", entrada="6,44"),
              _linha("05/05/2026", saida="-150,00")]   # sinal já na coluna Saída

    movs = normalizar_linhas_siga(linhas)

    assert [(m.data, m.valor) for m in movs] == [
        ("04/05/2026", -20582.25), ("04/05/2026", 6.44), ("05/05/2026", -150.0)]


def test_sem_sobras_quando_tudo_tem_par():
    banco = [("04/05/2026", -27.5), ("12/05/2026", 4000.0)]
    siga = [_linha("04/05/2026", saida="27,50"), _linha("12/05/2026", entrada="4.000,00")]
    assert sobras_no_siga(banco, siga) == []


def test_lancamento_duplicado_no_siga_vira_uma_sobra():
    banco = [("04/05/2026", -27.5)]
    siga = [_linha("04/05/2026", saida="27,50"), _linha("04/05/2026", saida="27,50", historico="DUPLICADO")]

    sobras = sobras_no_siga(banco, siga)

    assert [(s.data, s.valor, s.historico) for s in sobras] == [("04/05/2026", -27.5, "DUPLICADO")]


def test_valor_digitado_errado_vira_sobra():
    sobras = sobras_no_siga([("04/05/2026", -27.5)], [_linha("04/05/2026", saida="275,00")])
    assert [s.valor for s in sobras] == [-275.0]


def test_data_diferente_nao_pareia():
    sobras = sobras_no_siga([("04/05/2026", -27.5)], [_linha("05/05/2026", saida="27,50")])
    assert len(sobras) == 1


def test_movimentos_do_ofx_sao_todas_as_transacoes():
    dados = {"tipo_extrato": "CORRENTE", "transacoes": [{"data": "04/05/2026", "valor": -27.5},
                                                        {"data": "05/05/2026", "valor": 10.0}]}
    assert movimentos_do_banco(dados) == [("04/05/2026", -27.5), ("05/05/2026", 10.0)]


def test_movimentos_do_xls_usam_o_sinal_da_conta_de_aplicacao():
    dados = {"tipo_extrato": "APLICACAO", "transacoes": [], "movimentos": [
        {"data": "04/05/2026", "tipo": "RESGATE", "valor": 20582.25},
        {"data": "04/05/2026", "tipo": "RENDIMENTO", "valor": 6.44},
        {"data": "06/05/2026", "tipo": "APLICACAO", "valor": 9999.0}]}
    assert movimentos_do_banco(dados) == [
        ("04/05/2026", -20582.25), ("04/05/2026", 6.44), ("06/05/2026", 9999.0)]


def test_xls_sem_movimentos_completos_nao_aponta_sobras():
    assert movimentos_do_banco({"tipo_extrato": "APLICACAO", "transacoes": [{"data": "x", "valor": 1}]}) is None


def _resultado(situacao="conciliado", saldo=None, sobras=None, pendentes=0):
    from controllers.prova_real import ResultadoExtrato, ResultadoSaldo
    return ResultadoExtrato("12345-6", "10130", "DR - CENTRAL", "CORRENTE", situacao, pendentes=pendentes,
                            saldo=saldo or ResultadoSaldo(NAO_CONFERIDO, motivo="período filtrado à mão"),
                            sobras=sobras)


def test_resumo_de_cada_resultado():
    from controllers.prova_real import MovimentoSiga, ResultadoSaldo, resumo_resultado
    assert resumo_resultado(_resultado(saldo=conferir_saldo(1.0, 1.0))) == ("ok", "✔ Saldo confere (R$ 1,00)")
    nivel, texto = resumo_resultado(_resultado(saldo=conferir_saldo(1.0, 43.1),
                                               sobras=[MovimentoSiga("05/05/2026", 42.1)]))
    assert nivel == "alerta"
    assert texto == "⚠ Diferença de R$ 42,10 (SIGA R$ 43,10 × banco R$ 1,00) · 1 no SIGA sem par no banco"
    assert resumo_resultado(_resultado()) == ("neutro", "— Não conferido: período filtrado à mão")
    assert resumo_resultado(_resultado("conta_nao_encontrada"))[0] == "alerta"
    assert resumo_resultado(_resultado("mes_fechado", pendentes=2)) == (
        "neutro", "— Mês fechado no SIGA: 2 item(ns) pendente(s)")
    # Saldo confere, mas ficou algo pendente: não é "ok"
    assert resumo_resultado(_resultado("pendente", saldo=ResultadoSaldo(CONFERE, 1.0, 1.0), pendentes=1))[0] == "alerta"


def test_resumo_de_extrato_nao_autorizado_na_previa():
    from controllers.prova_real import resumo_resultado
    assert resumo_resultado(_resultado("recusado", pendentes=3)) == (
        "neutro", "— Lançamento não autorizado por você: 3 item(ns) pendente(s)")
