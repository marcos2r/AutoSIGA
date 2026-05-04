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

# Adiciona o diretório atual (onde o main.py está localizado) ao topo do sys.path.
# Isso garante que importações como `from ui.main_window import MainWindow` 
# funcionem mesmo se o aplicativo for executado de outro diretório (ex: via cron ou atalhos).
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ui.main_window import MainWindow

if __name__ == "__main__":
    # Instancia a janela principal que foi isolada no módulo UI
    app = MainWindow()
    
    # Inicia o loop de eventos (Main Loop) do CustomTkinter, 
    # mantendo a interface gráfica ativa e aguardando interações do usuário.
    app.mainloop()
