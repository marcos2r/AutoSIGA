"""
Módulo centralizador do diretório base da aplicação.

Os dados do usuário (config.json, credenciais, token do Gmail, logs e faturas)
ficam ao lado do executável. No build do PyInstaller (onedir), o código fica
dentro da pasta _internal, então caminhos calculados a partir de __file__
apontariam para ela e se perderiam a cada atualização de versão.
"""

import os
import sys


def diretorio_base() -> str:
    """
    Retorna a pasta onde os dados locais da aplicação devem ser lidos e gravados.

    Returns:
        str: Pasta do AutoSiga.exe quando empacotado; raiz do projeto quando rodando via Python.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
