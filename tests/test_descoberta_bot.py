"""Descoberta de contas com uma página falsa do SIGA (sem navegador)."""

from types import SimpleNamespace

import pytest

import bot.descoberta_contas as descoberta
import bot.sessao as sessao
from bot.siga_bot import SigaBot

ADM = "ADM - CENTRAL - SP"
DR = "DR - CENTRAL"
PIA = "PIA - CENTRAL"

GRADE_CTB = {
    "cabecalho": ["Cód. Reduzido", "Cód. Contábil", "Nome", "Localidade", "Cust", "TES", "CTB", "Status"],
    "linhas": [
        ["101 30", "1.1.1.02.01", "SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO", ADM, "", "S", "S", "Ativo"],
        ["103 96", "1.1.1.03.01", "SICREDI - AG: 0101 CC: 12345-6 APLICACAO", ADM, "", "S", "S", "Ativo"],
        ["101 27", "1.1.1.02.02", "SICREDI - AG: 0101 CC: 22222-2 DR", DR, "", "S", "S", "Ativo"],
    ],
}

CONTAS_TES = {
    ADM: [{"texto": "1000 - CAIXA GERAL", "inativa": False},
          {"texto": "10130 - SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO", "inativa": False},
          {"texto": "10396 - SICREDI - AG:0101 CC:123456 APLICACAO", "inativa": False},
          {"texto": "10127 - SICREDI - AG: 0101 CC: 22222-2 DR", "inativa": False},
          {"texto": "10199 - SICREDI - AG: 0101 CC: 99999-9 ANTIGA", "inativa": True}],
    DR: [{"texto": "10127 - SICREDI - AG: 0101 CC: 22222-2 DR", "inativa": False},
         {"texto": "10304 - SICREDI - AG: 0101 CC: 22222-2 APLICACAO", "inativa": False}],
}


class _Locator:
    def __init__(self, pagina, seletor):
        self.pagina = pagina
        self.seletor = seletor
        self.first = self

    def wait_for(self, state="visible", timeout=None):
        if self.seletor == "#grid1" and not self.pagina.acesso_ctb:
            raise TimeoutError("grade ausente")
        if self.seletor == "select#f_conta" and self.pagina.localidade not in self.pagina.contas_tes:
            raise TimeoutError("sem contas")

    def click(self, **kwargs):
        self.pagina.cliques.append(self.seletor)

    def text_content(self):
        if self.seletor == "li.green span.user-info":
            return f"USUARIO\n{self.pagina.localidade}"
        return self.pagina.competencia


class PaginaSiga:
    """Imita o SIGA: CTB00301 com ou sem acesso, TES01701 por localidade e o cabeçalho."""

    def __init__(self, acesso_ctb=True, localidade=ADM, contas_tes=None, opcoes_modal=(ADM, DR, PIA, "SEC - CENTRAL")):
        self.acesso_ctb = acesso_ctb
        self.localidade = localidade
        self.competencia = "10/2026"
        self.contas_tes = CONTAS_TES if contas_tes is None else contas_tes
        self.opcoes_modal = list(opcoes_modal)
        self.url = f"{descoberta.URL_SIGA}/SIS/SIS99908.aspx"
        self.visitas = []
        self.cliques = []
        self.keyboard = SimpleNamespace(press=lambda tecla: None)

    def goto(self, url):
        self.visitas.append(url)
        sem_acesso = "CTB00301" in url and not self.acesso_ctb
        self.url = f"{descoberta.URL_SIGA}/SIS/SIS99908.aspx" if sem_acesso else url

    def wait_for_load_state(self, estado):
        pass

    def locator(self, seletor):
        return _Locator(self, seletor)

    def evaluate(self, script, arg=None):
        if "fnFilter" in script:
            return True
        if "fnRecordsDisplay" in script:
            return {"processando": False, "linhas": 3, "total": 3}
        if "thead th" in script:
            return GRADE_CTB
        if "f_estabelecimento" in script:
            return self.opcoes_modal
        if "f_conta" in script:
            return self.contas_tes.get(self.localidade, [])
        return None


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setattr(descoberta, "time", SimpleNamespace(sleep=lambda s: None))
    registro = SimpleNamespace(status=[], catalogos=[], trocas=[], capturas=[])
    b = SigaBot([], callbacks={"on_catalogo": registro.catalogos.append}, tipo_lote="descoberta")
    b.browser_aberto = True
    monkeypatch.setattr(b, "update_status", lambda msg, color=None: registro.status.append(msg))
    monkeypatch.setattr(b, "esperar_loading", lambda page: None)
    monkeypatch.setattr(b, "_capturar_tela_e_log", lambda page, ident: registro.capturas.append(ident))
    b.registro = registro
    return b


def _trocar_contexto(bot, pagina, sem_acesso=(), erro_em=None):
    """Substitui a troca de localidade: registra e muda o cabeçalho da página falsa."""
    def ajustar(page, tipo, nome, mes, mudar_padrao=True):
        loc = f"{tipo} - {nome}"
        bot.registro.trocas.append((loc, mes, mudar_padrao))
        if loc == erro_em:
            raise RuntimeError("SIGA caiu")
        if loc in sem_acesso:
            return False
        pagina.localidade = loc
        if mes:
            pagina.competencia = mes
        return True
    bot._ajustar_localidade_competencia = ajustar


