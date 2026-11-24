"""Descrição da Release tirada do CHANGELOG (scripts/notas_da_release.py)."""

import importlib.util
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parent.parent / "scripts" / "notas_da_release.py"
_spec = importlib.util.spec_from_file_location("notas_da_release", _CAMINHO)
notas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notas)

CHANGELOG = """# Changelog

## v1.14.0

- **A**: primeira.
- **B**: segunda.

## v1.13.1

- **C**: antiga.
"""


def test_pega_so_a_secao_da_versao():
    assert notas.secao_do_changelog(CHANGELOG, "v1.14.0") == "- **A**: primeira.\n- **B**: segunda."
    assert notas.secao_do_changelog(CHANGELOG, "1.13.1") == "- **C**: antiga."


def test_versao_sem_secao_para_o_ci():
    with pytest.raises(ValueError):
        notas.secao_do_changelog(CHANGELOG, "v9.9.9")


def test_a_versao_atual_tem_secao_no_changelog():
    """Garante, a cada push, que a versão de version.py já está descrita no CHANGELOG."""
    from version import VERSION
    assert notas.secao_do_changelog(notas.CHANGELOG.read_text(encoding="utf-8"), VERSION)
