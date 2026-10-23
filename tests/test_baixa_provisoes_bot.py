"""Aprovação e baixa das provisões de energia pelo bot, com página falsa (dados fictícios)."""

import pytest
from bot_falso import PaginaGravadora, criar_bot

import bot.baixa_provisoes as bp
from bot.extratos import MesFechadoError
from controllers.baixa_energia import (
    APROVADA_SEM_BAIXA,
    APROVADO,
    BAIXADA,
    BAIXAR,
    FALHOU,
    LANCADO,
    PAGO,
    SEM_FATURA,
    DebitoEnergia,
    Decisao,
    ProvisaoSiga,
    periodo_de_vencimento,
    provisoes_da_grade,
    valor_siga,
)

GUID = "C2911CC0-0000-4D59-89EF-000000000001"
GUID_2 = "C2911CC0-0000-4D59-89EF-000000000002"
PERIODO = ("17/07/2026", "05/09/2026")
CONTAS = [{"texto": "101 - BANCOS CONTA MOVIMENTO", "valor": "15", "inativa": False},
          {"texto": "10130 - SICREDI - AG: 0101 CC: 12345-6 CAPTACAO", "valor": "900", "inativa": False},
          {"texto": "10123 - SICREDI - AG: 0101 CC: 12345-6 MANUTENCAO", "valor": "901", "inativa": False}]


class PaginaBaixa(PaginaGravadora):
    """Responde aos scripts do mixin como as telas do SIGA; cada atributo muda uma resposta."""

    def __init__(self, documento="018000001", valor="224,25", apagar="224,25", pagamentos=None,
                 restante="0,00", status_final=PAGO, mes_fechado=False):
        super().__init__()
        self.url = "https://siga.exemplo/TES/TES01501.aspx"
        self.cabecalho = {"documento": documento, "valor": valor, "apagar": apagar}
        self.pagamentos = pagamentos if pagamentos is not None else [["DÉBITO AUTOMÁTICO", "10123 - ...", "224,25", ""]]
        self.restante = restante
        self.status_final = status_final
        self.mes_fechado = mes_fechado
        self.visitas = []
        self.escolhas = []

    def goto(self, url):
        self.visitas.append(url)

    def evaluate(self, script, arg=None):
        self.scripts.append(script)
        respostas = {
            bp._JS_LER_CABECALHO: lambda: self.cabecalho,
            bp._JS_PREENCHER_DATA: lambda: True,
            bp._JS_MODAL_PAGAMENTO_ABERTO: lambda: True,
            bp._JS_QTD_CONTAS: lambda: len(CONTAS) + 1,
            bp._JS_LER_CONTAS_TES: lambda: CONTAS,
            bp._JS_VALOR_HISTORICO: lambda: "21",
            bp._JS_LER_PAGAMENTOS: lambda: {"linhas": self.pagamentos, "restante": self.restante},
            bp._JS_FILTRAR_VENCIMENTO: lambda: True,
            bp._JS_LER_PROVISOES: lambda: [_linha("018000001", self.status_final, GUID)],
        }
        if script == bp._JS_ESCOLHER:
            self.escolhas.append(tuple(arg))
            return True
        if "Fechamento de competência" in script:
            return self.mes_fechado
        return respostas[script]() if script in respostas else None

    def cliques(self):
        return [s for s, a, _ in self.acoes if a == "click"]


def _linha(numero, status, guid, fornecedor="ENERGISA MATO GROSSO DO SUL", valor="224,25"):
    return {"vencimento": "26/08/2026", "numero": numero, "fornecedor": fornecedor, "valor": valor,
            "status": status, "guid": guid}


def _decisao(status=LANCADO, guid=GUID, acao=BAIXAR):
    provisao = ProvisaoSiga("018000001", 224.25, status, guid)
    return Decisao(DebitoEnergia("26/08/2026", 224.25, "00012345678"), acao, "fatura 018000001", None, provisao)


def _bot(monkeypatch):
    bot, reg = criar_bot(monkeypatch, bp, "extrato")
    return bot, reg


def test_aprova_e_baixa_com_debito_automatico_na_conta_do_extrato(monkeypatch):
    bot, reg = _bot(monkeypatch)
    pagina = PaginaBaixa()

    resultados = bot._executar_baixas(pagina, [_decisao()], "10123", PERIODO)

    assert [r.situacao for r in resultados] == [BAIXADA]
    assert pagina.visitas == [f"https://siga.exemplo/TES/TES01508.aspx?codigo={GUID}",
                              f"https://siga.exemplo/TES/TES01506.aspx?codigo={GUID}"]
    assert pagina.escolhas == [("f_codigoFormaPgto", "9"), ("f_conta", "901"), ("f_historicobaixa", "21")]
    assert reg.campos == [{"f_valorpagamento": "224,25"}]
    # Aprovar, Novo Pagamento, Inserir e Confirmar, nessa ordem, e a TES01501 relida no fim
    assert pagina.cliques() == [bp._SUBMIT_FORMULARIO, "#btn-novo-pagamento", "#btn-confirmar", bp._SUBMIT_FORMULARIO,
                                "#btn_executar_programa"]
    assert reg.gravacoes == 2


