"""
Faixa "contas do SIGA" do lote de extratos: estado do catálogo, Buscar no SIGA e
Confirmar sugestões.

A descoberta roda numa thread com o SigaBot (tipo_lote="descoberta"); o catálogo volta
pelo callback `on_catalogo` e só é gravado e aplicado aos cards na thread da UI.
"""

import logging
import threading
from datetime import datetime

import customtkinter as ctk

from bot.siga_bot import SigaBot
from controllers.estado_card import EDITADO, NAO_ENCONTRADO, PENDENTE, SUGERIDO
from ui import tema

_NOME_FONTE = {"CTB00301": "Plano de Contas", "TES01701": "Caixas e Bancos"}


class CatalogoSigaMixin:
    """Liga o catálogo de contas do SIGA ao lote de cards da janela principal."""

    def construir_faixa_catalogo(self, master, depois_de):
        """Cria a faixa (oculta até haver cards), logo abaixo do widget `depois_de`."""
        self._faixa_ancora = depois_de
        self.frame_faixa = ctk.CTkFrame(master, corner_radius=6, border_width=1)
        self.lbl_faixa = ctk.CTkLabel(self.frame_faixa, text="", font=(tema.FONTE, 12), justify="left",
                                      anchor="w", wraplength=480)
        self.lbl_faixa.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        self.btn_confirmar_sugestoes = ctk.CTkButton(
            self.frame_faixa, text="Confirmar sugestões", height=30, font=(tema.FONTE, 12, "bold"),
            fg_color=tema.AZUL_NAVBAR, hover_color=tema.AZUL_NAVBAR_HOVER, text_color=tema.BRANCO,
            command=self.confirmar_sugestoes)
        self.btn_buscar_siga = ctk.CTkButton(
            self.frame_faixa, text="Buscar no SIGA", height=30, font=(tema.FONTE, 12),
            fg_color=tema.BRANCO, hover_color=tema.CINZA_HOVER, text_color=tema.AZUL_NAVBAR,
            border_width=1, border_color=tema.CINZA_BORDA, command=self.iniciar_descoberta_contas)
        self.btn_buscar_siga.pack(side="right", padx=(4, 10), pady=6)

    def atualizar_faixa_catalogo(self):
        """Mostra o estado do catálogo e as ações que fazem sentido para o lote atual."""
        cards = getattr(self, "cards_lote", [])
        if not cards:
            self.frame_faixa.pack_forget()
            return

        catalogo = self.config_manager.get_catalogo()
        estados = [c.estado.chave for c in cards if c.estado]
        faltando = sum(1 for e in estados if e in (PENDENTE, NAO_ENCONTRADO))
        a_confirmar = sum(1 for e in estados if e in (SUGERIDO, EDITADO))

        if catalogo.vazio:
            texto, aviso = "As contas do SIGA ainda não foram lidas. Busque no SIGA para preencher os cards sozinho.", True
        elif faltando:
            texto = f"{faltando} conta(s) sem correspondência no catálogo do SIGA."
            if self.config_manager.catalogo_vencido(catalogo):
                texto += " O catálogo tem mais de 30 dias: busque de novo."
            aviso = True
        else:
            texto, aviso = f"Contas do SIGA lidas em {self._data_br(catalogo.lido_em)} " \
                           f"({_NOME_FONTE.get(catalogo.fonte, catalogo.fonte)}).", False
        if catalogo.localidades_sem_acesso:
            texto += f" Sem acesso a: {', '.join(catalogo.localidades_sem_acesso)}."

        fundo, cor = (tema.AMARELO_FUNDO, tema.AMARELO_TEXTO) if aviso else (tema.AZUL_INFO_FUNDO, tema.AZUL_INFO_TEXTO)
        self.frame_faixa.configure(fg_color=fundo, border_color=cor)
        self.lbl_faixa.configure(text=texto, text_color=cor, fg_color=fundo)
        self.btn_buscar_siga.configure(text="Buscar no SIGA" if aviso else "Atualizar contas do SIGA")

        if a_confirmar:
            self.btn_confirmar_sugestoes.configure(text=f"Confirmar sugestões ({a_confirmar})")
            self.btn_confirmar_sugestoes.pack(side="right", padx=4, pady=6, before=self.btn_buscar_siga)
        else:
            self.btn_confirmar_sugestoes.pack_forget()
        if not self.frame_faixa.winfo_ismapped():
            self.frame_faixa.pack(fill="x", padx=15, pady=(0, 4), after=self._faixa_ancora)

    @staticmethod
    def _data_br(iso):
        try:
            return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
        except ValueError:
            return "data desconhecida"

    def confirmar_sugestoes(self):
        """Confirma de uma vez os cards sugeridos ou alterados que estão válidos."""
        for card in self.cards_lote:
            if card.estado and card.estado.chave in (SUGERIDO, EDITADO):
                card.confirmar()
        self.validar_lote_e_atualizar_botoes()

    def iniciar_descoberta_contas(self):
        """Abre o SIGA em segundo plano e lê as contas bancárias (somente leitura)."""
        if not self.verificar_e_solicitar_credenciais():
            return
        if getattr(self, "bot_instance", None) and getattr(self.bot_instance, "browser_aberto", False):
            self.atualizar_status("Aguarde o robô terminar antes de buscar as contas.", tema.AMARELO_TEXTO)
            return

        self.btn_buscar_siga.configure(state="disabled", text="Buscando no SIGA...")
        self.atualizar_status("Abrindo o SIGA para ler as contas bancárias...", tema.AZUL_TITULO)
        self.progress_bar.set(0.0)
        callbacks = {
            "update_status": self.atualizar_status,
            "update_progress": lambda val: self.after(0, lambda: self.progress_bar.set(val)),
            "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
            "on_catalogo": lambda cat: self.after(0, lambda: self.receber_catalogo(cat)),
            "on_finish": lambda: self.after(0, self._fim_descoberta),
        }
        self.bot_instance = SigaBot([], callbacks, tipo_lote="descoberta")
        threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

    def receber_catalogo(self, catalogo):
        """Grava o catálogo lido e refaz as sugestões dos cards ainda não confirmados."""
        try:
            self.config_manager.salvar_catalogo(catalogo)
            catalogo = self.config_manager.get_catalogo()
            for card in self.cards_lote:
                card.aplicar_catalogo(catalogo)
        except Exception as e:
            logging.error(f"Erro ao aplicar o catálogo de contas: {e}", exc_info=True)
            self.atualizar_status(f"Erro ao aplicar as contas do SIGA: {e}", tema.VERMELHO_TEXTO)
        self.validar_lote_e_atualizar_botoes()

    def _fim_descoberta(self):
        self.btn_buscar_siga.configure(state="normal")
        self.atualizar_faixa_catalogo()
