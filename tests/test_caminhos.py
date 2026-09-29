import os
import sys

import caminhos


def test_diretorio_base_em_desenvolvimento_e_a_raiz_do_projeto():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert caminhos.diretorio_base() == raiz


def test_diretorio_base_no_executavel_e_a_pasta_do_exe(monkeypatch, tmp_path):
    exe = tmp_path / "AutoSiga" / "AutoSiga.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    # Dados do usuário ficam ao lado do .exe, nunca dentro de _internal
    assert caminhos.diretorio_base() == str(exe.parent)
