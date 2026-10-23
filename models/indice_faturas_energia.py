"""
Índice das faturas de energia guardadas em `faturas_energisa/`, pelo código de débito automático.

O banco identifica cada débito de energia pelo código de débito automático da UC
("DEBITO CONVENIOS-ENERGI 70 ID <código> ..."), e o mesmo código vem impresso no PDF.
O índice liga esse código às faturas (número, UC, valor, vencimento) para achar a
provisão certa na Contas a Pagar do SIGA.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from caminhos import diretorio_base
from models.pdf_extractor import PdfExtractor


@dataclass(frozen=True)
class FaturaEnergia:
    """Dados de uma fatura lidos do PDF."""

    numero: str
    uc: str
    valor: float
    vencimento: str
    codigo_debito: str
    caminho: str = ""


def pasta_faturas() -> str:
    """Pasta onde a importação de energia guarda os PDFs (ao lado do executável)."""
    return os.path.join(diretorio_base(), "faturas_energisa")


def montar_indice(pasta: str | None = None,
                  extrair: Callable[[str], dict[str, Any]] = PdfExtractor.extrair_dados_fatura,
                  ) -> dict[str, list[FaturaEnergia]]:
    """Lê os PDFs da pasta e agrupa as faturas pelo código de débito automático.

    PDFs sem código, sem número ou sem valor ficam de fora: sem eles não dá para
    casar o débito com a provisão com segurança.

    Args:
        pasta: Pasta dos PDFs (padrão: `faturas_energisa/` ao lado do executável).
        extrair: Leitor de PDF (trocado nos testes).

    Returns:
        dict: {código: [FaturaEnergia, ...]}, sem números de fatura repetidos.
    """
    pasta = pasta or pasta_faturas()
    indice: dict[str, list[FaturaEnergia]] = {}
    if not os.path.isdir(pasta):
        return indice

    vistos = set()
    for raiz, _, arquivos in os.walk(pasta):
        for nome in sorted(arquivos):
            if not nome.lower().endswith(".pdf"):
                continue
            caminho = os.path.join(raiz, nome)
            try:
                dados = extrair(caminho)
            except Exception as e:
                logging.warning(f"Fatura ilegível no índice de energia: {nome} ({e})")
                continue
            codigo = str(dados.get("codigo_debito", "")).strip()
            numero = str(dados.get("numero_fatura", "")).strip()
            valor = float(dados.get("valor") or 0.0)
            if not codigo or not numero or valor <= 0 or numero in vistos:
                continue
            vistos.add(numero)
            indice.setdefault(codigo, []).append(FaturaEnergia(
                numero=numero, uc=str(dados.get("uc", "")).strip(), valor=valor,
                vencimento=str(dados.get("vencimento", "")).strip(), codigo_debito=codigo, caminho=caminho))
    return indice
