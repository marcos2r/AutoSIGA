"""Página e bot falsos para testar os fluxos do SigaBot sem navegador."""

from types import SimpleNamespace

from bot.siga_bot import SigaBot


class LocatorGravador:
    def __init__(self, pagina, seletor):
        self.pagina = pagina
        self.seletor = seletor

    @property
    def first(self):
        return self

    def count(self):
        return self.pagina.contagens.get(self.seletor, 1)

    def wait_for(self, state="visible", timeout=None):
        # Pop-ups opcionais (ex: "Sim" da competência) não aparecem por padrão
        raise TimeoutError(f"{self.seletor} não apareceu")

    def click(self, **kwargs):
        self.pagina.acoes.append((self.seletor, "click", None))

    def fill(self, texto, **kwargs):
        self.pagina.acoes.append((self.seletor, "fill", texto))

    def type(self, texto, **kwargs):
        self.pagina.acoes.append((self.seletor, "type", texto))

    def set_input_files(self, caminho):
        self.pagina.acoes.append((self.seletor, "upload", caminho))


class PaginaGravadora:
    """Registra o que o bot faz na página; `competencia_fechada` simula o aviso do SIGA."""

    def __init__(self, competencia_fechada=False):
        self.competencia_fechada = competencia_fechada
        self.acoes = []
        self.scripts = []
        self.contagens = {}

    def locator(self, seletor):
        return LocatorGravador(self, seletor)

    def wait_for_load_state(self, estado):
        pass

    def evaluate(self, script, arg=None):
        self.scripts.append(script)
        if "Fechamento de competência" in script:
            return self.competencia_fechada
        return None

    def valores(self, seletor, acao="type"):
        return [v for s, a, v in self.acoes if s == seletor and a == acao]


def criar_bot(monkeypatch, modulo, tipo_lote, dados=None):
    """SigaBot com os helpers de baixo nível trocados por gravadores.

    Returns:
        tuple: (bot, registro) — `registro` guarda Select2, campos, gravações,
        status e capturas de tela na ordem em que aconteceram.
    """
    monkeypatch.setattr(modulo, "time", SimpleNamespace(sleep=lambda s: None))
    registro = SimpleNamespace(select2=[], campos=[], gravacoes=0, status=[], capturas=[], mensagens=[])
    callbacks = {"show_message": lambda *args: registro.mensagens.append(args)}
    bot = SigaBot([], callbacks=callbacks, tipo_lote=tipo_lote)
    bot.browser_aberto = True
    bot.dados_processados = dados or {}

    def gravar():
        registro.gravacoes += 1

    monkeypatch.setattr(bot, "_verificar_sessao_ativa", lambda page: None)
    monkeypatch.setattr(bot, "esperar_loading", lambda page: None)
    monkeypatch.setattr(bot, "selecionar_select2",
                        lambda page, campo, termo, dropdown_is_ajax=True: registro.select2.append((campo, termo)))
    monkeypatch.setattr(bot, "_preencher_campos", lambda page, valores: registro.campos.append(valores))
    monkeypatch.setattr(bot, "_confirmar_gravacao", lambda page, timeout_ms: gravar())
    monkeypatch.setattr(bot, "_capturar_tela_e_log", lambda page, ident: registro.capturas.append(ident))
    monkeypatch.setattr(bot, "update_status", lambda msg, color=None: registro.status.append(msg))
    return bot, registro
