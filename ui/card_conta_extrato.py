"""
Card de uma conta de extrato no lote: mapeamento conta→SIGA e validação visual.
"""

from tkinter import messagebox

import customtkinter as ctk


class CardContaExtrato(ctk.CTkFrame):
    """
    Componente visual que encapsula a exibição dos dados de um extrato
    e seus respectivos campos de mapeamento do SIGA (Localidade, C. Corrente e C. Aplicação).
    """
    def __init__(self, parent, dados_extrato, config_manager, on_change_callback):
        super().__init__(parent, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=6)
        self.dados_extrato = dados_extrato
        self.config_manager = config_manager
        self.on_change_callback = on_change_callback

        self.conta_id = dados_extrato.get("conta_id", "")
        self.produto = dados_extrato.get("produto")
        self.tipo_extrato = dados_extrato.get("tipo_extrato")
        self.is_aplicacao = (self.tipo_extrato == "APLICACAO")

        self.inicializando = True
        self.construir_widgets()
        self.carregar_mapeamento()
        self.inicializando = False

    def construir_widgets(self):
        # Nome do arquivo e Info da conta
        tipo_desc = f"Aplicação: {self.produto}" if self.is_aplicacao else "Conta Corrente"
        label_header = f"Conta Bancária: {self.conta_id} ({tipo_desc})"

        self.lbl_titulo = ctk.CTkLabel(self, text=label_header, font=("Open Sans", 12, "bold"), text_color="#3D71A8")
        self.lbl_titulo.grid(row=0, column=0, columnspan=5, padx=10, pady=(6, 2), sticky="w")

        # Grid para inputs
        # Linha 1: Localidade
        self.lbl_loc = ctk.CTkLabel(self, text="Localidade:", font=("Open Sans", 11))
        self.lbl_loc.grid(row=1, column=0, padx=5, pady=2, sticky="e")

        self.combo_tipo = ctk.CTkComboBox(self, values=["ADM", "DR", "PIA"], width=65, height=24, font=("Open Sans", 11))
        self.combo_tipo.grid(row=1, column=1, padx=2, pady=2, sticky="w")

        self.entry_nome = ctk.CTkEntry(self, placeholder_text="Ex: SÃO PAULO", width=110, height=24, font=("Open Sans", 11))
        self.entry_nome.grid(row=1, column=2, padx=2, pady=2, sticky="w")
        self.entry_nome.bind("<FocusOut>", lambda e: self.salvar_e_notificar())
        self.entry_nome.bind("<KeyRelease>", lambda e: self._forcar_maiusculo(self.entry_nome))
        self.combo_tipo.configure(command=lambda v: self.salvar_e_notificar())

        # Linha 2: Contas SIGA
        self.lbl_cc_ca = ctk.CTkLabel(self, text="C. Corrente / Aplicação:", font=("Open Sans", 11))
        self.lbl_cc_ca.grid(row=2, column=0, padx=5, pady=2, sticky="e")

        self.entry_cc = ctk.CTkEntry(self, placeholder_text="C. Corrente", width=85, height=24, font=("Open Sans", 11))
        self.entry_cc.grid(row=2, column=1, padx=2, pady=2, sticky="w")
        self.entry_cc.bind("<FocusOut>", lambda e: self.salvar_e_notificar())

        self.entry_ca = ctk.CTkEntry(self, placeholder_text="C. Aplicação", width=85, height=24, font=("Open Sans", 11))
        self.entry_ca.grid(row=2, column=2, padx=2, pady=2, sticky="w")
        self.entry_ca.bind("<FocusOut>", lambda e: self.salvar_e_notificar())

        if self.is_aplicacao:
            self.entry_cc.configure(state="disabled", placeholder_text="N/A")

        # Indicador de status (Badge)
        self.lbl_status = ctk.CTkLabel(self, text="Pendente", font=("Open Sans", 11, "bold"), text_color="#D9534F", width=70)
        self.lbl_status.grid(row=1, column=3, rowspan=2, padx=10, pady=2)

        # Botão esquecer
        self.btn_limpar = ctk.CTkButton(self, text="Limpar", width=50, height=22, font=("Open Sans", 10), fg_color="#F0AD4E", hover_color="#EEA236", command=self.limpar_mapeamento)
        self.btn_limpar.grid(row=1, column=4, rowspan=2, padx=5, pady=2)

    def _forcar_maiusculo(self, entry):
        pos = entry.index("insert")
        texto = entry.get().upper()
        entry.delete(0, "end")
        entry.insert(0, texto)
        entry.icursor(pos)

    def carregar_mapeamento(self):
        tipo_adm, nome_adm = self.config_manager.get_geral()
        novo_tipo, novo_nome, dados = self.config_manager.get_mapeamento_conta(self.conta_id, tipo_adm, nome_adm, produto=self.produto)

        self.combo_tipo.set(novo_tipo)
        self.entry_nome.delete(0, 'end')
        self.entry_nome.insert(0, novo_nome.upper())

        if not self.is_aplicacao:
            self.entry_cc.delete(0, 'end')
            self.entry_cc.insert(0, dados.get("corrente", ""))

        self.entry_ca.delete(0, 'end')
        self.entry_ca.insert(0, dados.get("aplicacao", ""))

        self.atualizar_status_visual()

    def atualizar_status_visual(self):
        nome_adm = self.entry_nome.get().strip()
        cc = self.entry_cc.get().strip() if not self.is_aplicacao else "N/A"
        ca = self.entry_ca.get().strip()

        if nome_adm and ca and (self.is_aplicacao or cc):
            self.lbl_status.configure(text="Mapeado", text_color="#3C763D")
            self.configure(border_color="#3C763D")
        else:
            self.lbl_status.configure(text="Pendente", text_color="#D9534F")
            self.configure(border_color="#D9534F")

    def salvar_e_notificar(self):
        if getattr(self, "inicializando", False):
            return
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip().upper()
        cc = self.entry_cc.get().strip()
        ca = self.entry_ca.get().strip()

        self.config_manager.salvar_mapeamento_conta(
            self.conta_id, tipo_adm, nome_adm, cc, ca, produto=self.produto
        )

        if nome_adm:
            self.config_manager.salvar_geral(tipo_adm, nome_adm)

        self.atualizar_status_visual()
        if self.on_change_callback:
            self.on_change_callback()

    def limpar_mapeamento(self):
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip()
        if self.config_manager.limpar_conta(self.conta_id, tipo_adm, nome_adm, produto=self.produto):
            self.combo_tipo.set("ADM")
            self.entry_nome.delete(0, 'end')
            if not self.is_aplicacao:
                self.entry_cc.delete(0, 'end')
            self.entry_ca.delete(0, 'end')
            self.atualizar_status_visual()
            if self.on_change_callback:
                self.on_change_callback()
            messagebox.showinfo("Limpeza", f"O mapeamento da conta {self.conta_id} foi apagado.")

    def obter_dados_mapeados(self):
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip().upper()
        cc = self.entry_cc.get().strip()
        ca = self.entry_ca.get().strip()

        return {
            "tipo_adm": tipo_adm,
            "nome_adm": nome_adm,
            "corrente": cc,
            "aplicacao": ca,
            "valido": bool(nome_adm and ca and (self.is_aplicacao or cc))
        }
