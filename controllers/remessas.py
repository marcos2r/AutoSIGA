"""
Remessas entre administrações no extrato (Transf. Numerários, TES01301), Fase 3.

Uma transferência com "CONGREGACAO" na descrição e CNPJ diferente do da própria
administração é remessa (IT.TES.10): enviada quando sai da conta, recebida quando entra.
Ex. real (Dourados, 10/2026): "TRANSF ENTRE CONTAS-SI00074 03794799000123 CONGREGACAO CRISTA".

O que o robô faz com cada uma (bot, quando a tela estiver mapeada):
- recebida: confirma o recebimento pendente no SIGA com a mesma data e valor;
- enviada: lança, aprova e envia, mas só se o CNPJ de destino estiver cadastrado no
  config.json ("remessas": {"<cnpj>": {"destino": "ADM - ...", "finalidade": "3403"}});
  sem cadastro vira pendência pedindo o destino.

Decisão pura, sem navegador.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from controllers.classificador_extrato import normalizar

_RE_CNPJ = re.compile(r"\b(\d{14})\b")
_RE_CODIGO = re.compile(r"\b(SI\d+)\b")

ENVIADA = "enviada"
RECEBIDA = "recebida"

FINALIDADE_PADRAO = "3403"  # Transf. remetidas administrativas (IT.TES.08/10/22)


@dataclass(frozen=True)
class Remessa:
    """Uma remessa entre administrações vista no extrato."""

    conta_siga: str
    data: str
    valor: float          # positivo
    sentido: str          # ENVIADA ou RECEBIDA
    cnpj: str             # da outra administração
    codigo: str           # código da operação no banco ("SI00074"), ou ""
    descricao: str
    destino: str = ""     # só nas enviadas com cadastro no config
    finalidade: str = ""

    @property
    def pronta(self) -> bool:
        """Recebida sempre pode ser confirmada; enviada precisa do destino cadastrado."""
        return self.sentido == RECEBIDA or bool(self.destino)


def cnpjs_da_linha(descricao: Any) -> set[str]:
    return set(_RE_CNPJ.findall(normalizar(descricao)))


def reconhecer(lote: list[dict[str, Any]], proprios: set[str],
               cadastro: dict[str, Any] | None = None) -> list[Remessa]:
    """As remessas das contas correntes do lote.

    Args:
        lote: Extratos como o robô recebe (`transacoes`, `conta_siga_corrente`, `tipo_extrato`).
        proprios: CNPJs da própria administração (de `transferencias_internas`, ou do config).
        cadastro: Destinos por CNPJ, do config.json ("remessas").

    Returns:
        list[Remessa]: na ordem do lote.
    """
    remessas = []
    for dados in lote:
        conta = str(dados.get("conta_siga_corrente") or "")
        if dados.get("tipo_extrato") == "APLICACAO" or not conta:
            continue
        for t in dados.get("transacoes") or []:
            desc = normalizar(t.get("descricao"))
            outros = cnpjs_da_linha(desc) - proprios
            valor = float(t.get("valor") or 0.0)
            if "CONGREGACAO" not in desc or not outros or not valor:
                continue
            cnpj = sorted(outros)[0]
            achado = _RE_CODIGO.search(desc)
            codigo = achado.group(1) if achado else ""
            sentido = ENVIADA if valor < 0 else RECEBIDA
            destino, finalidade = "", ""
            if sentido == ENVIADA:
                dados_destino = (cadastro or {}).get(cnpj)
                if isinstance(dados_destino, dict) and dados_destino.get("destino"):
                    destino = str(dados_destino["destino"])
                    finalidade = str(dados_destino.get("finalidade") or FINALIDADE_PADRAO)
            remessas.append(Remessa(conta, str(t.get("data", "")), round(abs(valor), 2), sentido, cnpj, codigo,
                                    " ".join(str(t.get("descricao", "")).split())[:60], destino, finalidade))
    return remessas


def motivo_pendente(r: Remessa) -> str:
    """Frase para o painel quando a remessa não pôde seguir sozinha."""
    if r.sentido == ENVIADA and not r.destino:
        return (f"remessa enviada ao CNPJ {r.cnpj}: cadastre o destino desse CNPJ no config.json "
                "(\"remessas\") para o robô lançar em Transf. Numerários")
    return ""
