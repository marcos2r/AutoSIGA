"""
Credenciais do SIGA na UI: modal de cadastro no Keyring e verificação antes de rodar o bot.
"""

import os
from tkinter import messagebox

import customtkinter as ctk


class CredenciaisMixin:
    """Verificação e solicitação de credenciais do SIGA pela janela principal."""

    def verificar_credenciais_iniciais(self):
        """Verifica se existem credenciais salvas no Keyring ou .env. Caso contrário, abre a modal."""
        import keyring
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else None

        # Fallback legado de desenvolvedor .env
        usuario_env = os.getenv("SIGA_USUARIO", "")
        senha_env = os.getenv("SIGA_SENHA", "")

        if not (usuario and senha) and not (usuario_env and senha_env):
            self.abrir_modal_credenciais()

    def abrir_modal_credenciais(self):
        """Abre a modal de cadastro de credenciais seguras."""
        modal = ModalCredenciais(self, self.config_manager)
        modal.grab_set() # Foca a interação na modal

    def verificar_e_solicitar_credenciais(self):
        """
        Verifica se existem credenciais salvas no Keyring ou .env.
        Caso contrário, abre a modal de cadastro e aguarda o preenchimento pelo usuário.
        Retorna True se credenciais estiverem cadastradas/presentes, False caso contrário.
        """
        import keyring
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else None

        usuario_env = os.getenv("SIGA_USUARIO", "")
        senha_env = os.getenv("SIGA_SENHA", "")

        if (usuario and senha) or (usuario_env and senha_env):
            return True

        # Abre a modal de cadastro de forma síncrona
        messagebox.showinfo(
            "Credenciais Necessárias",
            "Para executar tarefas no SIGA, é necessário cadastrar suas credenciais de acesso."
        )
        modal = ModalCredenciais(self, self.config_manager)
        modal.grab_set()
        self.wait_window(modal)

        # Re-verifica após o fechamento da modal
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else None

        if (usuario and senha) or (usuario_env and senha_env):
            return True

        return False


class ModalCredenciais(ctk.CTkToplevel):
    """
    Janela modal para cadastro e edição segura de credenciais do SIGA no Keyring do Windows.
    """
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager

        self.title("Configurar Credenciais Seguras")
        self.geometry("380x250")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")

        # Centraliza na janela pai
        self.transient(parent)

        # Força o topo
        self.attributes("-topmost", True)

        self.construir_widgets()
        self.carregar_dados()

    def construir_widgets(self):
        # Título interno
        lbl_titulo = ctk.CTkLabel(self, text="Credenciais de Acesso ao SIGA", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        lbl_titulo.pack(pady=(15, 10))

        lbl_info = ctk.CTkLabel(
            self,
            text="Sua senha será salva de forma encriptada no Windows Credential Manager.",
            font=("Open Sans", 9), text_color="#666666", wraplength=340
        )
        lbl_info.pack(pady=(0, 15))

        # Usuário
        self.entry_usuario = ctk.CTkEntry(self, placeholder_text="Usuário (CPF ou E-mail)", width=280, height=30, font=("Open Sans", 11))
        self.entry_usuario.pack(pady=5)

        # Senha
        self.entry_senha = ctk.CTkEntry(self, placeholder_text="Senha do SIGA", show="*", width=280, height=30, font=("Open Sans", 11))
        self.entry_senha.pack(pady=5)

        # Botões
        self.frame_botoes = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_botoes.pack(pady=20)

        self.btn_salvar = ctk.CTkButton(
            self.frame_botoes, text="Gravar", width=100, height=30, font=("Open Sans", 12, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", command=self.salvar_credenciais
        )
        self.btn_salvar.grid(row=0, column=0, padx=5)

        self.btn_cancelar = ctk.CTkButton(
            self.frame_botoes, text="Cancelar", width=100, height=30, font=("Open Sans", 12, "bold"),
            fg_color="#D9534F", hover_color="#C9302C", command=self.destroy
        )
        self.btn_cancelar.grid(row=0, column=1, padx=5)

    def carregar_dados(self):
        import keyring
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else ""

        self.entry_usuario.insert(0, usuario)
        # keyring devolve None quando o usuário existe mas a senha não está neste Windows
        self.entry_senha.insert(0, senha or "")

    def salvar_credenciais(self):
        import keyring
        usuario = self.entry_usuario.get().strip()
        senha = self.entry_senha.get().strip()

        if not usuario or not senha:
            messagebox.showerror("Erro", "Por favor, preencha o usuário e a senha do SIGA.", parent=self)
            return

        try:
            # Salva o usuário no config.json
            self.config_manager.salvar_usuario_siga(usuario)
            # Salva a senha de forma encriptada no Windows Credential Manager
            keyring.set_password("AutoSIGA", usuario, senha)

            messagebox.showinfo("Sucesso", "Credenciais gravadas com segurança no Windows Keyring!", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro de Gravação", f"Não foi possível salvar no keyring: {e}", parent=self)
