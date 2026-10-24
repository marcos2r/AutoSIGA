"""Provisões de energia do período antes dos extratos: regras e etapa do bot (dados fictícios)."""

import pytest
from bot_falso import criar_bot

import bot.baixa_provisoes as bp
import bot.provisoes_energia as pe
from controllers.baixa_energia import LANCADO, PAGO, ProvisaoSiga
from controllers.provisao_energia import (
    JA_LANCADA,
    JA_LANCADA_MANUAL,
    LANCAR,
    SEM_EMISSAO,
    SEM_LOCALIDADE,
    SEM_NUMERO,
    chave_do_codigo,
    decidir_provisoes,
    linhas_do_painel,
    provisao_existente,
)

GUID = "C2911CC0-0000-4D59-89EF-000000000001"


def _fatura(numero="018000001", valor=224.25, codigo="00012345678"):
    return {"numero_fatura": numero, "valor": valor, "codigo_debito": codigo, "uc": "123.456.051-00",
            "emissao": "05/10/2026", "vencimento": "26/10/2026", "localidade_nome": "ADM DOURADOS"}


def _prov(numero, valor=224.25, status=LANCADO):
    return ProvisaoSiga(numero, valor, status, GUID)


def test_chave_do_codigo_tira_os_zeros_e_recusa_codigo_curto():
    assert chave_do_codigo("00012345678") == "12345678"
    assert chave_do_codigo("0000012") == ""
    assert chave_do_codigo("") == ""


@pytest.mark.parametrize("provisoes, esperado", [
    ([_prov("018000001")], JA_LANCADA),
    ([_prov("18000001")], JA_LANCADA),  # o SIGA às vezes tira os zeros
    ([_prov("1012345678", status=PAGO)], JA_LANCADA_MANUAL),  # GUIA lançada à mão com o código da UC
    ([_prov("1012345678", valor=81.41)], LANCAR),  # mesmo código, outro valor: fatura de outro mês
    ([_prov("019999999")], LANCAR),
    ([], LANCAR),
])
def test_provisao_existente_pelo_numero_ou_pelo_codigo_e_valor(provisoes, esperado):
    assert provisao_existente(_fatura(), provisoes)[0] == esperado


def test_decisoes_com_cada_pendencia_e_aviso_de_duplicada():
    ok = _fatura("018000002", valor=10.0)
    duplicada = _fatura("018000001")
    sem_numero = _fatura("")
    provisoes = [_prov("018000001"), _prov("018000001")]

    decisoes = decidir_provisoes([ok, duplicada, sem_numero], [_fatura("A")], [_fatura("B")], provisoes)

    assert [d.acao for d in decisoes] == [LANCAR, JA_LANCADA, SEM_NUMERO, SEM_LOCALIDADE, SEM_EMISSAO]
    assert "lançada 2 vezes" in decisoes[1].motivo


def test_painel_resume_e_lista_o_que_ficou_pendente():
    decisoes = decidir_provisoes([_fatura("F1"), _fatura("F2"), _fatura("F3")], [], [],
                                 [_prov("F3")])
    situacoes = {"F1": ("lancada", ""), "F2": ("nao_lancada", "competência 10/2026 fechada no SIGA")}

    linhas = linhas_do_painel(decisoes, situacoes)

    assert linhas[0] == ("alerta", "⚡ Provisões de energia: 1 lançada(s), 1 já estavam no SIGA, 1 pendente(s)")
    assert linhas[1:] == [("alerta", "   ⚠ fatura F2 · UC 123.456.051-00: competência 10/2026 fechada no SIGA")]


def test_conferencia_le_a_contas_a_pagar_em_volta_do_vencimento(monkeypatch):
    bot, _ = criar_bot(monkeypatch, bp, "extrato")
    periodos = []
    monkeypatch.setattr(bot, "_ler_provisoes_energisa",
                        lambda page, periodo: periodos.append(periodo) or [_prov("1012345678")])

    assert bot.verificar_fatura_ja_lancada(None, "018000001", vencimento="26/10/2026", fatura=_fatura())
    assert not bot.verificar_fatura_ja_lancada(None, "018000001", vencimento="26/10/2026")
    assert periodos[0] == ("27/08/2026", "25/12/2026")


def test_grade_cortada_nao_vira_decisao(monkeypatch):
    bot, _ = criar_bot(monkeypatch, bp, "extrato")
    monkeypatch.setattr(bot, "_executar_programa", lambda page, codigo: None)

    class Pagina:
        def evaluate(self, script, arg=None):
            if script == bp._JS_MOSTRAR_TODAS:
                return {"lidas": 100, "total": 156}
            return True

        def wait_for_load_state(self, estado):
            pass

    with pytest.raises(bp.GradeIncompletaError):
        bot._ler_provisoes_energisa(Pagina(), ("01/09/2026", "30/11/2026"))


