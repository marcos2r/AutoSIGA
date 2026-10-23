"""Laço de extratos do SigaBot de ponta a ponta, com uma Caixas e Bancos (TES01701) falsa."""

import importlib
from contextlib import nullcontext
from types import SimpleNamespace

import bot.siga_bot as siga_bot
from bot.extratos import MesFechadoError
from bot.siga_bot import SigaBot

ROTULOS = {
    "10130": "10130 - SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO",
    "10396": "10396 - SICREDI - AG: 0101 CC: 12345-6 APLICACAO",
    "10127": "10127 - SICREDI - AG: 0101 CC: 22222-2 PIA",
}


def _linha(data, valor):
    """Linha da grade #grid1 como o bot a lê (valores no formato brasileiro)."""
    texto = f"{abs(valor):.2f}".replace(".", ",")
    return {"data": data, "lote": "", "documento": "", "historico": "", "origem": "",
            "entrada": texto if valor > 0 else "", "saida": texto if valor < 0 else "", "saldo": ""}


class _Locator:
    def __init__(self, pagina, seletor):
        self.pagina, self.seletor = pagina, seletor

    @property
    def first(self):
        return self

    def wait_for(self, state="visible", timeout=None):
        pass

    def is_visible(self):
        return True

    def click(self, **kwargs):
        self.pagina.acoes.append(("click", self.seletor))

    def fill(self, texto, **kwargs):
        self.pagina.acoes.append(("fill", self.seletor, texto))


class PaginaTesouraria:
    """Imita a TES01701: lista de contas da localidade e a grade de movimentos por conta."""

    def __init__(self, grades, opcoes=None, saldos=None):
        self.grades = grades
        self.saldos = saldos or {}
        self.opcoes = opcoes if opcoes is not None else [
            {"texto": rotulo, "valor": f"id{codigo}", "inativa": False} for codigo, rotulo in ROTULOS.items()]
        self.conta = ""
        self.acoes = []
        self.periodo_ignorado = None

    def locator(self, seletor):
        return _Locator(self, seletor)

    def wait_for_load_state(self, estado):
        pass

    def evaluate(self, script, arg=None):
        if "f_data1" in script and arg is not None:
            # Grava como `fill` para os testes; `periodo_ignorado` imita o filtro que não fica
            for campo, valor in zip(("#f_data1", "#f_data2"), arg, strict=True):
                if valor:
                    self.acoes.append(("fill", campo, valor))
            return list(self.periodo_ignorado or arg)
        if "tfoot" in script:
            return self.saldos.get(self.conta)
        if "#grid1 tbody tr" in script:
            return [dict(linha) for linha in self.grades.get(self.conta, [])]
        if "select#f_conta option" in script:
            return [dict(o) for o in self.opcoes]
        if '$("#f_conta").val(v)' in script:
            self.conta = arg.removeprefix("id")
            self.acoes.append(("conta", self.conta))
        return None

    def programas(self):
        return [a[2] for a in self.acoes if a[:2] == ("fill", "#f_executar_programa")]


def _extrato(tipo_adm, conta, transacoes, aplicacao=False):
    return {
        "conta_id": "12345-6", "tipo_adm": tipo_adm, "nome_adm": "CENTRAL",
        "localidade_selecionada": f"{tipo_adm} - CENTRAL",
        "tipo_extrato": "APLICACAO" if aplicacao else "CORRENTE",
        "conta_siga_corrente": "" if aplicacao else conta, "conta_siga_aplicacao": conta if aplicacao else "",
        "data_inicial": "01/05/2026", "data_final": "31/05/2026", "transacoes": transacoes,
    }


