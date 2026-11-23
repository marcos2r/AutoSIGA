"""
Painel da aba Energia (View).

Configuração do e-mail da Energisa, atalhos para os cadastros e a lista de
faturas pendentes de mapeamento de UC.
"""

from tkinter import messagebox

import customtkinter as ctk

from models.faturas_pendentes import FaturasPendentes
from ui import tema
from ui.modais_energia import ModalLocalidades, ModalMapeamentoUC, abrir_pdf


class PanelEnergia(ctk.CTkFrame):
    """
    Aba dedicada para configuração, controle de e-mail e cadastro das Localidades da Energisa.
    """
    def __init__(self, parent, config_manager, callback_log, callback_topmost, trigger_bot_callback):
        super().__init__(parent, fg_color=tema.BRANCO)
        self.config_manager = config_manager
        self.callback_log = callback_log
        self.callback_topmost = callback_topmost
        self.trigger_bot_callback = trigger_bot_callback
        self.pendentes = FaturasPendentes(config_manager)

        self.construir_widgets()
        self.carregar_dados()
        self.atualizar_pendentes()

    def construir_widgets(self):
        # Título
        lbl_tit = ctk.CTkLabel(self, text="Provisionamento Automático de Energia (Energisa)", font=("Open Sans", 13, "bold"), text_color=tema.AZUL_TITULO)
        lbl_tit.pack(pady=(10, 5))

        # Configurações do E-mail (Grid)
        frame_config = ctk.CTkFrame(self, fg_color=tema.FUNDO_PAINEL, border_width=1, border_color=tema.CINZA_BORDA, corner_radius=6)
        frame_config.pack(padx=15, pady=5, fill="x")

        ctk.CTkLabel(frame_config, text="E-mail (Gmail):", font=("Open Sans", 11)).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        # Placeholder neutro: um e-mail real ali parecia valor já preenchido
        self.entry_email = ctk.CTkEntry(frame_config, placeholder_text="nome@gmail.com", width=250, height=28, font=(tema.FONTE, 12))
        self.entry_email.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.entry_email.bind("<FocusOut>", self.salvar_dados_email)
        self.entry_email.bind("<Return>", self.salvar_dados_email)

        secundario = dict(font=(tema.FONTE, 12), fg_color=tema.BRANCO, hover_color=tema.CINZA_HOVER,
                          text_color=tema.AZUL_NAVBAR, border_width=1, border_color=tema.CINZA_BORDA)
        btn_save_cfg = ctk.CTkButton(
            frame_config, text="Salvar e-mail", width=120, height=28, command=self.salvar_dados_email, **secundario
        )
        btn_save_cfg.grid(row=0, column=2, padx=5, pady=5, sticky="e")

        # Cadastros de apoio (Localidades e UCs): secundários, para não competir com a ação principal
        frame_tabelas = ctk.CTkFrame(self, fg_color="transparent")
        frame_tabelas.pack(padx=15, pady=10, fill="x")

        self.btn_locs = ctk.CTkButton(
            frame_tabelas, text="Cadastrar localidades", height=32, command=self.abrir_localidades, **secundario
        )
        self.btn_locs.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_ucs = ctk.CTkButton(
            frame_tabelas, text="Mapear UCs", height=32, command=self.abrir_ucs, **secundario
        )
        self.btn_ucs.pack(side="right", fill="x", expand=True, padx=5)

        # Botão Importar Faturas (ancorado embaixo para continuar visível mesmo com pendências em telas menores)
        self.btn_importar = ctk.CTkButton(
            self, text="Buscar e lançar contas de energia", font=("Open Sans", 14, "bold"),
            fg_color=tema.AZUL_NAVBAR, hover_color=tema.AZUL_NAVBAR_HOVER, height=40, command=self.iniciar_importacao_energia
        )
        self.btn_importar.pack(side="bottom", padx=15, pady=10, fill="x")

        # Faturas pendentes de mapeamento (só aparece quando há alguma)
        self.frame_pendentes = ctk.CTkFrame(self, fg_color=tema.AMARELO_FUNDO, border_width=1, border_color=tema.AMARELO_BORDA, corner_radius=6)
        self.lbl_pendentes = ctk.CTkLabel(self.frame_pendentes, text="", font=("Open Sans", 12, "bold"), text_color=tema.AMARELO_TEXTO)
        self.lbl_pendentes.pack(padx=10, pady=(8, 0), anchor="w")
        ctk.CTkLabel(
            self.frame_pendentes, text="Clique em Buscar e Lançar para mapear a UC de cada uma.",
            font=("Open Sans", 10), text_color=tema.CINZA_TEXTO
        ).pack(padx=10, anchor="w")
        self.scroll_pendentes = ctk.CTkScrollableFrame(self.frame_pendentes, fg_color="transparent", height=80)
        self.scroll_pendentes.pack(padx=5, pady=(4, 8), fill="both", expand=True)

    def atualizar_pendentes(self):
        """Redesenha a lista de faturas pendentes a partir do config.json."""
        for widget in self.scroll_pendentes.winfo_children():
            widget.destroy()

        faturas = self.pendentes.listar()
        if not faturas:
            self.frame_pendentes.pack_forget()
            return

        self.lbl_pendentes.configure(text=f"{len(faturas)} fatura(s) aguardando mapeamento de UC")
        self.frame_pendentes.pack(padx=15, pady=(0, 5), fill="both", expand=True)

        for fat in faturas:
            linha = ctk.CTkFrame(self.scroll_pendentes, fg_color=tema.BRANCO, border_width=1, border_color=tema.CINZA_BORDA, corner_radius=4)
            linha.pack(fill="x", pady=2, padx=2)

            valor = f"R$ {float(fat.get('valor') or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            texto = f"UC {fat.get('uc', '')}  ·  Ref. {fat.get('referencia', '')}  ·  {valor}  ·  Venc. {fat.get('vencimento', '')}"
            if fat.get("origem"):
                texto += f"  ·  {fat['origem']}"
            ctk.CTkLabel(linha, text=texto, font=("Open Sans", 11), text_color=tema.TEXTO, anchor="w").pack(side="left", padx=8, pady=4, fill="x", expand=True)

            ctk.CTkButton(
                linha, text="Descartar", font=("Open Sans", 10),
                fg_color=tema.VERMELHO_TEXTO, hover_color=tema.VERMELHO_HOVER, width=70, height=22,
                command=lambda f=fat: self.descartar_pendente(f)
            ).pack(side="right", padx=(4, 8), pady=4)

            ctk.CTkButton(
                linha, text="Ver PDF", font=("Open Sans", 10),
                fg_color=tema.AZUL_NAVBAR, hover_color=tema.AZUL_NAVBAR_HOVER, width=60, height=22,
                command=lambda f=fat: abrir_pdf(f.get("caminho_arquivo", ""), self)
            ).pack(side="right", padx=4, pady=4)

    def descartar_pendente(self, fatura):
        """Descarta de vez uma fatura pendente, após confirmação do usuário."""
        confirmar = messagebox.askyesno(
            "Descartar fatura",
            f"A fatura da UC {fatura.get('uc', '')} (ref. {fatura.get('referencia', '')}) não será lançada no SIGA "
            "e não será perguntada de novo.\n\nDeseja descartá-la?",
            parent=self
        )
        if confirmar:
            self.pendentes.descartar(fatura)
            self.atualizar_pendentes()

    def carregar_dados(self):
        cfg = self.config_manager.get_email_config()
        self.entry_email.insert(0, cfg.get("email", ""))
        self._email_salvo = cfg.get("email", "")

    def salvar_dados_email(self, event=None):
        """Grava o e-mail do Gmail.

        Pelo botão, avisa se estiver vazio. Ao sair do campo ou teclar Enter (``event``),
        salva em silêncio só o que mudou e for um e-mail: ninguém precisa lembrar de clicar.
        """
        email_str = self.entry_email.get().strip()
        if event is not None:
            if "@" not in email_str or email_str == self._email_salvo:
                return
        elif not email_str:
            messagebox.showerror("Erro", "Informe o e-mail do Gmail.", parent=self)
            return

        self.config_manager.salvar_email_config(email_str, "imap.gmail.com")
        self._email_salvo = email_str
        self.callback_log(f"E-mail das faturas de energia salvo: {email_str}", tema.VERDE_TEXTO)

    def abrir_localidades(self):
        ModalLocalidades(self.winfo_toplevel(), self.config_manager)

    def abrir_ucs(self):
        ModalMapeamentoUC(self.winfo_toplevel(), self.config_manager)

    def iniciar_importacao_energia(self):
        self.trigger_bot_callback()
