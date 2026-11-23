"""
Transferências entre contas do mesmo departamento: viram Movimentação Interna (TES01704).

No extrato do Sicredi cada ponta aparece como "TRANSF ENTRE CONTAS-SI00119 <CNPJ> ...": a
saída numa conta e a entrada na outra com o mesmo código, a mesma data e o mesmo valor.
Com as duas contas no lote, dá para saber origem e destino sem perguntar nada.

Regras (IT.TES.16 e IT.TES.10):
- as duas contas precisam ser da mesma localidade no SIGA; entre departamentos (ADM e
  Piedade, por exemplo) é Transf. Numerários, que fica como pendência;
- cada transferência é lançada uma vez só, pela conta de origem; a entrada na conta de
  destino casa sozinha na conferência;
- o que já está no SIGA (mesma data e valor na grade da origem) não é lançado de novo.

Decisão pura, sem navegador.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from controllers.classificador_extrato import normalizar
from controllers.prova_real import TOLERANCIA, normalizar_linhas_siga

_RE_TRANSF = re.compile(r"TRANSF ENTRE CONTAS-?\s*(SI\d+)")
_RE_CNPJ = re.compile(r"\b(\d{14})\b")

MOTIVO_SEM_PAR = "a outra ponta da transferência não está no lote"
MOTIVO_OUTRO_CNPJ = "CNPJ diferente do da administração: remessa entre administrações (Transf. Numerários) ou terceiro"
MOTIVO_OUTRO_DEPARTAMENTO = "contas de localidades diferentes: lance em Transf. Numerários (IT.TES.10)"


@dataclass(frozen=True)
class TransferenciaInterna:
    """Uma transferência com as duas pontas no lote, pronta para a TES01704."""

    codigo: str
    data: str
    valor: float          # positivo
    conta_origem: str     # código SIGA da conta corrente de onde saiu
    conta_destino: str    # código SIGA da conta corrente onde entrou
    descricao: str


@dataclass(frozen=True)
class PontaSolta:
    """Uma ponta que não virou movimentação interna, com o motivo para o painel."""

    conta_siga: str
    data: str
    valor: float
    descricao: str
    motivo: str


def codigo_transferencia(descricao: Any) -> str | None:
    """O código da operação ("SI00119") se a linha for uma transferência entre contas."""
    casa = _RE_TRANSF.search(normalizar(descricao))
    return casa.group(1) if casa else None


def _localidade(dados: dict[str, Any]) -> str:
    return normalizar(f"{dados.get('tipo_adm', '')} - {dados.get('nome_adm', '')}")


def parear(lote: list[dict[str, Any]]) -> tuple[list[TransferenciaInterna], list[PontaSolta]]:
    """Junta as pontas das transferências entre as contas correntes do lote.

    Args:
        lote: Extratos como o robô recebe (`transacoes`, `tipo_extrato`, `conta_siga_corrente`,
            `tipo_adm`, `nome_adm`).

    Returns:
        (pares completos, pontas soltas).
    """
    pontas = []
    for dados in lote:
        conta = str(dados.get("conta_siga_corrente") or "")
        if dados.get("tipo_extrato") == "APLICACAO" or not conta:
            continue
        for t in dados.get("transacoes") or []:
            codigo = codigo_transferencia(t.get("descricao"))
            if codigo:
                pontas.append((codigo, str(t.get("data", "")), round(float(t.get("valor") or 0.0), 2),
                               conta, _localidade(dados), str(t.get("descricao", ""))))

    pares, soltas, usadas = [], [], set()
    for i, (codigo, data, valor, conta, local, desc) in enumerate(pontas):
        if i in usadas or valor >= 0:
            continue
        par = next((j for j, p in enumerate(pontas) if j not in usadas and j != i and p[0] == codigo
                    and p[1] == data and abs(p[2] + valor) <= TOLERANCIA and p[3] != conta), None)
        if par is None:
            continue
        usadas.update({i, par})
        destino = pontas[par]
        if destino[4] != local:
            soltas += [PontaSolta(conta, data, valor, desc, MOTIVO_OUTRO_DEPARTAMENTO),
                       PontaSolta(destino[3], data, destino[2], destino[5], MOTIVO_OUTRO_DEPARTAMENTO)]
            continue
        pares.append(TransferenciaInterna(codigo, data, -valor, conta, destino[3], " ".join(desc.split())[:60]))
    # O CNPJ das transferências que casaram é o da própria administração; ponta solta com outro
    # CNPJ é remessa de outra administração (ou de terceiro), não movimentação interna
    proprios = {c for t in pares for c in _RE_CNPJ.findall(normalizar(t.descricao))}
    for i, p in enumerate(pontas):
        if i in usadas:
            continue
        cnpjs = set(_RE_CNPJ.findall(normalizar(p[5])))
        motivo = MOTIVO_OUTRO_CNPJ if proprios and cnpjs and not cnpjs & proprios else MOTIVO_SEM_PAR
        soltas.append(PontaSolta(p[3], p[1], p[2], p[5], motivo))
    return pares, soltas


def a_lancar(pares: list[TransferenciaInterna], conta_siga: str,
             grade: list[dict[str, Any]] | None) -> list[TransferenciaInterna]:
    """As transferências que saem desta conta e ainda não estão na grade dela (data e valor)."""
    livres = [m for m in normalizar_linhas_siga(grade) if m.valor < 0]
    faltam = []
    for t in pares:
        if t.conta_origem != conta_siga:
            continue
        achado = next((m for m in livres if m.data == t.data and abs(-m.valor - t.valor) <= TOLERANCIA), None)
        if achado is not None:
            livres.remove(achado)  # cada linha da grade casa uma vez só
        else:
            faltam.append(t)
    return faltam
