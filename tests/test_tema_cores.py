"""Cores da interface: só tokens de ui/tema.py, e os pares de texto passam no WCAG AA."""

import re
from pathlib import Path

import pytest

from ui import tema

PASTA_UI = Path(__file__).resolve().parent.parent / "ui"
HEX_LITERAL = re.compile(r"""["']#[0-9A-Fa-f]{3,8}["']""")


def _luminancia(hexa: str) -> float:
    """Luminância relativa (WCAG 2.1) de uma cor #RRGGBB."""
    canais = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(texto: str, fundo: str) -> float:
    """Razão de contraste WCAG entre duas cores."""
    claro, escuro = sorted((_luminancia(texto), _luminancia(fundo)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def test_ui_nao_tem_hex_solto():
    """Cor nova entra como token em tema.py; hex solto em outro arquivo de ui/ reprova."""
    achados = [
        f"{p.name}:{n}: {linha.strip()}"
        for p in sorted(PASTA_UI.glob("*.py")) if p.name != "tema.py"
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if HEX_LITERAL.search(linha)
    ]
    assert not achados, "Use os tokens de ui/tema.py:\n" + "\n".join(achados)


# Pares de texto realmente usados na interface: (texto, fundo)
PARES_TEXTO = [
    (tema.BRANCO, tema.AZUL_NAVBAR),          # botão primário e cabeçalho
    (tema.BRANCO, tema.VERMELHO_TEXTO),       # botão destrutivo (Excluir, Descartar)
    (tema.AZUL_NAVBAR, tema.BRANCO),          # botão secundário
    (tema.TEXTO, tema.BRANCO),
    (tema.CINZA_TEXTO, tema.BRANCO),
    (tema.CINZA_TEXTO, tema.FUNDO_JANELA),    # barra de status
    (tema.CINZA_TEXTO, tema.FUNDO_PAINEL),    # estado vazio da lista de cards
    (tema.AMARELO_TEXTO, tema.FUNDO_JANELA),
    (tema.AZUL_INFO_TEXTO, tema.FUNDO_JANELA),
    (tema.VERDE_TEXTO, tema.FUNDO_JANELA),
    (tema.VERMELHO_TEXTO, tema.FUNDO_JANELA),
    (tema.AZUL_TITULO, tema.BRANCO),
    (tema.CINZA_TEXTO, tema.CINZA_HOVER),     # botão primário desabilitado (ui/botoes.py)
    *[(texto, fundo) for fundo, texto in tema.SELO.values()],  # SELO guarda (fundo, texto)
]


@pytest.mark.parametrize("texto,fundo", PARES_TEXTO)
def test_pares_de_texto_passam_no_wcag_aa(texto, fundo):
    """Texto normal precisa de 4,5:1 (WCAG 2.1 AA)."""
    assert contraste(texto, fundo) >= 4.5, f"{texto} sobre {fundo}: {contraste(texto, fundo):.2f}:1"
