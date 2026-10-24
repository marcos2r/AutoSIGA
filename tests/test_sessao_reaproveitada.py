"""Edge reaproveitado: usa a sessão da aba já logada em vez de voltar ao login do SIGA."""

from bot.sessao import _TELA_CONSULTA, SessaoMixin


class _Locator:
    def __init__(self, pagina, seletor):
        self.pagina, self.seletor = pagina, seletor

    @property
    def first(self):
        return self

    def wait_for(self, state, timeout):
        if not self.pagina.logada:
            raise TimeoutError("barra de rotinas não apareceu")

    def count(self):
        return 0 if self.pagina.logada else 1


class _Pagina:
    def __init__(self, url, logada):
        self.url, self.logada, self.visitas = url, logada, []

    def goto(self, url, wait_until=None):
        self.visitas.append(url)

    def reload(self, **kw):
        raise AssertionError("recarregar pode reenviar um formulário gravado")

    def locator(self, seletor):
        return _Locator(self, seletor)


def test_aba_logada_e_reaproveitada_abrindo_so_tela_de_consulta():
    pagina = _Pagina("https://siga.congregacao.org.br/TES/TES01704.aspx", logada=True)

    assert SessaoMixin._sessao_aberta(pagina) is True
    assert pagina.visitas == [_TELA_CONSULTA]


def test_sessao_expirada_vai_para_o_login():
    assert SessaoMixin._sessao_aberta(_Pagina("https://siga.congregacao.org.br/CTB/CTB00301.aspx", logada=False)) is False


def test_aba_fora_do_siga_nem_tenta():
    pagina = _Pagina("edge://newtab/", logada=True)

    assert SessaoMixin._sessao_aberta(pagina) is False
    assert pagina.visitas == []
