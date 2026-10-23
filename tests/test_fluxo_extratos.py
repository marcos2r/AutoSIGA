"""Laço de extratos do SigaBot de ponta a ponta, com uma Caixas e Bancos (TES01701) falsa."""

import importlib
import re
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


class _Opcao:
    def __init__(self, valor, texto):
        self.valor, self.texto = valor, texto

    def text_content(self):
        return self.texto

    def get_attribute(self, nome):
        return self.valor


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

    def count(self):
        return len(self.pagina.opcoes())

    def nth(self, i):
        return self.pagina.opcoes()[i]


class PaginaTesouraria:
    """Imita a TES01701: lista de contas da localidade e a grade de movimentos por conta."""

    def __init__(self, grades):
        self.grades = grades
        self.conta = ""
        self.acoes = []

    def opcoes(self):
        return [_Opcao(f"id{codigo}", rotulo) for codigo, rotulo in ROTULOS.items()]

    def locator(self, seletor):
        return _Locator(self, seletor)

    def wait_for_load_state(self, estado):
        pass

    def evaluate(self, script, arg=None):
        if "#grid1 tbody tr" in script:
            return [dict(linha) for linha in self.grades.get(self.conta, [])]
        escolha = re.search(r'#f_conta"\)\.val\("id(\d+)"\)', script)
        if escolha:
            self.conta = escolha.group(1)
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


def _rodar(monkeypatch, lote, grades, lanca=True, troca_falha=(), mes_fechado=False):
    """Roda `fluxo_automacao` inteiro sem navegador e devolve o que aconteceu."""
    sem_espera = SimpleNamespace(sleep=lambda s: None, time=lambda: 0.0)
    monkeypatch.setattr(siga_bot, "time", sem_espera)
    try:
        monkeypatch.setattr(importlib.import_module("bot.fluxo_extratos"), "time", sem_espera)
    except ModuleNotFoundError:
        pass
    pagina = PaginaTesouraria(grades)
    reg = SimpleNamespace(trocas=[], lancamentos=[], rendimentos=[], status=[], telemetria=None)
    callbacks = {"show_dashboard": lambda tel, t: setattr(reg, "telemetria", tel)}
    bot = SigaBot(lote, callbacks=callbacks)

    monkeypatch.setattr(siga_bot, "sync_playwright", lambda: nullcontext(None))
    monkeypatch.setattr(bot, "_iniciar_navegador", lambda p: (SimpleNamespace(pages=[]), pagina))
    monkeypatch.setattr(bot, "_validar_sessao", lambda page: None)
    monkeypatch.setattr(bot, "_verificar_sessao_ativa", lambda page: None)
    monkeypatch.setattr(bot, "update_status", lambda msg, color=None: reg.status.append(msg))

    def trocar(page, tipo, nome, mes):
        reg.trocas.append((tipo, nome, mes))
        return tipo not in troca_falha

    def inserir(destino, page, pendentes):
        destino.append(list(pendentes))
        if mes_fechado:
            raise MesFechadoError(pendentes[0]["data"])
        bot._qtd_injecoes_efetuadas = len(pendentes)
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
    assert reg.pagina.programas() == ["TES01701"] * 3
    assert [a[1] for a in reg.pagina.acoes if a[0] == "conta"] == ["10130", "10396", "10127"]
    # PIX não é investimento; a aplicação já estava no SIGA
    assert reg.lancamentos == [[RESG]]
    assert reg.rendimentos == [[REND]]
    assert ("fill", "#f_data2", "31/05/2026") in reg.pagina.acoes
    assert reg.telemetria["injecoes"] == 2
    assert reg.telemetria["pendentes"] == 0
    assert reg.telemetria["siga_itens"] == 2


def test_lancamento_que_nao_aparece_na_grade_e_tentado_tres_vezes(monkeypatch):
    lote = [_extrato("DR", "10130", [RESG])]

    reg = _rodar(monkeypatch, lote, {}, lanca=False)

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
