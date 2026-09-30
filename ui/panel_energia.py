"""
Painel da aba Energia (View).

Configuração do e-mail da Energisa, atalhos para os cadastros e a lista de
faturas pendentes de mapeamento de UC.
"""

from tkinter import messagebox

import customtkinter as ctk

from models.faturas_pendentes import FaturasPendentes
from ui.modais_energia import ModalLocalidades, ModalMapeamentoUC, abrir_pdf


class PanelEnergia(ctk.CTkFrame):
    """
    Aba dedicada para configuração, controle de e-mail e cadastro das Localidades da Energisa.
    """
    def __init__(self, parent, config_manager, callback_log, callback_topmost, trigger_bot_callback):
        super().__init__(parent, fg_color="#FFFFFF")
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
        lbl_tit = ctk.CTkLabel(self, text="Provisionamento Automático de Energia (Energisa)", font=("Open Sans", 13, "bold"), text_color="#3D71A8")
        lbl_tit.pack(pady=(10, 5))

        # Configurações do E-mail (Grid)
        frame_config = ctk.CTkFrame(self, fg_color="#F8F9FA", border_width=1, border_color="#DDDDDD", corner_radius=6)
        frame_config.pack(padx=15, pady=5, fill="x")

        ctk.CTkLabel(frame_config, text="E-mail (Gmail):", font=("Open Sans", 11)).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.entry_email = ctk.CTkEntry(frame_config, placeholder_text="ccbdourados@gmail.com", width=250, height=24, font=("Open Sans", 11))
        self.entry_email.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(frame_config, text="Mês de Corte:", font=("Open Sans", 11)).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.entry_corte = ctk.CTkEntry(frame_config, placeholder_text="MM/AAAA (Ex: 06/2026)", width=130, height=24, font=("Open Sans", 11))
        self.entry_corte.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        btn_save_cfg = ctk.CTkButton(
            frame_config, text="Salvar Configuração 💾", font=("Open Sans", 11, "bold"),
            fg_color="#428BCA", hover_color="#3071A9", width=150, height=24, command=self.salvar_dados_email
        )
        btn_save_cfg.grid(row=1, column=2, padx=5, pady=5, sticky="e")

        # Cadastro de Tabelas (Localidades e UCs)
        frame_tabelas = ctk.CTkFrame(self, fg_color="transparent")
        frame_tabelas.pack(padx=15, pady=10, fill="x")

        self.btn_locs = ctk.CTkButton(
            frame_tabelas, text="Cadastrar Localidades 🏢", font=("Open Sans", 12, "bold"),
            fg_color="#F89406", hover_color="#DF8505", height=32, command=self.abrir_localidades
        )
        self.btn_locs.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_ucs = ctk.CTkButton(
            frame_tabelas, text="Mapear UCs 🔌", font=("Open Sans", 12, "bold"),
            fg_color="#F89406", hover_color="#DF8505", height=32, command=self.abrir_ucs
        )
        self.btn_ucs.pack(side="right", fill="x", expand=True, padx=5)

        # Faturas pendentes de mapeamento (só aparece quando há alguma)
        self.frame_pendentes = ctk.CTkFrame(self, fg_color="#FCF8E3", border_width=1, border_color="#FAEBCC", corner_radius=6)
        self.lbl_pendentes = ctk.CTkLabel(self.frame_pendentes, text="", font=("Open Sans", 12, "bold"), text_color="#8A6D3B")
        self.lbl_pendentes.pack(padx=10, pady=(8, 0), anchor="w")
        ctk.CTkLabel(
            self.frame_pendentes, text="Clique em Buscar e Lançar para mapear a UC de cada uma.",
            font=("Open Sans", 10), text_color="#666666"
        ).pack(padx=10, anchor="w")
        self.scroll_pendentes = ctk.CTkScrollableFrame(self.frame_pendentes, fg_color="transparent", height=110)
        self.scroll_pendentes.pack(padx=5, pady=(4, 8), fill="x")

        # Botão Importar Faturas
        self.btn_importar = ctk.CTkButton(
            self, text="⚡ BUSCAR E LANÇAR CONTAS DE ENERGIA ⚡", font=("Open Sans", 13, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=40, command=self.iniciar_importacao_energia
        )
        self.btn_importar.pack(padx=15, pady=15, fill="x")

    def atualizar_pendentes(self):
        """Redesenha a lista de faturas pendentes a partir do config.json."""
        for widget in self.scroll_pendentes.winfo_children():
            widget.destroy()

        faturas = self.pendentes.listar()
        if not faturas:
            self.frame_pendentes.pack_forget()
            return

        self.lbl_pendentes.configure(text=f"⚠️ {len(faturas)} fatura(s) aguardando mapeamento de UC")
        self.frame_pendentes.pack(padx=15, pady=(0, 5), fill="x", before=self.btn_importar)

        for fat in faturas:
            linha = ctk.CTkFrame(self.scroll_pendentes, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=4)
            linha.pack(fill="x", pady=2, padx=2)

            valor = f"R$ {float(fat.get('valor') or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            texto = f"UC {fat.get('uc', '')}  ·  Ref. {fat.get('referencia', '')}  ·  {valor}  ·  Venc. {fat.get('vencimento', '')}"
            ctk.CTkLabel(linha, text=texto, font=("Open Sans", 11), text_color="#333333", anchor="w").pack(side="left", padx=8, pady=4, fill="x", expand=True)

            ctk.CTkButton(
                linha, text="Descartar", font=("Open Sans", 10),
                fg_color="#D9534F", hover_color="#C9302C", width=70, height=22,
                command=lambda f=fat: self.descartar_pendente(f)
            ).pack(side="right", padx=(4, 8), pady=4)

            ctk.CTkButton(
                linha, text="Ver PDF", font=("Open Sans", 10),
                fg_color="#428BCA", hover_color="#3071A9", width=60, height=22,
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
        self.entry_corte.insert(0, cfg.get("mes_corte", ""))

    def salvar_dados_email(self):
        email_str = self.entry_email.get().strip()
        corte_str = self.entry_corte.get().strip()

        if not email_str:
            messagebox.showerror("Erro", "Informe o e-mail do Gmail.", parent=self)
            return

        self.config_manager.salvar_email_config(email_str, "imap.gmail.com", corte_str)

        messagebox.showinfo("Sucesso", "Configurações de energia gravadas com sucesso!", parent=self)

    def abrir_localidades(self):
        ModalLocalidades(self.winfo_toplevel(), self.config_manager)

    def abrir_ucs(self):
        ModalMapeamentoUC(self.winfo_toplevel(), self.config_manager)

    def iniciar_importacao_energia(self):
        self.trigger_bot_callback()