def test_com_acesso_a_contabilidade_le_tudo_sem_trocar_localidade(bot):
    pagina = PaginaSiga(acesso_ctb=True)
    _trocar_contexto(bot, pagina)

    catalogo = bot._fluxo_descoberta(pagina)

    assert catalogo.fonte == "CTB00301"
    assert [(c.codigo, c.localidade) for c in catalogo.contas] == [
        ("10130", ADM), ("10396", ADM), ("10127", DR)]
    assert bot.registro.catalogos == [catalogo]
    assert bot.registro.trocas == []
    assert not any("TES01701" in u for u in pagina.visitas)


def test_sem_acesso_a_contabilidade_percorre_a_tesouraria_e_restaura(bot):
    pagina = PaginaSiga(acesso_ctb=False)
    _trocar_contexto(bot, pagina)

    catalogo = bot._fluxo_descoberta(pagina)

    assert catalogo.fonte == "TES01701"
    # 10127 aparece na ADM e na DR; fica na DR, dona da aplicação da mesma CC. Caixa fica de fora.
    assert sorted((c.codigo, c.localidade, c.ativa) for c in catalogo.contas) == [
        ("10127", DR, True), ("10130", ADM, True), ("10199", ADM, False),
        ("10304", DR, True), ("10396", ADM, True)]
    # PIA sem contas legíveis vai para "sem acesso"; SEC não é visitada
    assert catalogo.localidades_sem_acesso == [PIA]
    # Nunca marca "mudar padrão" e volta ao contexto original no fim
    assert all(mudar is False for _, _, mudar in bot.registro.trocas)
    assert bot.registro.trocas[-1] == (ADM, "10/2026", False)
    assert pagina.localidade == ADM


def test_localidade_que_nao_troca_vai_para_sem_acesso(bot):
    pagina = PaginaSiga(acesso_ctb=False)
    _trocar_contexto(bot, pagina, sem_acesso=(DR,))

    catalogo = bot._fluxo_descoberta(pagina)

    assert DR in catalogo.localidades_sem_acesso
    assert {c.localidade for c in catalogo.contas} == {ADM}
    assert pagina.localidade == ADM


def test_contexto_e_restaurado_mesmo_com_excecao(bot):
    pagina = PaginaSiga(acesso_ctb=False)
    _trocar_contexto(bot, pagina, erro_em=PIA)

    bot._fluxo_descoberta(pagina)

    assert bot.registro.trocas[-1] == (ADM, "10/2026", False)
    assert pagina.localidade == ADM
    assert "descoberta_tesouraria" in bot.registro.capturas


def test_falha_ao_restaurar_avisa_o_usuario(bot):
    pagina = PaginaSiga(acesso_ctb=False)
    _trocar_contexto(bot, pagina)
    original = bot._ajustar_localidade_competencia

    def ajustar(page, tipo, nome, mes, mudar_padrao=True):
        return False if mes else original(page, tipo, nome, mes, mudar_padrao)
    bot._ajustar_localidade_competencia = ajustar

    bot._fluxo_descoberta(pagina)

    assert any("Troque a localidade manualmente" in s for s in bot.registro.status)


def test_sem_ler_o_contexto_nao_troca_nada(bot):
    pagina = PaginaSiga(acesso_ctb=False, localidade="")
    _trocar_contexto(bot, pagina)

    assert bot._fluxo_descoberta(pagina) is None
    assert bot.registro.trocas == []
    assert bot.registro.catalogos == []


class _PaginaModal:
    """Registra os seletores e o argumento do JS da troca de localidade."""

    def __init__(self):
        self.seletores = []
        self.args = []

    def locator(self, seletor):
        self.seletores.append(seletor)
        return SimpleNamespace(click=lambda **kw: None, wait_for=lambda **kw: None,
                               evaluate=lambda js: None, first=SimpleNamespace(
                                   click=lambda **kw: None, wait_for=lambda **kw: None, evaluate=lambda js: None))

    def evaluate(self, script, arg=None):
        self.args.append(arg)

    def wait_for_load_state(self, estado):
        pass


@pytest.mark.parametrize("mudar_padrao", [True, False])
def test_troca_usa_o_formulario_da_localidade(monkeypatch, mudar_padrao):
    monkeypatch.setattr(sessao, "time", SimpleNamespace(sleep=lambda s: None))
    b = SigaBot([], callbacks={})
    monkeypatch.setattr(b, "update_status", lambda *a: None)
    monkeypatch.setattr(SigaBot, "_contexto_ativo_confere", staticmethod(lambda *a: True))
    pagina = _PaginaModal()

    assert b._ajustar_localidade_competencia(pagina, "dr", "central", "", mudar_padrao=mudar_padrao)

    botao = [s for s in pagina.seletores if "Confirmar" in s]
    assert botao and all('select[name="f_estabelecimento"]' in s for s in botao)
    # Valores vão como argumento do JS, e "mudar padrão" segue o parâmetro
    assert pagina.args == [["DR", "CENTRAL", "", mudar_padrao]]
