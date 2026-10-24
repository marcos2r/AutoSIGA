"""
Quais faturas de energia entram na provisão do lote de extratos.

Pelo regime de competência, a provisão nasce no mês da fatura (o mês da emissão, a mesma
regra do lançamento na TES01502), e o débito no banco pode cair no mês seguinte. Por isso
o lote provisiona todas as faturas emitidas nos meses dos extratos, debitadas ou não, e
também as do mês anterior ao primeiro, que podem ter ficado sem provisão.
"""

import calendar
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

# A fatura emitida no fim do mês chega por e-mail alguns dias depois
_DIAS_APOS_O_MES = 10


def _mes(data: str) -> tuple[int, int] | None:
    try:
        d = datetime.strptime(data.strip(), "%d/%m/%Y")
    except (AttributeError, ValueError):
        return None
    return d.year, d.month


def _anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def meses_do_lote(extratos: Iterable[dict[str, Any]]) -> list[str]:
    """Meses de competência ("MM/AAAA") cobertos pelos extratos, mais o anterior ao primeiro.

    Args:
        extratos: Dados lidos dos arquivos (com data_inicial e data_final "DD/MM/AAAA").

    Returns:
        list[str]: Meses em ordem cronológica; vazia se nenhum extrato tiver período.
    """
    meses: set[tuple[int, int]] = set()
    for dados in extratos:
        inicio, fim = _mes(dados.get("data_inicial") or ""), _mes(dados.get("data_final") or "")
        if not inicio or not fim:
            continue
        atual = inicio
        while atual <= fim:
            meses.add(atual)
            atual = (atual[0] + 1, 1) if atual[1] == 12 else (atual[0], atual[1] + 1)
    if not meses:
        return []
    meses.add(_anterior(*min(meses)))
    return [f"{m:02d}/{a}" for a, m in sorted(meses)]


def janela_de_busca(meses: list[str]) -> tuple[date, date]:
    """Datas de recebimento do e-mail que cobrem as faturas emitidas nesses meses.

    Args:
        meses: Saída de `meses_do_lote` (não vazia).

    Returns:
        tuple[date, date]: Do primeiro dia do primeiro mês até alguns dias depois do último.
    """
    pares = sorted((int(m[3:]), int(m[:2])) for m in meses)
    (ano_ini, mes_ini), (ano_fim, mes_fim) = pares[0], pares[-1]
    ultimo_dia = calendar.monthrange(ano_fim, mes_fim)[1]
    return date(ano_ini, mes_ini, 1), date(ano_fim, mes_fim, ultimo_dia) + timedelta(days=_DIAS_APOS_O_MES)


def mes_de_corte(hoje: date) -> str:
    """Corte da importação da aba Energia ("MM/AAAA"): o mês anterior ao atual.

    Faturas mais antigas não são importadas por ali; as que faltarem entram pelo lote de
    extratos, que busca pelo período de cada extrato.
    """
    ano, mes = _anterior(hoje.year, hoje.month)
    return f"{mes:02d}/{ano}"


def competencia_da_fatura(fatura: dict[str, Any]) -> str:
    """Mês de competência da fatura ("MM/AAAA", o da emissão); vazio se a emissão não foi lida."""
    mes = _mes(fatura.get("emissao") or "")
    return f"{mes[1]:02d}/{mes[0]}" if mes else ""