def _rodar(monkeypatch, lote, grades, lanca=True, troca_falha=(), mes_fechado=False, opcoes=None, saldos=None,
          revisar=False, responder=None, etapa_baixas=None, grava=True, periodo_ignorado=None):
    """Roda `fluxo_automacao` inteiro sem navegador e devolve o que aconteceu."""
    sem_espera = SimpleNamespace(sleep=lambda s: None, time=lambda: 0.0)
    monkeypatch.setattr(siga_bot, "time", sem_espera)
    try:
        monkeypatch.setattr(importlib.import_module("bot.fluxo_extratos"), "time", sem_espera)
    except ModuleNotFoundError:
        pass
    pagina = PaginaTesouraria(grades, opcoes, saldos)
    pagina.periodo_ignorado = periodo_ignorado
    reg = SimpleNamespace(trocas=[], lancamentos=[], rendimentos=[], status=[], telemetria=None)
    reg.previas = []
    callbacks = {"show_dashboard": lambda tel, t: setattr(reg, "telemetria", tel)}
    bot = SigaBot(lote, callbacks=callbacks, revisar_antes_de_lancar=revisar)
    if responder:
        def previa(pendentes, contexto):
            reg.previas.append((pendentes, contexto))
            responder(bot)
        callbacks["request_authorization"] = previa

    monkeypatch.setattr(siga_bot, "sync_playwright", lambda: nullcontext(None))
    monkeypatch.setattr(bot, "_iniciar_navegador", lambda p: (SimpleNamespace(pages=[]), pagina))
    monkeypatch.setattr(bot, "_validar_sessao", lambda page: None)
    monkeypatch.setattr(bot, "_verificar_sessao_ativa", lambda page: None)
    monkeypatch.setattr(bot, "update_status", lambda msg, color=None: reg.status.append(msg))
    if etapa_baixas:
        monkeypatch.setattr(bot, "_etapa_baixas_energia", lambda page, dados, conta: etapa_baixas)

    def trocar(page, tipo, nome, mes):
        reg.trocas.append((tipo, nome, mes))
        return tipo not in troca_falha

    def inserir(destino, page, pendentes):
        destino.append(list(pendentes))
        if mes_fechado:
            raise MesFechadoError(pendentes[0]["data"])
        bot._qtd_injecoes_efetuadas = len(pendentes) if grava else 0
        if lanca:
            pagina.grades.setdefault(pagina.conta, []).extend(_linha(t["data"], t["valor"]) for t in pendentes)

    monkeypatch.setattr(bot, "_ajustar_localidade_competencia", trocar)
    monkeypatch.setattr(bot, "inserir_lancamentos_siga", lambda page, p: inserir(reg.lancamentos, page, p))
    monkeypatch.setattr(bot, "inserir_rendimentos_siga", lambda page, p: inserir(reg.rendimentos, page, p))

    bot.fluxo_automacao()
    reg.pagina = pagina
    return reg


APLIC = {"data": "05/05/2026", "valor": -200.0, "descricao": "APLICACAO FINANCEIRA"}
RESG = {"data": "10/05/2026", "valor": 300.0, "descricao": "RESG.APLIC.FIN"}
PIX = {"data": "12/05/2026", "valor": 50.0, "descricao": "PIX RECEBIDO"}
REND = {"data": "29/05/2026", "valor": 1.23, "descricao": "RENDIMENTOS"}


def _lote_padrao():
    return [
        _extrato("PIA", "10127", [APLIC]),
        _extrato("DR", "10130", [APLIC, RESG, PIX]),
        _extrato("DR", "10396", [REND], aplicacao=True),
    ]


def _grades_padrao():
    return {"10130": [_linha("05/05/2026", -200.0)], "10127": [_linha("05/05/2026", -200.0)]}


def test_lanca_so_o_que_falta_e_troca_localidade_so_quando_muda(monkeypatch):
    reg = _rodar(monkeypatch, _lote_padrao(), _grades_padrao())

    # Lote ordenado por localidade: DR (dois extratos, uma troca) e depois PIA
    assert reg.trocas == [("DR", "CENTRAL", "05/2026"), ("PIA", "CENTRAL", "05/2026")]
    # Cada extrato com lançamento é consultado de novo (conta e período refeitos) na conferência
    assert reg.pagina.programas() == ["TES01701"] * 5
    assert [a[1] for a in reg.pagina.acoes if a[0] == "conta"] == ["10130", "10130", "10396", "10396", "10127"]
    # PIX não é investimento; a aplicação já estava no SIGA
    assert reg.lancamentos == [[RESG]]
    assert reg.rendimentos == [[REND]]
    assert ("fill", "#f_data2", "31/05/2026") in reg.pagina.acoes
    assert reg.telemetria["injecoes"] == 2
    assert reg.telemetria["pendentes"] == 0
    assert reg.telemetria["siga_itens"] == 2


def test_gravado_que_nao_aparece_na_conferencia_nao_e_lancado_de_novo(monkeypatch):
    # 23/10/2026: a conferência leu o mês errado e o robô começou a lançar os 14 itens de novo
    lote = [_extrato("DR", "10130", [RESG])]

    reg = _rodar(monkeypatch, lote, {}, lanca=False)

    assert reg.lancamentos == [[RESG]]
    assert reg.telemetria["pendentes"] == 1
    assert any("não encontrou os 1 lançamento(s) gravado(s)" in s for s in reg.status)
    # A conferência refaz o período do extrato, não reaproveita o filtro padrão da tela
    assert reg.pagina.acoes.count(("fill", "#f_data2", "31/05/2026")) == 2


def test_filtro_que_nao_fica_com_o_periodo_nao_lanca_nada(monkeypatch):
    # O filtro da TES01701 abre no mês atual; se a data não entra, a grade é de outro mês
    lote = [_extrato("DR", "10130", [RESG])]

    reg = _rodar(monkeypatch, lote, {}, periodo_ignorado=["01/10/2026", "31/10/2026"])

    assert reg.lancamentos == []
    assert reg.telemetria["pendentes"] == 1
    assert any("não mostrou o período do extrato" in s and "01/10/2026" in s for s in reg.status)
    assert _resultados(reg)["10130"].situacao == "pendente"


