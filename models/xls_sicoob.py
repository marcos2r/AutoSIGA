"""
Leitura dos extratos e relatórios em Excel (.xlsx e .xls) gerados pelo Sicoob (banco 756).

Suporta os dois modelos exportados pelo Sicoob / SISBR:
1. Extrato de Conta Corrente (.xlsx, aba "LANÇAMENTOS"):
   Tabela DATA | DOCUMENTO | HISTÓRICO | INFORMAÇÕES COMPLEMENTARES | VALOR, com dias em
   ordem decrescente, linhas "SALDO DO DIA" após os movimentos de cada dia e "SALDO ANTERIOR"
   no rodapé. Não traz o número da conta nas células; usa o número do nome do arquivo quando
   presente, ou "SICOOB" para o usuário escolher a conta no card.
2. Extrato PIX de Recebimentos (.xlsx e .xls, aba "Extrato Pix"):
   Cabeçalho com Cooperativa, Conta Corrente e Período, tabela Data Movimento | Histórico |
   Pagador | CPF/CNPJ do Pagador | Instituição | Valor, e rodapé "Resumo" com total e
   quantidade. Como traz só entradas de PIX (sem saldo nem demais movimentos da conta),
   marca `movimentos_completos=False` para servir às ofertas sem distorcer a prova real.
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import openpyxl
import xlrd

from controllers.catalogo_contas import normalizar_texto
from models.ofx_reader import OfxReader

BANCO_SICOOB = "756"
CONTA_PADRAO_SICOOB = "SICOOB"
_TOLERANCIA_SALDO = 0.01

_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RE_PERIODO = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(?:a|at[eé])\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
_RE_CONTA_CABECALHO = re.compile(r"CONTA(?:\s+CORRENTE)?\s*:\s*([\d.]*-\d)", re.IGNORECASE)
_RE_CONTA_NUMERO = re.compile(r"(?<!\d)(\d[\d.]{2,10}-\d)(?!\d)")
_RE_CARIMBO_ARQUIVO = re.compile(r"[_-]\d{6,14}")
_RE_TOTAL_RESUMO = re.compile(r"VALOR\s+TOTAL\s*:\s*R?\$?\s*([\d.,]+)", re.IGNORECASE)
_RE_QTD_RESUMO = re.compile(r"QUANTIDADE\s+DE\s+REGISTROS\s*:\s*(\d+)", re.IGNORECASE)


@dataclass
class _CelulaOpenpyxl:
    """Imita `xlrd.sheet.Cell` para que os leitores tratem `.xls` e `.xlsx` do mesmo jeito."""

    value: Any
    ctype: int


class _AbaOpenpyxl:
    """Adaptador de worksheet do `openpyxl` com a interface 0-based do `xlrd`."""

    def __init__(self, ws: Any) -> None:
        self._linhas: list[list[_CelulaOpenpyxl]] = []
        for row in ws.iter_rows(values_only=True):
            self._linhas.append([self._converter(v) for v in row])
        self.nrows = len(self._linhas)
        self.ncols = max((len(r) for r in self._linhas), default=0)

    @staticmethod
    def _converter(valor: Any) -> _CelulaOpenpyxl:
        if valor is None:
            return _CelulaOpenpyxl("", xlrd.XL_CELL_EMPTY)
        if isinstance(valor, (datetime, date)):
            return _CelulaOpenpyxl(valor.strftime("%d/%m/%Y"), xlrd.XL_CELL_TEXT)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return _CelulaOpenpyxl(float(valor), xlrd.XL_CELL_NUMBER)
        texto = str(valor)
        return _CelulaOpenpyxl(texto, xlrd.XL_CELL_TEXT if texto != "" else xlrd.XL_CELL_EMPTY)

    def cell(self, r: int, c: int) -> _CelulaOpenpyxl:
        if 0 <= r < self.nrows and 0 <= c < len(self._linhas[r]):
            return self._linhas[r][c]
        return _CelulaOpenpyxl("", xlrd.XL_CELL_EMPTY)

    def cell_value(self, r: int, c: int) -> Any:
        return self.cell(r, c).value


class _PlanilhaOpenpyxl:
    """Adaptador de workbook do `openpyxl` compatível com `xlrd.Book`."""

    def __init__(self, wb: Any) -> None:
        self._wb = wb

    def sheet_names(self) -> list[str]:
        return list(self._wb.sheetnames)

    def sheet_by_index(self, idx: int) -> _AbaOpenpyxl:
        return _AbaOpenpyxl(self._wb[self._wb.sheetnames[idx]])


def abrir_workbook(caminho: str) -> Any:
    """Abre um arquivo `.xls` (via `xlrd`) ou `.xlsx` (via `openpyxl`).

    Arquivos `.xls` gerados pelo SISBR/Sicoob costumam trazer setores OLE que disparam
    `CompDocError` no `xlrd` estrito; nesses casos, reabre ignorando a corrupção do container.
    """
    if caminho.lower().endswith(".xlsx"):
        return _PlanilhaOpenpyxl(openpyxl.load_workbook(caminho, data_only=True))
    try:
        return xlrd.open_workbook(caminho)
    except xlrd.compdoc.CompDocError:
        return xlrd.open_workbook(caminho, ignore_workbook_corruption=True)


def eh_planilha_sicoob(sheet: Any) -> bool:
    """Diz se a aba é um extrato de conta corrente ou relatório PIX do Sicoob."""
    return _linha_cabecalho_extrato(sheet) != -1 or _linha_cabecalho_pix(sheet) != -1


def ler_planilha_sicoob(sheet: Any, caminho: str = "") -> dict[str, Any]:
    """Lê a aba do Sicoob (extrato de conta corrente ou relatório PIX) no formato do `OfxReader`."""
    if _linha_cabecalho_extrato(sheet) != -1:
        return ler_extrato_sicoob(sheet, caminho)
    if _linha_cabecalho_pix(sheet) != -1:
        return ler_relatorio_pix_sicoob(sheet, caminho)
    raise ValueError("A planilha não corresponde a um formato de extrato Sicoob conhecido.")


def _texto(sheet: Any, r: int, c: int) -> str:
    return str(sheet.cell_value(r, c)).strip() if c < sheet.ncols else ""


def _numero_moeda(sheet: Any, r: int, c: int) -> float | None:
    """Lê um valor numérico ou moeda brasileira ('R$ 1.200,00', '-141,84') da célula."""
    cell = sheet.cell(r, c)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        return float(cell.value)
    texto = str(cell.value).replace("R$", "").replace("\xa0", "").strip()
    if not texto:
        return None
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _linha_cabecalho_extrato(sheet: Any) -> int:
    for r in range(min(20, sheet.nrows)):
        titulos = [normalizar_texto(_texto(sheet, r, c)) for c in range(sheet.ncols)]
        if (
            len(titulos) >= 5
            and titulos[0] == "DATA"
            and "DOCUMENTO" in titulos
            and any(t.startswith("HIST") for t in titulos)
            and any("COMPLEMENTAR" in t for t in titulos)
            and any(t.startswith("VALOR") for t in titulos)
        ):
            return r
    return -1


def _linha_cabecalho_pix(sheet: Any) -> int:
    for r in range(min(25, sheet.nrows)):
        titulos = [normalizar_texto(_texto(sheet, r, c)) for c in range(sheet.ncols)]
        if (
            len(titulos) >= 6
            and any("DATA" in t for t in titulos)
            and any(t.startswith("HIST") for t in titulos)
            and "PAGADOR" in titulos
            and any(t.startswith("VALOR") for t in titulos)
        ):
            return r
    return -1


def montar_historico_sicoob(historico: str, info_complementar: str) -> str:
    """Combina o HISTÓRICO e as INFORMAÇÕES COMPLEMENTARES em uma única linha legível.

    Segue o mesmo padrão do `OfxReader` para o Sicoob:
    - Em PIX ("Recebimento Pix\\nFulano\\n***.123.456-**"), junta "Recebimento Pix Fulano".
    - Em TED/transferência ("JAIME MACEDO\\n724...\\nCODIGO TED..."), usa a linha do nome.
    - Em depósito com CPF e envelope, junta as linhas com " - ".
    """
    descricao = " ".join(historico.replace(";", ",").split())
    linhas = [" ".join(l.replace(";", ",").split()) for l in (info_complementar or "").splitlines() if l.strip()]
    if not linhas:
        return descricao

    primeira_upper = normalizar_texto(linhas[0])
    if primeira_upper.startswith(("RECEBIMENTO PIX", "PAGAMENTO PIX", "TRANSFERENCIA PIX")) and len(linhas) >= 2:
        detalhe = f"{linhas[0]} {linhas[1]}"
    elif primeira_upper.startswith("CPF:"):
        detalhe = " - ".join(linhas)
    else:
        detalhe = linhas[0]
    return OfxReader._montar_historico(descricao, detalhe)


def _extrair_conta(sheet: Any, ate_linha: int, caminho: str) -> str:
    """Procura o número da conta no topo da planilha ou no nome do arquivo; fallback 'SICOOB'."""
    for r in range(max(ate_linha, 0)):
        linha_str = " ".join(_texto(sheet, r, c) for c in range(sheet.ncols))
        m_cab = _RE_CONTA_CABECALHO.search(linha_str)
        if m_cab:
            return m_cab.group(1)
        m_num = _RE_CONTA_NUMERO.search(linha_str)
        if m_num:
            return m_num.group(1)

    if caminho:
        nome_limpo = _RE_CARIMBO_ARQUIVO.sub("", os.path.splitext(os.path.basename(caminho))[0])
        m_arq = _RE_CONTA_NUMERO.search(nome_limpo)
        if m_arq:
            return m_arq.group(1)
    return CONTA_PADRAO_SICOOB


def _chave_data(data_str: str) -> datetime:
    return datetime.strptime(data_str, "%d/%m/%Y")


def ler_extrato_sicoob(sheet: Any, caminho: str = "") -> dict[str, Any]:
    """Lê o extrato de conta corrente do Sicoob em XLSX/XLS e devolve no formato do `OfxReader`."""
    cabecalho = _linha_cabecalho_extrato(sheet)
    if cabecalho == -1:
        raise ValueError("Não foi possível localizar a tabela de lançamentos no extrato Sicoob.")

    titulos = [normalizar_texto(_texto(sheet, cabecalho, c)) for c in range(sheet.ncols)]
    idx_data = titulos.index("DATA")
    idx_hist = next(i for i, t in enumerate(titulos) if t.startswith("HIST"))
    idx_info = next(i for i, t in enumerate(titulos) if "COMPLEMENTAR" in t)
    idx_valor = next(i for i, t in enumerate(titulos) if t.startswith("VALOR"))

    conta_id = _extrair_conta(sheet, cabecalho, caminho)
    por_dia: dict[str, list[dict[str, Any]]] = {}
    saldos_do_dia: list[tuple[str, float]] = []
    saldo_anterior: float | None = None
    data_saldo_anterior: str | None = None

    for r in range(cabecalho + 1, sheet.nrows):
        if not any(_texto(sheet, r, c) for c in range(sheet.ncols)):
            continue
        data = _texto(sheet, r, idx_data)
        hist = _texto(sheet, r, idx_hist)
        info = _texto(sheet, r, idx_info)
        valor = _numero_moeda(sheet, r, idx_valor)
        if not _RE_DATA.match(data) or valor is None:
            logging.warning(f"Linha {r} do extrato Sicoob ignorada: data={data!r}")
            continue

        hist_norm = normalizar_texto(hist)
        if "SALDO BLOQUEADO" in hist_norm:
            continue
        if hist_norm.startswith("SALDO ANTERIOR"):
            saldo_anterior = valor
            data_saldo_anterior = data
            continue
        if hist_norm.startswith(("SALDO DO DIA", "SALDO ATUAL")):
            saldos_do_dia.append((data, valor))
            continue

        descricao = " ".join(hist.split())
        historico = montar_historico_sicoob(descricao, info)
        por_dia.setdefault(data, []).append({
            "id": "",
            "data": data,
            "valor": valor,
            "tipo": "credit" if valor > 0 else "debit",
            "descricao": descricao,
            "historico": historico,
        })

    # O Sicoob exporta os dias do mais recente para o mais antigo; reordena por data crescente
    datas_ordenadas = sorted(por_dia.keys(), key=_chave_data)
    transacoes = [tx for d in datas_ordenadas for tx in por_dia[d]]

    saldos_ordenados = sorted(saldos_do_dia, key=lambda item: _chave_data(item[0]))
    ultimo_saldo = saldos_ordenados[-1][1] if saldos_ordenados else saldo_anterior
    data_ultimo_saldo = saldos_ordenados[-1][0] if saldos_ordenados else data_saldo_anterior

    data_inicial: str | None = None
    if data_saldo_anterior:
        data_inicial = (_chave_data(data_saldo_anterior) + timedelta(days=1)).strftime("%d/%m/%Y")
    elif datas_ordenadas:
        data_inicial = datas_ordenadas[0]

    data_final: str | None = data_ultimo_saldo or (datas_ordenadas[-1] if datas_ordenadas else data_inicial)

    saldo_atual: float | None = ultimo_saldo
    soma_tx = sum(t["valor"] for t in transacoes)
    if (
        saldo_anterior is None
        or saldo_atual is None
        or abs(saldo_anterior + soma_tx - saldo_atual) > _TOLERANCIA_SALDO
    ):
        if saldo_anterior is not None and saldo_atual is not None:
            logging.warning(
                f"Saldos do extrato Sicoob não fecham: anterior={saldo_anterior:.2f}, "
                f"movimentos={soma_tx:.2f}, final={saldo_atual:.2f}."
            )
        saldo_atual = None

    return {
        "banco": BANCO_SICOOB,
        "conta_id": conta_id,
        "moeda": "BRL",
        "saldo_atual": round(saldo_atual, 2) if saldo_atual is not None else None,
        "data_saldo": data_final if saldo_atual is not None else None,
        "data_inicial": data_inicial,
        "data_final": data_final,
        "transacoes": transacoes,
    }


def ler_relatorio_pix_sicoob(sheet: Any, caminho: str = "") -> dict[str, Any]:
    """Lê o Relatório/Extrato PIX de Recebimentos do Sicoob (.xlsx ou .xls)."""
    cabecalho = _linha_cabecalho_pix(sheet)
    if cabecalho == -1:
        raise ValueError("Não foi possível localizar a tabela no Extrato PIX do Sicoob.")

    conta_id = _extrair_conta(sheet, cabecalho, caminho)
    data_inicial, data_final = None, None
    for r in range(cabecalho):
        texto_linha = " ".join(_texto(sheet, r, c) for c in range(sheet.ncols))
        m_per = _RE_PERIODO.search(texto_linha)
        if m_per:
            data_inicial, data_final = m_per.group(1), m_per.group(2)

    titulos = [normalizar_texto(_texto(sheet, cabecalho, c)) for c in range(sheet.ncols)]
    idx_data = next(i for i, t in enumerate(titulos) if "DATA" in t)
    idx_hist = next(i for i, t in enumerate(titulos) if t.startswith("HIST"))
    idx_pagador = titulos.index("PAGADOR")
    idx_valor = next(i for i, t in enumerate(titulos) if t.startswith("VALOR"))

    transacoes: list[dict[str, Any]] = []
    total_resumo: float | None = None
    qtd_resumo: int | None = None

    for r in range(cabecalho + 1, sheet.nrows):
        linha_str = " ".join(_texto(sheet, r, c) for c in range(sheet.ncols)).strip()
        if not linha_str:
            continue
        m_tot = _RE_TOTAL_RESUMO.search(linha_str)
        if m_tot:
            total_resumo = float(m_tot.group(1).replace(".", "").replace(",", "."))
            continue
        m_qtd = _RE_QTD_RESUMO.search(linha_str)
        if m_qtd:
            qtd_resumo = int(m_qtd.group(1))
            continue

        data = _texto(sheet, r, idx_data)
        if not _RE_DATA.match(data):
            continue
        valor = _numero_moeda(sheet, r, idx_valor)
        if valor is None:
            continue
        hist = " ".join(_texto(sheet, r, idx_hist).replace(";", ",").split())
        pagador = " ".join(_texto(sheet, r, idx_pagador).replace(";", ",").split())
        transacoes.append({
            "id": "",
            "data": data,
            "valor": valor,
            "tipo": "credit" if valor > 0 else "debit",
            "descricao": hist,
            "historico": OfxReader._montar_historico(hist, pagador),
        })

    if qtd_resumo is not None and len(transacoes) != qtd_resumo:
        raise ValueError(
            f"Quantidade de registros no Extrato PIX ({len(transacoes)}) diverge do resumo ({qtd_resumo})."
        )
    if total_resumo is not None and abs(sum(t["valor"] for t in transacoes) - total_resumo) > _TOLERANCIA_SALDO:
        raise ValueError("Soma dos recebimentos PIX diverge do Valor Total informado no resumo.")

    if not data_inicial and transacoes:
        datas_ord = sorted((t["data"] for t in transacoes), key=_chave_data)
        data_inicial, data_final = datas_ord[0], datas_ord[-1]

    return {
        "banco": BANCO_SICOOB,
        "conta_id": conta_id,
        "moeda": "BRL",
        "saldo_atual": None,
        "data_saldo": None,
        "data_inicial": data_inicial,
        "data_final": data_final,
        "movimentos_completos": False,
        "transacoes": transacoes,
    }
