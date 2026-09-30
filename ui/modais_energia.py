"""
Modais da aba Energia (View).

Cadastro de localidades, manutenção do mapeamento UC -> Localidade e a pergunta
interativa exibida quando uma fatura chega de uma UC ainda não mapeada.
"""

import os
from tkinter import messagebox

import customtkinter as ctk


class ModalLocalidades(ctk.CTkToplevel):
    """
    Janela modal para cadastro, listagem e manutenção de Localidades da Energisa.
    """
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager

        self.title("Manutenção de Localidades")
        self.geometry("580x420")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()

        self.construir_widgets()
        self.carregar_tabela()

    def construir_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Cadastro de Localidades", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        lbl_titulo.pack(pady=10)

        # Campos de Cadastro
        frame_inputs = ctk.CTkFrame(self, fg_color="transparent")
        frame_inputs.pack(padx=20, pady=5, fill="x")

        self.entry_codigo = ctk.CTkEntry(frame_inputs, placeholder_text="Código (Ex: BR 10-0516)", width=150, height=28, font=("Open Sans", 11))
        self.entry_codigo.grid(row=0, column=0, padx=5, pady=5)

        self.entry_nome = ctk.CTkEntry(frame_inputs, placeholder_text="Descrição/Nome da Localidade", width=360, height=28, font=("Open Sans", 11))
        self.entry_nome.grid(row=0, column=1, padx=5, pady=5)

        btn_salvar = ctk.CTkButton(
            frame_inputs, text="Adicionar / Salvar", font=("Open Sans", 11, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=28, command=self.salvar_localidade
        )
        btn_salvar.grid(row=1, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # Divisor
        div = ctk.CTkFrame(self, height=1, fg_color="#EEEEEE")
        div.pack(fill="x", padx=15, pady=5)

        lbl_lista = ctk.CTkLabel(self, text="Localidades Cadastradas", font=("Open Sans", 12, "bold"), text_color="#3D71A8")
        lbl_lista.pack(pady=(5, 2))

        # Lista rolável
        self.scroll_tabela = ctk.CTkScrollableFrame(self, fg_color="#F8F9FA", corner_radius=6, height=200)
        self.scroll_tabela.pack(padx=20, pady=5, fill="both", expand=True)

    def carregar_tabela(self):
        # Limpa widgets na scrollable list
        for widget in self.scroll_tabela.winfo_children():
            widget.destroy()

        localidades = self.config_manager.get_localidades_energia()
        if not localidades:
            lbl_empty = ctk.CTkLabel(self.scroll_tabela, text="Nenhuma localidade cadastrada.", font=("Open Sans", 11), text_color="#999999")
            lbl_empty.pack(pady=40)
            return

        for idx, loc in enumerate(localidades):
            item_frame = ctk.CTkFrame(self.scroll_tabela, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=4)
            item_frame.pack(fill="x", pady=2, padx=2)

            cod = loc.get("codigo", "")
            nome = loc.get("nome", "")

            lbl_cod = ctk.CTkLabel(item_frame, text=cod, font=("Open Sans", 11, "bold"), text_color="#3D71A8", width=120, anchor="w")
            lbl_cod.pack(side="left", padx=10, pady=5)

            btn_del = ctk.CTkButton(
                item_frame, text="Excluir", font=("Open Sans", 10),
                fg_color="#D9534F", hover_color="#C9302C", width=60, height=20,
                command=lambda c=cod: self.excluir_localidade(c)
            )
            btn_del.pack(side="right", padx=10, pady=5)

            btn_edit = ctk.CTkButton(
                item_frame, text="Editar", font=("Open Sans", 10),
                fg_color="#F0AD4E", hover_color="#EC971F", width=60, height=20,
                command=lambda c=cod, n=nome: self.editar_localidade(c, n)
            )
            btn_edit.pack(side="right", padx=5, pady=5)

            lbl_nome = ctk.CTkLabel(item_frame, text=nome, font=("Open Sans", 11), anchor="w")
            lbl_nome.pack(side="left", padx=5, pady=5, fill="x", expand=True)

    def editar_localidade(self, codigo, nome):
        self.entry_codigo.delete(0, "end")
        self.entry_codigo.insert(0, codigo)
        self.entry_nome.delete(0, "end")
        self.entry_nome.insert(0, nome)

    def salvar_localidade(self):
        codigo = self.entry_codigo.get().strip().upper()
        nome = self.entry_nome.get().strip().upper()

        if not codigo or not nome:
            messagebox.showerror("Erro", "Preencha o Código e a Descrição.", parent=self)
            return

        # Padrão simples de formato "BR XX-XXXX"
        if not codigo.startswith("BR ") or len(codigo) < 8:
            messagebox.showwarning("Aviso", "O código deve seguir o padrão 'BR 10-0516'.", parent=self)

        self.config_manager.salvar_localidade_energia(codigo, nome)
        self.entry_codigo.delete(0, "end")
        self.entry_nome.delete(0, "end")
        self.carregar_tabela()
        messagebox.showinfo("Sucesso", "Localidade gravada com sucesso!", parent=self)

    def excluir_localidade(self, codigo):
        if messagebox.askyesno("Confirmar", f"Deseja excluir a localidade {codigo}?", parent=self):
            self.config_manager.remover_localidade_energia(codigo)
            self.carregar_tabela()


class ModalMapeamentoUC(ctk.CTkToplevel):
    """
    Janela modal para manutenção do mapeamento de Unidades Consumidoras para Localidades.
    """
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager

        self.title("Manutenção de UCs")
        self.geometry("580x420")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()

        self.construir_widgets()
        self.carregar_tabela()

    def construir_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Mapeamento UC -> Localidade", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        lbl_titulo.pack(pady=10)

        # Cadastro
        frame_inputs = ctk.CTkFrame(self, fg_color="transparent")
        frame_inputs.pack(padx=20, pady=5, fill="x")

        self.entry_uc = ctk.CTkEntry(frame_inputs, placeholder_text="Nº UC (Ex: 890.005.051-36)", width=170, height=28, font=("Open Sans", 11))
        self.entry_uc.grid(row=0, column=0, padx=5, pady=5)

        # Dropdown de localidades cadastradas
        localidades = self.config_manager.get_localidades_energia()
        self.combo_loc_values = [f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome'] for l in localidades]
        
        self.combo_loc = ctk.CTkComboBox(
            frame_inputs, values=self.combo_loc_values if self.combo_loc_values else ["Cadastre Localidades Primeiro"],
            width=340, height=28, font=("Open Sans", 10)
        )
        self.combo_loc.grid(row=0, column=1, padx=5, pady=5)

        btn_salvar = ctk.CTkButton(
            frame_inputs, text="Relacionar UC", font=("Open Sans", 11, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=28, command=self.salvar_mapeamento
        )
        btn_salvar.grid(row=1, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # Divisor
        div = ctk.CTkFrame(self, height=1, fg_color="#EEEEEE")
        div.pack(fill="x", padx=15, pady=5)

        lbl_lista = ctk.CTkLabel(self, text="Mapeamentos UC Existentes", font=("Open Sans", 12, "bold"), text_color="#3D71A8")
        lbl_lista.pack(pady=(5, 2))

        # Lista rolável
        self.scroll_tabela = ctk.CTkScrollableFrame(self, fg_color="#F8F9FA", corner_radius=6, height=200)
        self.scroll_tabela.pack(padx=20, pady=5, fill="both", expand=True)

    def carregar_tabela(self):
        for widget in self.scroll_tabela.winfo_children():
            widget.destroy()

        mapeamentos = self.config_manager.get_mapeamentos_uc()
        if not mapeamentos:
            lbl_empty = ctk.CTkLabel(self.scroll_tabela, text="Nenhum mapeamento de UC cadastrado.", font=("Open Sans", 11), text_color="#999999")
            lbl_empty.pack(pady=40)
            return

        for idx, m in enumerate(mapeamentos):
            item_frame = ctk.CTkFrame(self.scroll_tabela, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=4)
            item_frame.pack(fill="x", pady=2, padx=2)

            uc_num = m.get("uc", "")
            loc_cod = m.get("localidade_codigo", "")

            lbl_uc = ctk.CTkLabel(item_frame, text=uc_num, font=("Open Sans", 11, "bold"), text_color="#3D71A8", width=130, anchor="w")
            lbl_uc.pack(side="left", padx=10, pady=5)

            btn_del = ctk.CTkButton(
                item_frame, text="Excluir", font=("Open Sans", 10),
                fg_color="#D9534F", hover_color="#C9302C", width=60, height=20,
                command=lambda u=uc_num: self.excluir_mapeamento(u)
            )
            btn_del.pack(side="right", padx=10, pady=5)

            localidades_dict = {l["codigo"]: l["nome"] for l in self.config_manager.get_localidades_energia()}
            loc_nome = localidades_dict.get(loc_cod, "")
            texto_loc = f"{loc_cod} - {loc_nome}" if loc_nome else loc_cod

            btn_edit = ctk.CTkButton(
                item_frame, text="Editar", font=("Open Sans", 10),
                fg_color="#F0AD4E", hover_color="#EC971F", width=60, height=20,
                command=lambda u=uc_num, ln=loc_nome: self.editar_mapeamento(u, ln)
            )
            btn_edit.pack(side="right", padx=5, pady=5)

            lbl_loc = ctk.CTkLabel(item_frame, text=texto_loc, font=("Open Sans", 11), anchor="w")
            lbl_loc.pack(side="left", padx=5, pady=5, fill="x", expand=True)

    def editar_mapeamento(self, uc, loc_nome):
        self.entry_uc.delete(0, "end")
        self.entry_uc.insert(0, uc)
        if loc_nome:
            localidades = self.config_manager.get_localidades_energia()
            for l in localidades:
                if l["nome"] == loc_nome or l["codigo"] == loc_nome:
                    comb = f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome']
                    self.combo_loc.set(comb)
                    break

    def salvar_mapeamento(self):
        uc = self.entry_uc.get().strip()
        loc_texto = self.combo_loc.get().strip()

        if not uc or not loc_texto or "Cadastre" in loc_texto:
            messagebox.showerror("Erro", "Preencha a UC e selecione uma Localidade.", parent=self)
            return

        localidades = self.config_manager.get_localidades_energia()
        codigo_loc = None
        for l in localidades:
            comb = f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome']
            if comb == loc_texto or l["nome"] == loc_texto or l["codigo"] == loc_texto:
                codigo_loc = l["codigo"]
                break

        if not codigo_loc:
            messagebox.showerror("Erro", "Localidade inválida.", parent=self)
            return

        self.config_manager.salvar_mapeamento_uc(uc, codigo_loc)
        self.entry_uc.delete(0, "end")
        self.carregar_tabela()
        messagebox.showinfo("Sucesso", "Relação gravada com sucesso!", parent=self)

    def excluir_mapeamento(self, uc):
        if messagebox.askyesno("Confirmar", f"Deseja remover o relacionamento da UC {uc}?", parent=self):
            self.config_manager.remover_mapeamento_uc(uc)
            self.carregar_tabela()


def abrir_pdf(caminho_pdf: str, parent) -> None:
    """Abre o PDF da fatura no visualizador padrão do Windows."""
    if caminho_pdf and os.path.exists(caminho_pdf):
        try:
            os.startfile(caminho_pdf)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o PDF: {e}", parent=parent)


class ModalPerguntaMapeamentoUC(ctk.CTkToplevel):
    """
    Modal interativo aberto dinamicamente pelo bot para associar uma UC desconhecida.

    A fatura já está gravada como pendente antes do modal abrir. Por isso, fechar a
    janela ou escolher "Deixar Pendente" nunca a perde: ela aparece na aba Energia e
    volta a ser perguntada na próxima importação.
    """
    def __init__(self, parent, uc, config_manager, callback_resposta, caminho_pdf=None):
        super().__init__(parent)
        self.parent = parent
        self.uc = uc
        self.config_manager = config_manager
        self.callback_resposta = callback_resposta
        self.caminho_pdf = caminho_pdf

        self.title("Mapear Unidade Consumidora")
        self.geometry("380x360")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()

        # Fechar pelo "X" equivale a deixar pendente (e destrava a thread que aguarda a resposta)
        self.protocol("WM_DELETE_WINDOW", self.deixar_pendente)

        self.construir_widgets()

    def construir_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Nova UC Detectada!", font=("Open Sans", 14, "bold"), text_color="#D9534F")
        lbl_titulo.pack(pady=8)

        lbl_desc = ctk.CTkLabel(
            self, text=f"Deseja relacionar a Unidade Consumidora {self.uc} a alguma localidade para lançar no SIGA?",
            font=("Open Sans", 11), text_color="#333333", wraplength=320
        )
        lbl_desc.pack(pady=8)

        # Botão para visualizar nota fiscal (PDF) se houver
        if self.caminho_pdf and os.path.exists(self.caminho_pdf):
            btn_ver_nota = ctk.CTkButton(
                self, text="📄 Visualizar Fatura (Abrir PDF)", font=("Open Sans", 11, "underline"),
                fg_color="transparent", text_color="#428BCA", hover_color="#EEEEEE",
                width=280, height=25, command=self.abrir_nota
            )
            btn_ver_nota.pack(pady=5)

        # Dropdown
        localidades = self.config_manager.get_localidades_energia()
        self.localidades_list = localidades
        combo_values = [f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome'] for l in localidades]

        self.combo_loc = ctk.CTkComboBox(
            self, values=combo_values if combo_values else ["Cadastre Localidades Primeiro"],
            width=280, height=30, font=("Open Sans", 10)
        )
        self.combo_loc.pack(pady=8)

        # Botões: a ação principal em destaque; a secundária é neutra e afastada,
        # para reduzir cliques acidentais
        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(pady=(10, 4))

        btn_confirmar = ctk.CTkButton(
            frame_btn, text="Mapear e Lançar", font=("Open Sans", 12, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", width=160, height=38, command=self.confirmar
        )
        btn_confirmar.grid(row=0, column=0, padx=(0, 16))

        btn_pendente = ctk.CTkButton(
            frame_btn, text="Deixar Pendente", font=("Open Sans", 11),
            fg_color="#E6E6E6", hover_color="#D4D4D4", text_color="#333333",
            width=110, height=32, command=self.deixar_pendente
        )
        btn_pendente.grid(row=0, column=1)

        lbl_dica = ctk.CTkLabel(
            self, text="Faturas pendentes ficam na aba Energia e podem ser lançadas depois.",
            font=("Open Sans", 10), text_color="#666666", wraplength=320
        )
        lbl_dica.pack(pady=(4, 8))

    def abrir_nota(self):
        abrir_pdf(self.caminho_pdf, self)

    def confirmar(self):
        loc_txt = self.combo_loc.get().strip()
        if "Cadastre" in loc_txt or not loc_txt:
            messagebox.showerror("Erro", "Selecione uma localidade válida.", parent=self)
            return

        codigo_loc = None
        for l in self.localidades_list:
            comb = f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome']
            if comb == loc_txt or l["nome"] == loc_txt or l["codigo"] == loc_txt:
                codigo_loc = l["codigo"]
                break

        if not codigo_loc:
            messagebox.showerror("Erro", "Localidade inválida.", parent=self)
            return

        self.config_manager.salvar_mapeamento_uc(self.uc, codigo_loc)
        
        self.callback_resposta(codigo_loc)
        self.destroy()

    def deixar_pendente(self):
        self.callback_resposta(None)
        self.destroy()
