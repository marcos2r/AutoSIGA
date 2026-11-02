"""Aprovação e baixa em lote dos boletos e PIX pelo bot, com página falsa (dados fictícios)."""

import pytest
from bot_falso import criar_bot
from test_baixa_provisoes_bot import PaginaBaixa

import bot.baixa_contas_pagar as bcp
import bot.baixa_provisoes as bp
from controllers.baixa_contas_pagar import (
    APROVADA_SEM_BAIXA,
    BAIXADA,
    BAIXAR,
    FALHOU,
    JA_BAIXADA,
    NAO_AUTORIZADA,
    DecisaoPagamento,
    PagamentoExtrato,
    ParcelaSiga,
)
from controllers.baixa_energia import APROVADO, LANCADO, PAGO

GUID_A = "AAAAAAAA-0000-4D59-89EF-000000000001"
GUID_B = "AAAAAAAA-0000-4D59-89EF-000000000002"
PERIODO = ("21/09/2026", "10/11/2026")
FORNECEDOR = "FERRAGENS AURORA LTDA"


class PaginaLote(PaginaBaixa):
    """TES01501 e TES01519 falsas: `lote` é o que a baixa em lote mostra ao abrir."""

    def __init__(self, guids=(GUID_A, GUID_B), total="300,00", abre=True, status_final=PAGO, **kwargs):
        super().__init__(documento="501", valor="100,00", data_lida="26/10/2026",
                         gravados=[["26/10/2026", "100,00", "0,00"], ["26/10/2026", "200,00", "0,00"]], **kwargs)
        self.lote = {"guids": list(guids), "total": total}
        self.abre, self.status_lote = abre, status_final
        self.selecionados = None

    def evaluate(self, script, arg=None):
        if script == bcp._JS_ABRIR_LOTE:
            self.scripts.append(script)
            self.selecionados = list(arg)
            return True
        respostas = {
            bcp._JS_LOTE_ABERTO: lambda: self.abre,
            bcp._JS_LER_LOTE: lambda: self.lote,
            bp._JS_AVISOS_ABERTOS: lambda: [] if self.abre else ["Existem itens selecionados com Status "
                                                                 "diferente de Aprovado"],
            bcp._JS_VALOR_HISTORICO: lambda: "21",
            bcp._JS_FECHAR_SELECT2: lambda: True,
            bcp._JS_DEFINIR_DATA: lambda: setattr(self, "data_lida", arg) or True,
            bp._JS_LER_PROVISOES: lambda: [_linha("501", GUID_A, self.status_lote), _linha("502", GUID_B, self.status_lote)],
        }
        if script in respostas:
            self.scripts.append(script)
            return respostas[script]()
        return super().evaluate(script, arg)


def _linha(numero, guid, status, valor="100,00"):
    return {"vencimento": "23/10/2026", "numero": numero, "fornecedor": FORNECEDOR, "valor": valor,
            "status": status, "guid": guid}


def _decisao(status_a=LANCADO, status_b=APROVADO):
    pagamento = PagamentoExtrato("26/10/2026", 300.0, FORNECEDOR, "11222333000144", "boleto")
    parcelas = (ParcelaSiga("501", FORNECEDOR, 100.0, status_a, GUID_A, "23/10/2026"),
                ParcelaSiga("502", FORNECEDOR, 200.0, status_b, GUID_B, "23/10/2026"))
    return DecisaoPagamento(pagamento, BAIXAR, "501 e 502", parcelas)


def _bot(monkeypatch):
    return criar_bot(monkeypatch, bp, "extrato")


def test_aprova_o_lancado_e_baixa_as_parcelas_juntas_na_baixa_em_lote(monkeypatch):
    bot, reg = _bot(monkeypatch)
    # A parcela 502 vale 200: a tela da TES01506 mostra o valor de cada parcela conferida
    valores = iter(["100,00", "100,00", "200,00"])
    pagina = PaginaLote()
    original = pagina.evaluate
    monkeypatch.setattr(pagina, "evaluate", lambda s, a=None: (
        dict(pagina.cabecalho, documento="501" if pagina.visitas[-1].endswith(GUID_A) else "502", valor=next(valores))
        if s == bp._JS_LER_CABECALHO else original(s, a)))

    resultados, fechado = bot._executar_baixas_cp(pagina, [_decisao()], "10123", PERIODO)

    assert [r.situacao for r in resultados] == [BAIXADA] and fechado is False
    # Só a Lançado passa pela TES01508; depois a data gravada é conferida em cada parcela
    assert pagina.visitas == [f"https://siga.exemplo/TES/TES01508.aspx?codigo={GUID_A}",
                              f"https://siga.exemplo/TES/TES01506.aspx?codigo={GUID_A}",
                              f"https://siga.exemplo/TES/TES01506.aspx?codigo={GUID_B}"]
    assert pagina.selecionados == [GUID_A, GUID_B]
    assert pagina.escolhas == [("f_formapagamento", "8"), ("f_conta", "901"), ("f_historico", "21")]
    assert reg.campos[-1] == {"f_documento": "501"}
    assert "boleto de R$ 300,00 pago em 26/10/2026" in reg.campos[0]["f_motivo"]
    assert bcp._SUBMIT_LOTE in pagina.cliques()
    assert reg.gravacoes == 2  # a aprovação e a baixa em lote