def test_grade_de_outro_mes_nao_lanca_nada(monkeypatch):
    # 23/10/2026: o extrato de setembro foi comparado com a grade de outubro e saiu todo duplicado
    lote = [_extrato("DR", "10130", [RESG])]

    reg = _rodar(monkeypatch, lote, {"10130": [_linha("16/06/2026", 399.34)]})

    assert reg.lancamentos == []
    assert any("fora de 01/05/2026 a 31/05/2026" in s for s in reg.status)


def test_lancamento_que_falhou_sem_gravar_e_tentado_tres_vezes(monkeypatch):
    lote = [_extrato("DR", "10130", [RESG])]

    reg = _rodar(monkeypatch, lote, {}, lanca=False, grava=False)

    assert reg.lancamentos == [[RESG]] * 3
    assert reg.telemetria["pendentes"] == 1
    assert any("não bateram" in s for s in reg.status)


def test_localidade_que_nao_troca_pula_os_extratos_dela(monkeypatch):
    reg = _rodar(monkeypatch, _lote_padrao(), _grades_padrao(), troca_falha=("DR",))

    # A DR é tentada uma vez só; o segundo extrato dela é pulado sem nova troca
    assert reg.trocas == [("DR", "CENTRAL", "05/2026"), ("PIA", "CENTRAL", "05/2026")]
    assert reg.pagina.programas() == ["TES01701"]
    assert reg.lancamentos == [] and reg.rendimentos == []
    assert reg.telemetria["pendentes"] == 4


def test_mes_fechado_nao_retenta_e_pula_o_resto_da_localidade(monkeypatch):
    reg = _rodar(monkeypatch, _lote_padrao(), _grades_padrao(), mes_fechado=True)

    assert reg.lancamentos == [[RESG]]
    assert reg.rendimentos == []
    assert reg.pagina.programas() == ["TES01701"] * 2
    assert reg.telemetria["pendentes"] == 2
    assert any("Meses fechados" in s for s in reg.status)


def _opcao(texto, inativa=False):
    return {"texto": texto, "valor": f"v-{texto.split()[0]}", "inativa": inativa}


def test_conta_ausente_na_localidade_pula_o_extrato_sem_consultar_nem_lancar(monkeypatch):
    lote = [_extrato("DR", "10130", [RESG]), _extrato("PIA", "10127", [APLIC])]
    opcoes = [_opcao("110130 - SICREDI - AG: 0101 CC: 99999-9"),       # contém "10130", mas é outra
              _opcao("10130 - SICREDI - AG: 0101 CC: 12345-6", inativa=True),
              _opcao(ROTULOS["10127"])]

    reg = _rodar(monkeypatch, lote, {}, opcoes=opcoes)

    # A DR é pulada antes de consultar; a PIA segue normalmente
    assert reg.lancamentos == [[APLIC]]
    assert [a for a in reg.pagina.acoes if a[0] == "conta"] == [("conta", "v-10127")] * 2
    assert reg.pagina.acoes.count(("click", '#f_main button[type="submit"].btn-success')) == 2
    assert reg.telemetria["pendentes"] == 1
    assert any("Conta 10130 não encontrada em DR - CENTRAL" in s for s in reg.status)


def _resultados(reg):
    return {r.conta_siga: r for r in reg.telemetria["extratos"]}


def test_prova_real_confere_o_saldo_e_nao_aponta_sobras(monkeypatch):
    lote = [dict(_extrato("DR", "10130", [APLIC, RESG]), saldo_atual=1.0, data_saldo="31/05/2026")]
    grades = {"10130": [_linha("05/05/2026", -200.0)]}

    reg = _rodar(monkeypatch, lote, grades, saldos={"10130": "1,00"})

    r = _resultados(reg)["10130"]
    assert (r.situacao, r.lancados, r.pendentes) == ("conciliado", 1, 0)
    assert r.saldo.status == "confere"
    assert r.sobras == []
    assert any("Prova real: saldo confere (R$ 1,00)" in s for s in reg.status)


def test_prova_real_aponta_diferenca_e_lancamento_sem_par(monkeypatch):
    lote = [dict(_extrato("DR", "10130", [APLIC]), saldo_atual=1.0)]
    grades = {"10130": [_linha("05/05/2026", -200.0), _linha("05/05/2026", -200.0)]}   # duplicado

    reg = _rodar(monkeypatch, lote, grades, saldos={"10130": "-199,00"})

    r = _resultados(reg)["10130"]
    assert r.saldo.status == "diverge"
    assert r.saldo.diferenca == -200.0
    assert [(s.data, s.valor) for s in r.sobras] == [("05/05/2026", -200.0)]
    assert reg.lancamentos == []


