"""
Botão primário (azul cheio) que troca o fundo quando é desabilitado.

O CTkButton só troca a cor do texto ao desabilitar; o fundo azul continua, e o texto
cinza some nele (visto em 23/11/2026 no "Conciliar no SIGA"). Aqui o desabilitado vira
cinza-claro com texto cinza (4,6:1), com cara de "ainda não dá para clicar".
"""

import customtkinter as ctk

from ui import tema


class BotaoPrimario(ctk.CTkButton):
    """CTkButton azul do SIGA que ajusta o fundo ao estado (normal ou disabled)."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", tema.AZUL_NAVBAR)
        kwargs.setdefault("hover_color", tema.AZUL_NAVBAR_HOVER)
        kwargs.setdefault("text_color", tema.BRANCO)
        kwargs.setdefault("text_color_disabled", tema.CINZA_TEXTO)
        self._fundo_ativo = kwargs["fg_color"]
        super().__init__(master, **kwargs)
        self._pintar(kwargs.get("state", "normal"))

    def configure(self, require_redraw=False, **kwargs):
        """Repassa ao CTkButton e, se o estado mudou, troca o fundo junto."""
        if "fg_color" in kwargs and kwargs.get("state") != "disabled":
            self._fundo_ativo = kwargs["fg_color"]
        super().configure(require_redraw=require_redraw, **kwargs)
        if "state" in kwargs:
            self._pintar(kwargs["state"])

    def _pintar(self, estado):
        fundo = tema.CINZA_HOVER if estado == "disabled" else self._fundo_ativo
        super().configure(fg_color=fundo)
