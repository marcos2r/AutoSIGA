import pytest
from unittest.mock import MagicMock, patch
import os

# Mock class mimicking MainWindow behavior
class DummyMainWindow:
    def __init__(self):
        self.config_manager = MagicMock()
        self.wait_window = MagicMock()

    def verificar_e_solicitar_credenciais(self):
        # We import here since we are mimicking the MainWindow method
        import keyring
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else None

        usuario_env = os.getenv("SIGA_USUARIO", "")
        senha_env = os.getenv("SIGA_SENHA", "")

        if (usuario and senha) or (usuario_env and senha_env):
            return True

        # Abre a modal de cadastro de forma síncrona
        from tkinter import messagebox
        messagebox.showinfo(
            "Credenciais Necessárias", 
            "Para executar tarefas no SIGA, é necessário cadastrar suas credenciais de acesso."
        )
        # Mock instantiating and showing the modal
        modal = MagicMock()
        self.wait_window(modal)

        # Re-verifica após o fechamento da modal
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else None

        if (usuario and senha) or (usuario_env and senha_env):
            return True

        return False


@patch("keyring.get_password")
@patch("tkinter.messagebox.showinfo")
@patch("os.getenv")
def test_verificar_e_solicitar_credenciais_ja_cadastradas_keyring(mock_getenv, mock_showinfo, mock_get_password):
    # Setup
    win = DummyMainWindow()
    win.config_manager.get_usuario_siga.return_value = "usuario_siga_teste"
    mock_get_password.return_value = "senha_siga_teste"
    mock_getenv.return_value = ""

    # Execute
    result = win.verificar_e_solicitar_credenciais()

    # Assertions
    assert result is True
    win.config_manager.get_usuario_siga.assert_called_once()
    mock_get_password.assert_called_with("AutoSIGA", "usuario_siga_teste")
    mock_showinfo.assert_not_called()


@patch("keyring.get_password")
@patch("tkinter.messagebox.showinfo")
@patch("os.getenv")
def test_verificar_e_solicitar_credenciais_ja_cadastradas_env(mock_getenv, mock_showinfo, mock_get_password):
    # Setup
    win = DummyMainWindow()
    win.config_manager.get_usuario_siga.return_value = ""
    mock_get_password.return_value = None
    mock_getenv.side_effect = lambda key, default="": "valor_env" if "SIGA_" in key else ""

    # Execute
    result = win.verificar_e_solicitar_credenciais()

    # Assertions
    assert result is True
    mock_showinfo.assert_not_called()


@patch("keyring.get_password")
@patch("tkinter.messagebox.showinfo")
@patch("os.getenv")
def test_verificar_e_solicitar_credenciais_solicita_e_cadastra(mock_getenv, mock_showinfo, mock_get_password):
    # Setup
    win = DummyMainWindow()
    
    # First check: no credentials (usuario = "")
    # Second check: has credentials (usuario = "usuario_novo")
    win.config_manager.get_usuario_siga.side_effect = ["", "usuario_novo"]
    
    # Mock keyring.get_password to return None if user is empty, or "senha_nova" if user is "usuario_novo"
    mock_get_password.side_effect = lambda service, username: "senha_nova" if username == "usuario_novo" else None
    mock_getenv.return_value = ""

    # Execute
    result = win.verificar_e_solicitar_credenciais()

    # Assertions
    assert result is True
    mock_showinfo.assert_called_once()
    assert win.wait_window.called


@patch("keyring.get_password")
@patch("tkinter.messagebox.showinfo")
@patch("os.getenv")
def test_verificar_e_solicitar_credenciais_cancela_cadastro(mock_getenv, mock_showinfo, mock_get_password):
    # Setup
    win = DummyMainWindow()
    
    # First check: no credentials; Second check: still no credentials
    win.config_manager.get_usuario_siga.return_value = ""
    mock_get_password.return_value = None
    mock_getenv.return_value = ""

    # Execute
    result = win.verificar_e_solicitar_credenciais()

    # Assertions
    assert result is False
    mock_showinfo.assert_called_once()
    assert win.wait_window.called