def test_extrato_sem_lancamento_novo_so_confere(monkeypatch):
    lote = [dict(_extrato("DR", "10396", [], aplicacao=True), saldo_atual=50.0, movimentos=[])]

    reg = _rodar(monkeypatch, lote, {}, saldos={"10396": "50,00"})

    assert reg.rendimentos == []
    assert _resultados(reg)["10396"].saldo.status == "confere"


def test_periodo_filtrado_nao_confere_o_saldo(monkeypatch):
    lote = [dict(_extrato("DR", "10130", [APLIC]), saldo_atual=1.0, periodo_filtrado=True)]

    reg = _rodar(monkeypatch, lote, {"10130": [_linha("05/05/2026", -200.0)]}, saldos={"10130": "9,99"})

    saldo = _resultados(reg)["10130"].saldo
    assert saldo.status == "nao_conferido"
    assert "filtrado" in saldo.motivo


def test_saldo_do_banco_de_outra_data_nao_e_comparado(monkeypatch):
    lote = [dict(_extrato("DR", "10130", []), saldo_atual=1.0, data_saldo="20/05/2026")]

    reg = _rodar(monkeypatch, lote, {}, saldos={"10130": "1,00"})

    assert _resultados(reg)["10130"].saldo.status == "nao_conferido"


def test_resultado_registra_conta_nao_encontrada_e_mes_fechado(monkeypatch):
    reg = _rodar(monkeypatch, _lote_padrao(), _grades_padrao(), mes_fechado=True)

    situacoes = {(r.conta_siga, r.situacao) for r in reg.telemetria["extratos"]}
    assert situacoes == {("10130", "mes_fechado"), ("10396", "mes_fechado"), ("10127", "conciliado")}


class _EventoSemEspera:
    """Event que não espera de verdade: só diz se já foi liberado."""

    def __init__(self):
        self.liberado = False

    def clear(self):
        self.liberado = False

    def set(self):
        self.liberado = True

    def wait(self, timeout=None):
        return self.liberado


def test_previa_desligada_lanca_sem_perguntar(monkeypatch):
    reg = _rodar(monkeypatch, [_extrato("DR", "10130", [RESG])], {},
                 responder=lambda bot: bot.responder_autorizacao(False))

    assert reg.previas == []
    assert reg.lancamentos == [[RESG]]


def test_previa_autorizada_lanca_e_mostra_a_conta(monkeypatch):
    reg = _rodar(monkeypatch, [_extrato("DR", "10130", [RESG])], {}, revisar=True,
                 responder=lambda bot: bot.responder_autorizacao(True))

    assert reg.previas == [([RESG], {"conta": "10130", "tipo": "lancamentos", "localidade": "DR - CENTRAL"})]
    assert reg.lancamentos == [[RESG]]


def test_previa_recusada_nao_grava_e_segue_para_o_proximo(monkeypatch):
    lote = [_extrato("DR", "10130", [RESG]), _extrato("PIA", "10127", [APLIC])]

    reg = _rodar(monkeypatch, lote, {}, revisar=True, responder=lambda bot: bot.responder_autorizacao(False))

    assert len(reg.previas) == 2
    assert reg.lancamentos == []
    assert reg.telemetria["pendentes"] == 2
    assert {r.situacao for r in reg.telemetria["extratos"]} == {"recusado"}


def test_fechar_o_navegador_durante_a_previa_nao_trava_nem_grava(monkeypatch):
    def fechar(bot):
        bot._evento_autorizacao = _EventoSemEspera()
        bot.browser_aberto = False

    reg = _rodar(monkeypatch, [_extrato("DR", "10130", [RESG]), _extrato("PIA", "10127", [APLIC])], {},
                 revisar=True, responder=fechar)

    assert reg.lancamentos == []
    # O laço para no extrato seguinte porque o navegador foi fechado
    assert len(reg.previas) == 1


def test_baixas_de_energia_entram_no_resultado_do_extrato(monkeypatch):
    baixas = ["resultado fictício"]

    reg = _rodar(monkeypatch, [_extrato("DR", "10130", [RESG])], {}, etapa_baixas=(baixas, False))

    assert reg.telemetria["extratos"][0].baixas == baixas
    assert reg.lancamentos == [[RESG]]


def test_mes_fechado_nas_baixas_pula_a_conciliacao(monkeypatch):
    reg = _rodar(monkeypatch, [_extrato("DR", "10130", [RESG])], {}, etapa_baixas=([], True))

    assert reg.lancamentos == []
    assert [r.situacao for r in reg.telemetria["extratos"]] == ["mes_fechado"]