def test_lote_com_outras_parcelas_ou_outro_total_nao_e_confirmado(monkeypatch):
    for pagina in (PaginaLote(guids=[GUID_A]), PaginaLote(total="299,00")):
        bot, reg = _bot(monkeypatch)
        resultados, _ = bot._executar_baixas_cp(pagina, [_decisao(APROVADO)], "10123", PERIODO)

        assert resultados[0].situacao == FALHOU
        assert bcp._SUBMIT_LOTE not in pagina.cliques() and reg.gravacoes == 0


def test_data_que_a_tela_deixa_vazia_e_posta_pelo_jquery(monkeypatch):
    bot, reg = _bot(monkeypatch)
    pagina = PaginaLote()
    pagina.data_lida = ""  # a TES01519 apaga algumas datas digitadas em campo vazio

    bot._preencher_data_lote(pagina, "05/10/2026")

    assert pagina.data_lida == "05/10/2026" and bcp._JS_DEFINIR_DATA in pagina.scripts


def test_data_trocada_pela_tela_nao_e_corrigida_por_baixo(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaLote()
    pagina.data_lida = "01/10/2026"

    with pytest.raises(bp.BaixaNaoConferidaError):
        bot._preencher_data_lote(pagina, "05/10/2026")
    assert bcp._JS_DEFINIR_DATA not in pagina.scripts


def test_lote_que_nao_abre_mostra_o_aviso_do_siga(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaLote(abre=False)
    monkeypatch.setattr(bot, "_esperar_condicao", lambda page, script, segundos: False)

    resultados, _ = bot._executar_baixas_cp(pagina, [_decisao(APROVADO)], "10123", PERIODO)

    assert resultados[0].situacao == FALHOU and "Status diferente de Aprovado" in resultados[0].detalhe


def test_status_que_nao_ficou_pago_vira_falha(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaLote(status_final=APROVADO)
    monkeypatch.setattr(bot, "_conferir_data_gravada", lambda *a: None)

    resultados, _ = bot._executar_baixas_cp(pagina, [_decisao(APROVADO)], "10123", PERIODO)

    assert resultados[0].situacao == FALHOU and "Aprovado" in resultados[0].detalhe


def test_mes_fechado_depois_de_aprovar_interrompe_os_pagamentos_seguintes(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaLote()

    def fechado(page, decisao, conta):
        raise bcp.MesFechadoError("baixa")

    monkeypatch.setattr(bot, "_baixar_em_lote", fechado)
    monkeypatch.setattr(bot, "_aprovar_provisao", lambda *a: None)
    monkeypatch.setattr(bot, "_conferir_status_cp", lambda page, resultados, periodo: resultados)

    resultados, mes_fechado = bot._executar_baixas_cp(pagina, [_decisao(), _decisao()], "10123", PERIODO)

    assert mes_fechado is True and [r.situacao for r in resultados] == [APROVADA_SEM_BAIXA]


def _extrato(tipo="CORRENTE", descricao=f"LIQUIDACAO BOLETO-          11222333000144 {FORNECEDOR}"):
    return {"tipo_extrato": tipo, "data_inicial": "01/10/2026", "data_final": "31/10/2026",
            "transacoes": [{"data": "26/10/2026", "valor": -300.0, "descricao": descricao}]}


def test_etapa_so_roda_com_a_opcao_ligada_em_conta_corrente_com_boleto_ou_pix(monkeypatch):
    bot, _ = _bot(monkeypatch)
    lidas = []
    monkeypatch.setattr(bot, "_ler_contas_a_pagar", lambda page, periodo: lidas.append(periodo) or [])
    bot.baixar_energia = False
    assert bot._etapa_baixas_contas_pagar(None, _extrato(), "10123") == (None, False)
    bot.baixar_energia = True
    assert bot._etapa_baixas_contas_pagar(None, _extrato("APLICACAO"), "10123") == (None, False)
    assert bot._etapa_baixas_contas_pagar(None, _extrato(descricao="TARIFA"), "10123") == (None, False)
    assert lidas == []


def test_etapa_decide_com_a_grade_e_respeita_a_previa(monkeypatch):
    bot, _ = _bot(monkeypatch)
    bot.baixar_energia = True
    grade = [_linha("501", GUID_A, LANCADO, "100,00"), _linha("502", GUID_B, LANCADO, "200,00"),
             _linha("400", "AAAAAAAA-0000-4D59-89EF-000000000003", PAGO, "77,00")]
    monkeypatch.setattr(bot, "_ler_contas_a_pagar", lambda page, periodo: grade)
    monkeypatch.setattr(bot, "_pedir_autorizacao", lambda previa, conta, tipo: False)
    extrato = _extrato()
    extrato["transacoes"].append({"data": "24/10/2026", "valor": -77.0,
                                  "descricao": f"PAGAMENTO PIX-PIX_DEB   11222333000144 {FORNECEDOR}"})

    resultados, fechado = bot._etapa_baixas_contas_pagar(None, extrato, "10123")

    assert [r.situacao for r in resultados] == [NAO_AUTORIZADA, JA_BAIXADA] and fechado is False
    assert len(resultados[0].decisao.parcelas) == 2


def test_falha_ao_ler_a_contas_a_pagar_nao_para_a_conciliacao(monkeypatch):
    bot, reg = _bot(monkeypatch)
    bot.baixar_energia = True

    def falhar(page, periodo):
        raise bp.GradeIncompletaError("a Contas a Pagar mostrou 100 de 300 linhas")

    monkeypatch.setattr(bot, "_ler_contas_a_pagar", falhar)

    assert bot._etapa_baixas_contas_pagar(None, _extrato(), "10123") == (None, False)
    assert reg.capturas == ["erro_ler_contas_a_pagar"] and "puladas" in reg.status[-1]
