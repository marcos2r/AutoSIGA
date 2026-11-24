"""
Monta a descrição da Release a partir da seção da versão no docs/CHANGELOG.md.

Usado pelo CI (.github/workflows/ci_cd.yml) ao publicar uma tag vX.Y.Z: a Release passa a
trazer tudo o que foi implementado, e não só a lista automática de pull requests.

Uso: python scripts/notas_da_release.py v1.14.0 notas_release.md
"""

from __future__ import annotations

import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "docs" / "CHANGELOG.md"


def secao_do_changelog(texto: str, versao: str) -> str:
    """O texto da seção "## vX.Y.Z" até a próxima "## ", sem o título.

    Args:
        texto: Conteúdo do CHANGELOG.
        versao: "v1.14.0" ou "1.14.0".

    Raises:
        ValueError: a versão não tem seção no CHANGELOG (a Release não sai sem descrição).
    """
    alvo = f"## v{versao.lstrip('v')}"
    linhas = texto.splitlines()
    try:
        inicio = next(i for i, linha in enumerate(linhas) if linha.strip() == alvo)
    except StopIteration:
        raise ValueError(f"{alvo} não está no docs/CHANGELOG.md") from None
    fim = next((i for i in range(inicio + 1, len(linhas)) if linhas[i].startswith("## ")), len(linhas))
    corpo = "\n".join(linhas[inicio + 1:fim]).strip()
    if not corpo:
        raise ValueError(f"{alvo} está vazia no docs/CHANGELOG.md")
    return corpo


def main(argv: list[str]) -> int:
    versao, destino = argv[1], Path(argv[2])
    corpo = secao_do_changelog(CHANGELOG.read_text(encoding="utf-8"), versao)
    destino.write_text(f"## O que há de novo na {versao}\n\n{corpo}\n\n"
                       "Histórico completo em `docs/CHANGELOG.md`.\n", encoding="utf-8")
    print(f"Descrição da Release {versao} gravada em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
