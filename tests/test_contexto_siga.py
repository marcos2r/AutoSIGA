from bot.siga_bot import SigaBot


class _Elemento:
    def __init__(self, texto):
        self.texto = texto
        self.first = self

    def text_content(self):
        return self.texto


class PaginaCabecalho:
    """Imita o cabeçalho do SIGA com a localidade e o mês de trabalho ativos."""

    def __init__(self, localidade, competencia):
        self.textos = {'li.green span.user-info': localidade, 'span#f_competencianome': competencia}

    def locator(self, seletor):
        return _Elemento(self.textos[seletor])


def test_contexto_confere_quando_localidade_e_mes_batem():
    pagina = PaginaCabecalho("DOURADOS\nADM - DOURADOS - MS", " 08/2026 ")
    assert SigaBot._contexto_ativo_confere(pagina, "ADM", "DOURADOS - MS", "08/2026")


def test_contexto_diverge_quando_mes_nao_foi_trocado():
    pagina = PaginaCabecalho("ADM - DOURADOS - MS", "07/2026")
    assert not SigaBot._contexto_ativo_confere(pagina, "ADM", "DOURADOS - MS", "08/2026")


def test_contexto_diverge_quando_localidade_e_outra():
    pagina = PaginaCabecalho("BR 10-0054 - VILA PLANALTO", "08/2026")
    assert not SigaBot._contexto_ativo_confere(pagina, "ADM", "DOURADOS - MS", "08/2026")


def test_sem_mes_alvo_confere_so_a_localidade():
    pagina = PaginaCabecalho("ADM - DOURADOS - MS", "05/2026")
    assert SigaBot._contexto_ativo_confere(pagina, "adm", "dourados - ms", "")