def _bot_etapa(monkeypatch, conectado=True, autorizar=True, confirmadas=("F1",), validas=None):
    bot, reg = criar_bot(monkeypatch, bp, "extrato")
    bot.lote_processados = [{"data_inicial": "01/10/2026", "data_final": "23/10/2026"}]
    reg.buscas, reg.previas, reg.lancadas = [], [], []
    monkeypatch.setattr(pe.EmailReader, "conectado", staticmethod(lambda: conectado))
    validas = validas if validas is not None else [_fatura("F1"), _fatura("F2", codigo="00099999999")]
    monkeypatch.setattr(pe.FaturaEnergiaController, "buscar_faturas_do_periodo",
                        staticmethod(lambda meses, cb=None: reg.buscas.append(meses) or (validas, [], [])))
    monkeypatch.setattr(bot, "_garantir_localidade_competencia", lambda page, uc, comp: None)
    monkeypatch.setattr(bot, "_ler_provisoes_energisa", lambda page, periodo: [_prov("F2")])
    monkeypatch.setattr(bot, "_pedir_autorizacao",
                        lambda previa, conta, tipo: reg.previas.append((previa, tipo)) or autorizar)

    def inserir(page, faturas):
        reg.lancadas.append([f["numero_fatura"] for f in faturas])
        bot.faturas_energia_sucesso = [f for f in faturas if f["numero_fatura"] in confirmadas]
        bot.motivos_energia = {"F9": "competência 10/2026 fechada no SIGA"}

    monkeypatch.setattr(bot, "inserir_faturas_energia_siga", inserir)
    bot._indice_energia = {"velho": []}
    return bot, reg


def test_etapa_provisiona_so_o_que_falta_depois_da_previa(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch)

    linhas = bot._etapa_provisoes_energia(None)

    assert reg.buscas == [["09/2026", "10/2026"]]
    assert [(len(p), t) for p, t in reg.previas] == [(1, "provisoes")]
    assert reg.lancadas == [["F1"]]
    assert linhas[0] == ("ok", "⚡ Provisões de energia: 1 lançada(s), 1 já estavam no SIGA, 0 pendente(s)")
    assert bot._indice_energia is None  # a baixa relê os PDFs novos


def test_etapa_sem_email_conectado_nao_busca_nem_le_o_siga(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch, conectado=False)

    assert bot._etapa_provisoes_energia(None) is None
    assert reg.buscas == [] and reg.lancadas == []


def test_etapa_com_previa_recusada_nao_lanca(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch, autorizar=False)

    linhas = bot._etapa_provisoes_energia(None)

    assert reg.lancadas == []
    assert linhas[1] == ("alerta", "   ⚠ fatura F1 · UC 123.456.051-00: provisão não autorizada na prévia")


def test_etapa_sem_ler_a_contas_a_pagar_nao_lanca_nada(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch)

    def falhar(page, periodo):
        raise bp.GradeIncompletaError("a Contas a Pagar mostrou 100 de 156 linhas")

    monkeypatch.setattr(bot, "_ler_provisoes_energisa", falhar)

    linhas = bot._etapa_provisoes_energia(None)

    assert reg.previas == [] and reg.lancadas == []
    assert linhas[0][0] == "alerta" and "100 de 156" in linhas[0][1]


def test_etapa_registra_a_fatura_que_nao_foi_confirmada(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch, confirmadas=())

    linhas = bot._etapa_provisoes_energia(None)

    assert linhas[1] == ("alerta", "   ⚠ fatura F1 · UC 123.456.051-00: não confirmada no SIGA: veja o log")


def test_etapa_usa_as_faturas_baixadas_antes_de_abrir_o_navegador(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch)
    bot._busca_energia = {"meses": ["10/2026"], "faturas": ([_fatura("F1")], [], [])}

    linhas = bot._etapa_provisoes_energia(None)

    assert reg.buscas == []  # o e-mail não é lido de novo
    assert reg.lancadas == [["F1"]]
    assert linhas[0][0] == "ok" and bot._busca_energia is None


def test_falha_no_email_antes_do_navegador_vai_para_o_painel(monkeypatch):
    bot, reg = _bot_etapa(monkeypatch)
    bot._busca_energia = {"linhas": [("alerta", "⚡ falha ao ler o e-mail")]}

    assert bot._etapa_provisoes_energia(None) == [("alerta", "⚡ falha ao ler o e-mail")]
    assert reg.lancadas == []
