"""
Leitor do extrato mensal do cartão empresarial Sicredi (XLS "Cartão Sicredi Visa Empresarial").

A fatura não é extrato de conta: traz as compras de cada portador, o vencimento e o total
que será debitado na conta corrente ("DEB.CTA.FATURA" no extrato). O robô usa as compras para
achar as provisões que esse débito quita (controllers/baixa_cartao.py). O PDF que o banco
oferece só traz o resumo (vencimento e total), sem as compras, por isso o XLS é o usado.

Formato (aba "Relatorio", visto em 24/11/2026):
    Conta Corrente: | 58416-3
    Cartão Sicredi Visa Empresarial - Extrato Mensal
    Data de Vencimento: | 13/10/2026
    Valor Total(R$): | 6.267,40
    Histórico de Despesas / Despesas no Brasil
    Cartão: 4960.45XX.XXXX.0119 - NOME DO PORTADOR
    Data | Descrição | Parcela | Valor (R$)
    24/09/2026 | DELICATESSEN PANIFIC | 01/01 | 182,12
    13/09/2026 | Pag Fat Deb Cc | 01/01 | -3.747,26   (pagamento da fatura anterior: ignorado)
    Total R$: | 2.520,14
"""

from __future__ import annotations

import re
from typing import Any

TIPO_FATURA_CARTAO = "FATURA_CARTAO"
_MARCA = "CARTAO SICREDI"
_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _texto(valor: Any) -> str:
    return " ".join(str(valor if valor is not None else "").split())


def _sem_acento_maiusculo(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").upper()


def _valor(texto: Any) -> float | None:
    if isinstance(texto, (int, float)):
        return float(texto)
    limpo = _texto(texto).replace("R$", "").replace(" ", "")
    if not limpo:
        return None
    try:
        return float(limpo.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _linhas(sheet: Any) -> list[list[str]]:
    """Linhas como texto; usa `cell_value`, que o xlrd e o leitor de .xlsx (abrir_workbook) oferecem."""
    ncols = getattr(sheet, "ncols", 0) or max((len(sheet.row_values(i)) for i in range(sheet.nrows)), default=0)
    return [[_texto(sheet.cell_value(i, j)) for j in range(ncols)] for i in range(sheet.nrows)]


def eh_fatura_cartao(sheet: Any) -> bool:
    """A planilha é o extrato mensal do cartão empresarial Sicredi?"""
    for linha in _linhas(sheet)[:12]:
        texto = _sem_acento_maiusculo(" ".join(linha))
        if _MARCA in texto and "EXTRATO" in texto:
            return True
    return False


def ler_fatura_cartao(sheet: Any, caminho: str = "") -> dict[str, Any]:
    """Lê a fatura: conta corrente, vencimento, total e as compras no Brasil e no exterior.

    Returns:
        dict: {"tipo_extrato": "FATURA_CARTAO", "banco": "748", "conta_id", "vencimento",
        "total", "compras": [{"data", "descricao", "parcela", "valor", "portador"}],
        "caminho_arquivo"}.

    Raises:
        ValueError: sem vencimento ou total, ou as compras não somam o total da fatura.
    """
    conta, vencimento, total, portador = "", "", None, ""
    compras: list[dict[str, Any]] = []
    for linha in _linhas(sheet):
        celulas = [c for c in linha if c]
        if not celulas:
            continue
        rotulo = _sem_acento_maiusculo(celulas[0])
        if rotulo.startswith("CONTA CORRENTE") and len(celulas) > 1:
            conta = celulas[1]
        elif rotulo.startswith("DATA DE VENCIMENTO") and len(celulas) > 1 and not vencimento:
            vencimento = celulas[1]
        elif rotulo.startswith("VALOR TOTAL") and len(celulas) > 1 and total is None:
            total = _valor(celulas[1])
        elif rotulo.startswith("CARTAO:"):
            portador = celulas[0].split(" - ", 1)[1].strip() if " - " in celulas[0] else ""
        elif _RE_DATA.match(celulas[0]) and len(celulas) >= 3:
            valor = _valor(celulas[-1])
            descricao = celulas[1]
            # Pagamento da fatura anterior aparece como linha negativa: não é compra
            if valor is None or valor <= 0 or "PAG FAT" in _sem_acento_maiusculo(descricao):
                continue
            parcela = celulas[2] if len(celulas) >= 4 else ""
            compras.append({"data": celulas[0], "descricao": descricao, "parcela": parcela,
                            "valor": round(valor, 2), "portador": portador})
    if not vencimento or total is None:
        raise ValueError("Fatura do cartão sem data de vencimento ou valor total.")
    soma = round(sum(c["valor"] for c in compras), 2)
    if abs(soma - total) > 0.01:
        raise ValueError(f"As compras da fatura somam {soma:.2f}, mas o total é {total:.2f}: arquivo incompleto?")
    return {"tipo_extrato": TIPO_FATURA_CARTAO, "banco": "748", "conta_id": conta, "vencimento": vencimento,
            "total": round(total, 2), "compras": compras, "caminho_arquivo": caminho}
