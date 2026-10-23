"""
Leitura do extrato de conta corrente do Sicredi em XLS.

É o mesmo extrato do OFX em outro formato: título "Extrato", rótulo "Conta:" e a tabela
Data | Descrição | Documento | Valor (R$) | Saldo (R$). A saída tem o mesmo formato do
`OfxReader`, para o lote tratar os dois arquivos do mesmo jeito.

Diferenças em relação ao OFX que o leitor compensa:
- O OFX junta descrição e documento no MEMO ("DEBITO CONVENIOS-ENERGI 70 ..."); aqui
  o MEMO é remontado, porque os filtros de palavras-chave e a baixa de energia o leem.
- O banco corta a descrição em 48 caracteres, o que pode truncar o código de débito
  automático no fim ("... ID 0002"). Código cortado é descartado: sem ele a baixa de
  energia fica pendente em vez de casar com a fatura errada.
- Abaixo da tabela vêm o saldo do dia da emissão e os "Lançamentos Futuros", com datas
  válidas; a leitura para na primeira linha em branco depois dos movimentos.
"""

import logging
import re
from typing import Any

import xlrd

_TAMANHO_MAX_DESCRICAO = 48
# Período completo ("Dados referentes ao período de 01/09/2026 a 30/09/2026.")
_RE_PERIODO = re.compile(r"(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})")
_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
# Nome da operação: o texto antes do primeiro número da descrição
_RE_OPERACAO = re.compile(r"^(\D*?)\s*(\d.*)?$")
_RE_ID_NO_FIM = re.compile(r"(\bID)\s*\d*$")
_LARGURA_DOCUMENTO = 9  # o OFX traz o documento com largura fixa antes do restante da descrição
_TOLERANCIA_SALDO = 0.01


def eh_conta_corrente(sheet: Any) -> bool:
    """Diz se a aba é um extrato de conta corrente (tem as colunas Descrição e Documento).

    O de Capital Social tem a mesma tabela; ele fica com o `XlsReader`, que o recusa.
    """
    cabecalho = _linha_cabecalho(sheet)
    if cabecalho == -1:
        return False
    return not any("CAPITAL SOCIAL" in _texto(sheet, r, c).upper()
                   for r in range(cabecalho) for c in range(sheet.ncols))


def _texto(sheet: Any, r: int, c: int) -> str:
    return str(sheet.cell_value(r, c)).strip() if c < sheet.ncols else ""


def _linha_cabecalho(sheet: Any) -> int:
    for r in range(min(20, sheet.nrows)):
        titulos = [_texto(sheet, r, c).upper() for c in range(sheet.ncols)]
        if (titulos and titulos[0] == "DATA" and any(t.startswith("DESCRI") for t in titulos)
                and "DOCUMENTO" in titulos and any(t.startswith("VALOR") for t in titulos)):
            return r
    return -1


def _numero(sheet: Any, r: int, c: int) -> float | None:
    cell = sheet.cell(r, c)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        return float(cell.value)
    texto = str(cell.value).strip()
    if not texto:
        return None
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def montar_memo(descricao: str, documento: str) -> str:
    """Remonta o MEMO do OFX a partir da descrição e do documento do XLS.

    Args:
        descricao: Coluna Descrição ("DEBITO CONVENIOS 123 ENERGISA MS ID 0002").
        documento: Coluna Documento ("ENERGI 70").

    Returns:
        str: "DEBITO CONVENIOS-ENERGI 70 123 ENERGISA MS ID ..." como no OFX, sem o
        código final quando a descrição veio cortada pelo banco.
    """
    descricao = descricao.strip()
    if len(descricao) >= _TAMANHO_MAX_DESCRICAO:
        descricao = _RE_ID_NO_FIM.sub(r"\1", descricao)
    m = _RE_OPERACAO.match(descricao)
    operacao, resto = (m.group(1), m.group(2) or "") if m else (descricao, "")
    if not documento.strip():
        return f"{operacao}-{' ' * (_LARGURA_DOCUMENTO + 1)}{resto}".rstrip() if resto else operacao
    return f"{operacao}-{documento.ljust(_LARGURA_DOCUMENTO)} {resto}".rstrip()