def test_provisao_ja_aprovada_so_e_baixada(monkeypatch):
    bot, reg = _bot(monkeypatch)
    pagina = PaginaBaixa()

    bot._executar_baixas(pagina, [_decisao(APROVADO)], "10123", PERIODO)

    assert [u.split("/")[-1].split("?")[0] for u in pagina.visitas] == ["TES01506.aspx"]
    assert reg.gravacoes == 1


def test_so_executa_decisoes_baixar(monkeypatch):
    bot, reg = _bot(monkeypatch)
    pagina = PaginaBaixa()

    assert bot._executar_baixas(pagina, [_decisao(acao=SEM_FATURA)], "10123", PERIODO) == []
    assert pagina.visitas == [] and reg.gravacoes == 0


@pytest.mark.parametrize("pagina, motivo", [
    (PaginaBaixa(documento="018999999"), "documento"),                    # TES abriu outra fatura
    (PaginaBaixa(valor="230,00", apagar="230,00"), "valor"),              # valor da provisão mudou
])
def test_tela_diferente_nao_aprova_nem_baixa(monkeypatch, pagina, motivo):
    bot, reg = _bot(monkeypatch)

    resultados = bot._executar_baixas(pagina, [_decisao()], "10123", PERIODO)

    assert resultados[0].situacao == FALHOU and motivo in resultados[0].detalhe
    assert reg.gravacoes == 0
    assert reg.capturas == ["baixa_018000001"]


@pytest.mark.parametrize("pagina", [
    PaginaBaixa(apagar="100,00"),                                          # já houve pagamento parcial
    PaginaBaixa(pagamentos=[]),                                            # Inserir não pôs nada
    PaginaBaixa(pagamentos=[["DÉBITO", "10123", "224,25"], ["DÉBITO", "10123", "224,25"]]),
    PaginaBaixa(pagamentos=[["DÉBITO", "10123", "200,00"]]),
    PaginaBaixa(restante="24,25"),
])
def test_baixa_nao_confirma_se_a_grade_de_pagamentos_nao_bate(monkeypatch, pagina):
    bot, reg = _bot(monkeypatch)

    resultados = bot._executar_baixas(pagina, [_decisao()], "10123", PERIODO)

    # Aprovou (1 gravação), mas não clicou em Confirmar na baixa
    assert reg.gravacoes == 1
    assert pagina.cliques().count(bp._SUBMIT_FORMULARIO) == 1
    assert resultados[0].situacao == FALHOU  # status relido não é Aprovado (a página falsa diz Pago)


def test_aprovada_e_baixa_falhou_fica_registrada(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaBaixa(pagamentos=[], status_final=APROVADO)

    resultados = bot._executar_baixas(pagina, [_decisao()], "10123", PERIODO)

    assert resultados[0].situacao == APROVADA_SEM_BAIXA


def test_conta_que_nao_aparece_na_baixa_nao_e_trocada_por_outra(monkeypatch):
    bot, reg = _bot(monkeypatch)
    pagina = PaginaBaixa()

    resultados = bot._executar_baixas(pagina, [_decisao(APROVADO)], "10999", PERIODO)

    assert resultados[0].situacao == FALHOU and "10999" in resultados[0].detalhe
    assert ("f_conta", "900") not in pagina.escolhas and reg.gravacoes == 0


def test_gravou_mas_nao_ficou_pago_vira_falha(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaBaixa(status_final=APROVADO)

    resultados = bot._executar_baixas(pagina, [_decisao()], "10123", PERIODO)

    assert resultados[0].situacao == FALHOU and "Aprovado" in resultados[0].detalhe


def test_mes_fechado_interrompe_o_lote(monkeypatch):
    bot, _ = _bot(monkeypatch)

    with pytest.raises(MesFechadoError):
        bot._executar_baixas(PaginaBaixa(mes_fechado=True), [_decisao(), _decisao(guid=GUID_2)], "10123", PERIODO)


def test_codigo_de_parcela_invalido_nao_vira_url(monkeypatch):
    bot, _ = _bot(monkeypatch)
    pagina = PaginaBaixa()

    resultados = bot._executar_baixas(pagina, [_decisao(guid="x' onload='1")], "10123", PERIODO)

    assert pagina.visitas == [] and resultados[0].situacao == FALHOU


def test_provisoes_da_grade_so_da_energisa_e_com_guid():
    linhas = [_linha("018000001", LANCADO, GUID), _linha("1", LANCADO, GUID_2, fornecedor="OUTRO LTDA"),
              _linha("018000003", PAGO, ""), _linha("018000004", APROVADO, GUID_2, valor="1.234,56")]

    provisoes = provisoes_da_grade(linhas)

    assert [(p.numero, p.valor, p.status) for p in provisoes] == [("018000001", 224.25, LANCADO),
                                                                 ("018000004", 1234.56, APROVADO)]


def test_periodo_de_vencimento_e_valor_no_formato_do_siga():
    assert periodo_de_vencimento("01/08/2026", "31/08/2026") == ("22/06/2026", "05/09/2026")
    assert periodo_de_vencimento("", "31/08/2026") is None
    assert valor_siga(1234.5) == "1.234,50"
