"""Garante o teto de 500 linhas por arquivo de código (regra do projeto)."""

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = ("bot", "ui", "models", "controllers", "tests")
LIMITE = 500


def _arquivos_python():
    """Lista os .py das pastas de código do projeto, mais os da raiz."""
    arquivos = list(RAIZ.glob("*.py"))
    for pasta in PASTAS:
        arquivos.extend((RAIZ / pasta).rglob("*.py"))
    return sorted(arquivos)


@pytest.mark.parametrize("arquivo", _arquivos_python(), ids=lambda p: p.relative_to(RAIZ).as_posix())
def test_arquivo_abaixo_do_teto(arquivo):
    """Cada arquivo .py deve ter no máximo LIMITE linhas."""
    linhas = len(arquivo.read_text(encoding="utf-8").splitlines())
    assert linhas <= LIMITE, f"{arquivo.name} tem {linhas} linhas (teto {LIMITE})"
