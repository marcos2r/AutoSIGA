"""De onde vem a diferença da prova real: composição, painel e Excel (dados fictícios)."""

from controllers.baixa_energia import SEM_FATURA, DebitoEnergia, Decisao, ResultadoBaixa
from controllers.diferenca_extrato import (
    ORIGEM_ENERGIA,
    ORIGEM_FALTA,
    ORIGEM_RESTO,
    ORIGEM_SOBRA,
    cabecalho_extrato,
    compor_diferenca,
    itens_da_diferenca,
    linhas_do_extrato,
)
from controllers.prova_real import (
    MovimentoBanco,
    MovimentoSiga,
    ResultadoExtrato,
    conferir_saldo,
    parear,
)

ENERGIA = "DEBITO CONVENIOS-ENERGI 70 ID 00012345678 ENERGISA MS"


def _linha(data, entrada="", saida="", historico=""):
    return {"data": data, "entrada": entrada, "saida": saida, "historico": historico}


def _resultado(saldo_banco, saldo_siga, sobras, faltas, baixas=None):
    return ResultadoExtrato("12345-6", "10123", "ADM - CENTRAL", "CORRENTE", "conciliado",
                            saldo=conferir_saldo(saldo_banco, saldo_siga), sobras=sobras, faltas=faltas,
                            baixas=baixas, periodo="01/10/2026 a 23/10/2026")


def test_parear_devolve_o_que_sobra_de_cada_lado():
    banco = [("05/10/2026", -100.0, "TARIFA"), ("06/10/2026", -50.0, ENERGIA)]
    siga = [_linha("05/10/2026", saida="100,00"), _linha("07/10/2026", saida="30,00", historico="DUPLICADO")]

    sobras, faltas = parear(banco, siga)

    assert [(s.data, s.valor) for s in sobras] == [("07/10/2026", -30.0)]
    assert faltas == [MovimentoBanco("06/10/2026", -50.0, ENERGIA)]


def test_composicao_fecha_com_a_diferenca():
    # SIGA − banco = (−30 da sobra) − (−50 de energia) − (−20 de tarifa) + 5 sem explicação = 45
    sobras = [MovimentoSiga("07/10/2026", -30.0, "DUPLICADO")]
    faltas = [MovimentoBanco("06/10/2026", -50.0, ENERGIA), MovimentoBanco("08/10/2026", -20.0, "TARIFA")]

    c = compor_diferenca(45.0, sobras, faltas)

    assert [f.valor for f in c.energia] == [-50.0] and [f.valor for f in c.outros] == [-20.0]
    assert c.sem_explicacao == 5.0


def test_centavo_de_arredondamento_nao_vira_resto():
    assert compor_diferenca(50.01, [], [MovimentoBanco("06/10/2026", -50.0, ENERGIA)]).sem_explicacao == 0.0


def test_cabecalho_mostra_tipo_e_periodo():
    r = _resultado(1.0, 1.0, [], [])
    assert cabecalho_extrato(r) == "10123 · ADM - CENTRAL · Conta corrente · 01/10/2026 a 23/10/2026"


def test_painel_lista_cada_origem_da_diferenca():
    r = _resultado(100.0, 145.0, [MovimentoSiga("07/10/2026", -30.0, "DUPLICADO")],
                   [MovimentoBanco("06/10/2026", -50.0, ENERGIA), MovimentoBanco("08/10/2026", -20.0, "TARIFA")])

    textos = [t for _, t in linhas_do_extrato(r)]

    assert textos == [
        "   De onde vem a diferença de R$ 45,00:",
        "   • −R$ 30,00: 1 lançamento(s) no SIGA sem par no banco",
        "      07/10/2026 · DUPLICADO · R$ -30,00",
        "   • +R$ 50,00: 1 débito(s) de energia sem baixa no SIGA",
        f"      06/10/2026 · {ENERGIA} · R$ -50,00",
        "   • +R$ 20,00: 1 movimento(s) do banco sem lançamento no SIGA",
        "      08/10/2026 · TARIFA · R$ -20,00",
        "   • +R$ 5,00: sem explicação nos movimentos do período (confira o saldo inicial e lançamentos fora "
        "do período)",
    ]


def test_energia_com_baixas_mostra_so_o_total_e_as_baixas_explicam():
    decisao = Decisao(DebitoEnergia("06/10/2026", 50.0, "00012345678"), SEM_FATURA, "código sem fatura conhecida")
    r = _resultado(100.0, 150.0, [], [MovimentoBanco("06/10/2026", -50.0, ENERGIA)],
                   baixas=[ResultadoBaixa(decisao, SEM_FATURA, decisao.motivo)])

    textos = [t for _, t in linhas_do_extrato(r)]

    assert textos[1] == "   • +R$ 50,00: 1 débito(s) de energia sem baixa no SIGA (detalhe nas baixas abaixo)"
    assert "código sem fatura conhecida" in textos[-1] and len(textos) == 3


def test_saldo_que_confere_nao_mostra_composicao():
    assert linhas_do_extrato(_resultado(1.0, 1.0, [], [])) == []


def test_itens_do_excel_somam_a_diferenca():
    r = _resultado(100.0, 145.0, [MovimentoSiga("07/10/2026", -30.0, "DUPLICADO")],
                   [MovimentoBanco("06/10/2026", -50.0, ENERGIA), MovimentoBanco("08/10/2026", -20.0, "TARIFA")])

    itens = itens_da_diferenca(r)

    assert [i[3] for i in itens] == [ORIGEM_SOBRA, ORIGEM_ENERGIA, ORIGEM_FALTA, ORIGEM_RESTO]
    assert round(sum(i[4] for i in itens), 2) == r.saldo.diferenca


def test_sem_faltas_conhecidas_o_excel_lista_so_as_sobras():
    r = _resultado(1.0, 43.1, [MovimentoSiga("05/05/2026", 42.1, "DUPLICADO")], None)
    assert itens_da_diferenca(r) == [("05/05/2026", "DUPLICADO", 42.1, ORIGEM_SOBRA, 42.1)]
