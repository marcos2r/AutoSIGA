"""
Módulo principal (Entrypoint) do AutoSIGA.

Este arquivo é o ponto de partida da aplicação. Ele é responsável por:
1. Configurar o PYTHONPATH para garantir que os módulos internos 
   (models, controllers, bot, ui) sejam localizados corretamente, independente
   de onde o script seja chamado.
2. Instanciar e executar a interface gráfica principal (MainWindow).
"""

import sys
import os
import shutil
import tkinter as tk
from tkinter import messagebox
from dotenv import load_dotenv

# Adiciona o diretório atual (onde o main.py está localizado) ao topo do sys.path.
# Isso garante que importações como `from ui.main_window import MainWindow` 
# funcionem mesmo se o aplicativo for executado de outro diretório (ex: via cron ou atalhos).
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Define caminhos base
raiz_dir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(raiz_dir, ".env")
env_example_path = os.path.join(raiz_dir, ".env.example")

# 1. Verifica a existência do arquivo .env. Se ausente, cria um a partir do .env.example
if not os.path.exists(env_path):
    try:
        if os.path.exists(env_example_path):
            shutil.copy(env_example_path, env_path)
            msg_setup = (
                "O arquivo de configuração '.env' estava ausente e foi criado automaticamente na raiz do projeto.\n\n"
                "Por favor, abra o arquivo '.env' e preencha as variáveis:\n"
                "- SIGA_USUARIO\n"
                "- SIGA_SENHA\n\n"
                "O aplicativo será encerrado para que você possa efetuar essa configuração."
            )
        else:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write("SIGA_USUARIO=\nSIGA_SENHA=\n")
            msg_setup = (
                "O arquivo de configuração '.env' foi criado na raiz do projeto.\n\n"
                "Por favor, configure as chaves 'SIGA_USUARIO' e 'SIGA_SENHA' no arquivo '.env' antes de iniciar."
            )
        
        # Exibe o popup explicativo de forma nativa e limpa
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Configuração Inicial Necessária", msg_setup)
        root.destroy()
        sys.exit(1)
    except Exception as e:
        print(f"Erro ao inicializar o arquivo de configuração .env: {e}")
        sys.exit(1)

# Carrega as variáveis do .env recém-validado
load_dotenv(env_path)

# 2. Valida se as variáveis de credenciais obrigatórias estão preenchidas (Fail Fast)
usuario_env = os.getenv("SIGA_USUARIO", "").strip()
senha_env = os.getenv("SIGA_SENHA", "").strip()

if not usuario_env or not senha_env:
    msg_erro = (
        "Configurações obrigatórias ausentes ou vazias no arquivo '.env'!\n\n"
        "Para que a conciliação automatizada funcione, preencha as variáveis:\n"
        "SIGA_USUARIO=seu_usuario\n"
        "SIGA_SENHA=sua_senha\n\n"
        "Acesse o arquivo '.env' localizado em:\n"
        f"{env_path}"
    )
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Erro de Segurança e Configuração", msg_erro)
    root.destroy()
    sys.exit(1)

from ui.main_window import MainWindow

if __name__ == "__main__":
    # Configura pasta e arquivo de log local para auditoria técnica das conciliações
    log_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    import logging
    from datetime import datetime
    log_filename = os.path.join(log_dir, f"conciliacao_{datetime.now().strftime('%Y_%m_%d')}.log")
    
    # Cria handler customizado para o console que tolera falhas de encode cp1252 no Windows
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    try:
        # Tenta forçar UTF-8 no console se disponível no Python moderno
        console_handler.stream = open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
    except Exception:
        pass
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            console_handler
        ]
    )
    
    # Instancia a janela principal que foi isolada no módulo UI
    app = MainWindow()
    
    # Inicia o loop de eventos (Main Loop) do CustomTkinter, 
    # mantendo a interface gráfica ativa e aguardando interações do usuário.
    app.mainloop()
