"""
Tarifas do extrato: o que lançar como despesa em Caixas e Bancos (TES01702), Fase 2.

Decisão pura, sem navegador. Parte das faltas da prova real (movimentos do banco sem
lançamento no SIGA), escolhe as que o classificador marca como TARIFA e monta um
lançamento por linha do extrato, para casar um a um na conferência seguinte.

As contas vêm da configuração (`config.json`, chave "tarifas") e o recurso nasce
desligado: só grava depois que o usuário confirmar a conta de despesa e o histórico.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from controllers.classificador_extrato import TARIFA, classificar
from controllers.prova_real import MovimentoBanco

# Levantados na TES01702 em 23/11/2026 (docs/regras/siga.md); o usuário confirma antes de ligar
PADRAO = {
    "ativo": False,
    "despesa": "3030",            # 3030 - DESPESAS BANCARIAS
    "historico": "012",           # 012 - DESP.BANCÁRIAS
    "tipo_documento": "AVISO DE DÉBITO",
    "forma_pagamento": "DÉBITO AUTOMÁTICO",
    "centro_custo": "ADM",
}


@dataclass(frozen=True)
class RegraTarifa:
    """Como a Administração lança tarifa no SIGA."""

    ativo: bool
    despesa: str
    historico: str
    tipo_documento: str
    forma_pagamento: str
    centro_custo: str

    @classmethod
    def da_config(cls, dados: dict[str, Any] | None) -> RegraTarifa:
        """Junta o que está no config.json com os padrões; chave desconhecida é ignorada."""
        valores = {**PADRAO, **{k: v for k, v in (dados or {}).items() if k in PADRAO}}
        return cls(ativo=bool(valores["ativo"]), despesa=str(valores["despesa"]),
                   historico=str(valores["historico"]), tipo_documento=str(valores["tipo_documento"]),
                   forma_pagamento=str(valores["forma_pagamento"]), centro_custo=str(valores["centro_custo"]))


@dataclass(frozen=True)
class LancamentoTarifa:
    """Uma despesa a gravar na TES01702."""

    data: str
    valor: float     # positivo: o valor da despesa
    descricao: str   # vai no complemento, para achar a linha do extrato depois
    documento: str   # Nº Documento: a data sem barras, como no lançamento manual de rendimento


def planejar(faltas: list[MovimentoBanco] | None, regra: RegraTarifa) -> list[LancamentoTarifa]:
    """Tarifas do extrato que ainda não estão no SIGA, uma por linha.

    Returns:
        list[LancamentoTarifa]: vazia se o recurso estiver desligado ou não houver tarifa.
    """
    if not regra.ativo:
        return []
    lancamentos = []
    for f in faltas or []:
        if f.valor >= 0 or classificar({"descricao": f.descricao, "valor": f.valor}).categoria != TARIFA:
            continue
        lancamentos.append(LancamentoTarifa(f.data, round(-f.valor, 2), " ".join(f.descricao.split())[:60],
                                            f.data.replace("/", "")))
    return lancamentos