def ler_conta_corrente(sheet: Any) -> dict[str, Any]:
    """Converte a aba do extrato de conta corrente no formato do `OfxReader`.

    Returns:
        dict: banco, conta_id, moeda, saldo_atual, data_saldo, data_inicial, data_final e
        transacoes ({"id", "data", "valor", "tipo", "descricao", "historico"}). O saldo fica
        None quando falta a coluna ou quando anterior + movimentos não fecha com o último.

    Raises:
        ValueError: Se faltar a conta, o período ou a tabela.
    """
    conta_id, data_inicial, data_final = "", None, None
    cabecalho = _linha_cabecalho(sheet)
    for r in range(max(cabecalho, 0)):
        rotulo = _texto(sheet, r, 0)
        if rotulo.startswith("Conta:"):
            conta_id = next((v for c in range(1, sheet.ncols) if (v := _texto(sheet, r, c))), "")
        periodo = _RE_PERIODO.search(" ".join(_texto(sheet, r, c) for c in range(sheet.ncols)))
        if periodo:
            data_inicial, data_final = periodo.groups()
    if cabecalho == -1:
        raise ValueError("Não foi possível localizar a tabela de movimentos no XLS de conta corrente.")
    if not conta_id:
        raise ValueError("Não foi possível identificar o número da Conta no arquivo XLS.")
    if not data_inicial:
        raise ValueError("Não foi possível identificar o período do extrato no arquivo XLS.")

    titulos = [_texto(sheet, cabecalho, c).upper() for c in range(sheet.ncols)]
    idx_desc = next(i for i, t in enumerate(titulos) if t.startswith("DESCRI"))
    idx_doc = titulos.index("DOCUMENTO")
    idx_valor = next(i for i, t in enumerate(titulos) if t.startswith("VALOR"))
    idx_saldo = next((i for i, t in enumerate(titulos) if t.startswith("SALDO")), -1)

    transacoes: list[dict[str, Any]] = []
    saldo_anterior: float | None = None
    ultimo_saldo: float | None = None
    for r in range(cabecalho + 1, sheet.nrows):
        data = _texto(sheet, r, 0)
        if not any(_texto(sheet, r, c) for c in range(sheet.ncols)):
            break  # fim da tabela: o que vem abaixo é saldo do dia e lançamentos futuros
        if any(_texto(sheet, r, c).upper().startswith("SALDO ANTERIOR") for c in range(sheet.ncols)):
            saldo_anterior = next((n for c in range(sheet.ncols) if (n := _numero(sheet, r, c)) is not None), None)
            continue
        valor = _numero(sheet, r, idx_valor)
        if not _RE_DATA.match(data) or valor is None:
            logging.warning(f"Linha {r} do XLS de conta corrente ignorada: {data!r}")
            continue
        memo = montar_memo(_texto(sheet, r, idx_desc), str(sheet.cell_value(r, idx_doc)))
        transacoes.append({"id": "", "data": data, "valor": valor, "tipo": "credit" if valor > 0 else "debit",
                           "descricao": memo, "historico": memo})
        if idx_saldo != -1:
            ultimo_saldo = _numero(sheet, r, idx_saldo)

    saldo_atual = ultimo_saldo if transacoes else saldo_anterior
    if saldo_anterior is None or saldo_atual is None or \
            abs(saldo_anterior + sum(t["valor"] for t in transacoes) - saldo_atual) > _TOLERANCIA_SALDO:
        saldo_atual = None

    return {
        "banco": "748",  # Sicredi
        "conta_id": conta_id,
        "moeda": "BRL",
        "saldo_atual": saldo_atual,
        "data_saldo": data_final if saldo_atual is not None else None,
        "data_inicial": data_inicial,
        "data_final": data_final,
        "transacoes": transacoes,
    }
