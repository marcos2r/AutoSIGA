import pytest

import bot.siga_helpers as siga_helpers
from bot.siga_bot import SigaBot


class RelogioFalso:
    """Substitui o módulo time no helper: sleep só avança o relógio."""

    def __init__(self):
        self.agora = 0.0

    def monotonic(self):
        return self.agora

    def sleep(self, segundos):
        self.agora += segundos


class LocatorFalso:
    def __init__(self, pagina, seletor):
        self.pagina = pagina
        self.seletor = seletor

    @property
    def first(self):
        return self

    def count(self):
        return self.pagina.contar(self.seletor)

    def text_content(self):
        return self.pagina.texto(self.seletor)

    def get_attribute(self, nome):
        return ""

    def wait_for(self, state="visible", timeout=None):
        if self.seletor.endswith(".select2-input") and not self.pagina.aberto:
            raise TimeoutError("dropdown fechado")

    def click(self, **kwargs):
        if self.seletor.startswith("#s2id_"):
            self.pagina.aberto = True

    def fill(self, texto, **kwargs):
        self.pagina.digitado = texto

    def type(self, texto, **kwargs):
        self.pagina.digitado += texto
        self.pagina.inicio_busca = None if self.pagina.exige_enter else self.pagina.relogio.agora

    def press(self, tecla):
        self.pagina.teclas.append(tecla)
        if self.pagina.exige_enter and self.pagina.inicio_busca is None:
            self.pagina.inicio_busca = self.pagina.relogio.agora
        elif self.pagina.pronto() and self.pagina.opcoes:
            self.pagina.escolhido = self.pagina.opcoes[0]
            self.pagina.aberto = False


class PaginaSelect2:
    """Imita um Select2 do SIGA cujos resultados chegam `atraso` segundos após a busca."""

    def __init__(self, relogio, opcoes, atraso=0.6, exige_enter=False, escolhido=""):
        self.relogio = relogio
        self.opcoes = opcoes
        self.atraso = atraso
        self.exige_enter = exige_enter
        self.escolhido = escolhido
        self.aberto = False
        self.digitado = ""
        self.inicio_busca = None
        self.teclas = []

    def locator(self, seletor):
        return LocatorFalso(self, seletor)

    def evaluate(self, script, arg=None):
        if "select2('close')" in script:
            self.aberto = False

    def pronto(self):
        return self.inicio_busca is not None and self.relogio.agora >= self.inicio_busca + self.atraso

    def contar(self, seletor):
        if not self.aberto or not self.digitado:
            return 0
        if seletor.endswith(".select2-searching"):
            return 0 if self.pronto() else 1
        if seletor.endswith("li.select2-result-selectable"):
            return len(self.opcoes) if self.pronto() else 0
        if seletor.endswith(".select2-no-results"):
            return 1 if self.pronto() and not self.opcoes else 0
        return 0

    def texto(self, seletor):
        if seletor.endswith(".select2-chosen"):
            return self.escolhido
        if seletor.endswith(".select2-searching"):
            return "Tecle Enter para buscar" if self.inicio_busca is None else "Buscando..."
        if seletor.endswith("li.select2-result-selectable"):
            return self.opcoes[0]
        return ""


@pytest.fixture
def relogio(monkeypatch):
    relogio = RelogioFalso()
    monkeypatch.setattr(siga_helpers, "time", relogio)
    return relogio


def _bot():
    return SigaBot([], callbacks={}, tipo_lote="extrato")


def test_seleciona_assim_que_o_resultado_chega(relogio):
    pagina = PaginaSelect2(relogio, ["4100 - RENDA SOBRE APLICAÇÃO FINANCEIRA"], atraso=0.6)

    _bot().selecionar_select2(pagina, "f_receita", "4100")

    assert pagina.escolhido.startswith("4100")
    # As pausas fixas antigas somavam 3,2 s no caso AJAX
    assert relogio.agora < 1.0


def test_pressiona_enter_quando_o_siga_pede(relogio):
    pagina = PaginaSelect2(relogio, ["10130 - CONTA CORRENTE"], exige_enter=True)

    _bot().selecionar_select2(pagina, "f_conta", "10130")

    assert pagina.escolhido == "10130 - CONTA CORRENTE"
    # Um Enter dispara a busca e outro confirma a opção
    assert pagina.teclas == ["Enter", "Enter"]


def test_nao_reabre_quando_o_valor_ja_esta_escolhido(relogio):
    pagina = PaginaSelect2(relogio, [], escolhido="TRANSF. BANCÁRIA")

    _bot().selecionar_select2(pagina, "f_formapagamento", "TRANSF. BANCARIA", dropdown_is_ajax=False)

    assert not pagina.aberto
    assert relogio.agora == 0.0


def test_falha_apos_tres_tentativas_sem_a_opcao(relogio, monkeypatch):
    pagina = PaginaSelect2(relogio, ["999 - OUTRA CONTA"])
    bot = _bot()
    capturas = []
    monkeypatch.setattr(bot, "_capturar_tela_e_log", lambda page, ident: capturas.append(ident))

    with pytest.raises(RuntimeError, match="após 3 tentativas"):
        bot.selecionar_select2(pagina, "f_conta", "10130")

    assert capturas == ["select2_f_conta"]


def test_espera_desiste_no_limite_quando_a_busca_nao_volta(relogio):
    pagina = PaginaSelect2(relogio, ["10130 - CONTA"], atraso=999)
    pagina.aberto = True
    input_search = pagina.locator("#select2-drop:visible .select2-input")
    input_search.type("10130")

    assert _bot()._aguardar_resultados_select2(pagina, input_search, "10130", timeout=10.0) is False
    assert 10.0 <= relogio.agora < 10.5


def test_sem_resultado_so_encerra_apos_espera_minima(relogio):
    pagina = PaginaSelect2(relogio, [], atraso=0.0)
    pagina.aberto = True
    input_search = pagina.locator("#select2-drop:visible .select2-input")
    input_search.type("XYZ")

    assert _bot()._aguardar_resultados_select2(pagina, input_search, "XYZ", timeout=10.0) is True
    assert relogio.agora >= siga_helpers.ESPERA_MIN_SEM_RESULTADO
