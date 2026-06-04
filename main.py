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
from dotenv import load_dotenv

# Adiciona o diretório atual (onde o main.py está localizado) ao topo do sys.path.
# Isso garante que importações como `from ui.main_window import MainWindow` 
# funcionem mesmo se o aplicativo for executado de outro diretório (ex: via cron ou atalhos).
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Carrega configurações ambientais e segredos do arquivo .env
load_dotenv()

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
