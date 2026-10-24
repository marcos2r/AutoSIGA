import bot.siga_helpers as siga_helpers
from bot.siga_bot import SigaBot


class LocatorFalso:
    def __init__(self, pagina, seletor):
        self.pagina = pagina
        self.seletor = seletor

    @property
    def first(self):
        return self

    def wait_for(self, state="visible", timeout=None):
        self.pagina.esperas.append((self.seletor, state))
        if self.seletor.startswith(".modal.in"):
            aberta = self.pagina.modal_aberta
            if (state == "visible" and not aberta) or (state == "hidden" and aberta):
                raise TimeoutError(f"{self.seletor} não ficou {state}")

    def evaluate(self, script):
        self.pagina.cliques += 1
        # Os primeiros cliques podem cair na animação de abertura e ser ignorados
        if self.pagina.cliques > self.pagina.cliques_ignorados:
            self.pagina.modal_aberta = False


class PaginaGravacao:
    """Imita a modal "Ok" que o SIGA mostra depois de gravar um lançamento."""

    def __init__(self, modal_aberta=True, cliques_ignorados=0):
        self.modal_aberta = modal_aberta
        self.cliques_ignorados = cliques_ignorados
        self.cliques = 0
        self.esperas = []

    def locator(self, seletor):
        return LocatorFalso(self, seletor)

    def evaluate(self, script):
        pass

    def wait_for_function(self, script, timeout=None):
        # esperar_loading: todas as camadas .blockUI escondidas
        if ".blockUI" in script:
            self.esperas.append((".blockUI", "hidden"))


def _bot(monkeypatch):
    bot = SigaBot([], callbacks={}, tipo_lote="extrato")
    monkeypatch.setattr(siga_helpers.time, "sleep", lambda s: None)
    return bot


def test_clica_ok_e_espera_o_loading(monkeypatch):
    pagina = PaginaGravacao()

    _bot(monkeypatch)._confirmar_gravacao(pagina, timeout_ms=10000)

    assert pagina.cliques == 1
    assert not pagina.modal_aberta
    assert (".blockUI", "hidden") in pagina.esperas


def test_clica_de_novo_quando_o_primeiro_clique_e_ignorado(monkeypatch):
    pagina = PaginaGravacao(cliques_ignorados=1)

    _bot(monkeypatch)._confirmar_gravacao(pagina, timeout_ms=10000)

    assert pagina.cliques == 2
    assert not pagina.modal_aberta


def test_sem_modal_de_sucesso_segue_sem_erro(monkeypatch):
    pagina = PaginaGravacao(modal_aberta=False)

    _bot(monkeypatch)._confirmar_gravacao(pagina, timeout_ms=10000)

    assert pagina.cliques == 0
    assert (".blockUI", "hidden") in pagina.esperas
