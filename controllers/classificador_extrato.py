"""
Classificador das linhas do extrato: diz o que cada movimento do banco é.

Fonte única para as decisões "isto é oferta?", "isto é aplicação?", "isto é tarifa?".
As regras ficam em dados (`regras_extrato.json`, versionado e empacotado pelo `AutoSIGA.spec`),
na ordem de prioridade: a primeira que casa decide. `montar_regras` aceita regras de outra
origem (por exemplo, do `config.json`) para pôr na frente das versionadas.

Linha que nenhuma regra pega: crédito vira OFERTA (regra da IT.TES.05, entrada na conta de
captação) e débito vira DESCONHECIDA, que nenhum fluxo lança por palpite.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

ENERGIA = "energia"
CONVENIO = "convenio"
BOLETO = "boleto"
FATURA_CARTAO = "fatura_cartao"
PIX_FORNECEDOR = "pix_fornecedor"
TARIFA = "tarifa"
COTA_CAPITAL = "cota_capital"
GUIA = "guia"  # DARF, GPS, FGTS, ISSQN
RENDIMENTO = "rendimento"
RESGATE = "resgate"
APLICACAO = "aplicacao"
DEPOSITO = "deposito"
TRANSFERENCIA = "transferencia"
OFERTA = "oferta"
DESCONHECIDA = "desconhecida"

# Movimentos de investimento: o robô lança na Movimentação Interna (aplicação e resgate)
# ou como Receita (rendimento)
INVESTIMENTOS = frozenset({APLICACAO, RESGATE, RENDIMENTO})

_ARQUIVO_REGRAS = Path(__file__).with_name("regras_extrato.json")


@dataclass(frozen=True)
class Regra:
    """Uma regra: se `padrao` casa no `campo` e o sinal confere, a linha é `categoria`."""

    categoria: str
    padrao: re.Pattern[str]
    sinal: str | None = None  # "+" crédito, "-" débito, None qualquer
    campo: str = "descricao"

    def casa(self, textos: dict[str, str], valor: float) -> bool:
        """Verdadeiro se a linha (textos já normalizados e valor) satisfaz a regra."""
        if self.sinal == "+" and valor <= 0 or self.sinal == "-" and valor >= 0:
            return False
        return bool(self.padrao.search(textos.get(self.campo, "")))


@dataclass(frozen=True)
class Classificacao:
    """Resultado: a categoria e a regra que decidiu (para log e para explicar ao usuário)."""

    categoria: str
    regra: str  # o padrão que casou, ou "padrão: crédito/débito sem regra"

    @property
    def eh_investimento(self) -> bool:
        return self.categoria in INVESTIMENTOS


def normalizar(texto: Any) -> str:
    """Sem acento, em maiúsculas e com espaços simples, como as regras esperam."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.upper().split())


def montar_regras(dados: list[dict[str, Any]]) -> tuple[Regra, ...]:
    """Compila as regras de uma lista de dicionários (do JSON ou do config.json).

    Raises:
        ValueError: regra sem categoria, com regex inválida, sinal ou campo desconhecido.
    """
    regras = []
    for i, d in enumerate(dados):
        categoria, padrao = d.get("categoria"), d.get("padrao")
        sinal, campo = d.get("sinal"), d.get("campo", "descricao")
        if not categoria or not padrao:
            raise ValueError(f"Regra {i} sem categoria ou padrão: {d}")
        if sinal not in (None, "+", "-") or campo not in ("descricao", "historico"):
            raise ValueError(f"Regra {i} com sinal ou campo inválido: {d}")
        try:
            compilado = re.compile(padrao)
        except re.error as e:
            raise ValueError(f"Regra {i} com regex inválida ({e}): {padrao}") from e
        regras.append(Regra(categoria, compilado, sinal, campo))
    return tuple(regras)


@lru_cache(maxsize=1)
def regras_padrao() -> tuple[Regra, ...]:
    """Regras versionadas em `regras_extrato.json` (lidas uma vez por execução)."""
    dados = json.loads(_ARQUIVO_REGRAS.read_text(encoding="utf-8"))
    return montar_regras(dados["regras"])


def classificar(transacao: dict[str, Any], regras: tuple[Regra, ...] | None = None) -> Classificacao:
    """Classifica uma linha do extrato (`descricao`, `historico` opcional e `valor`).

    Args:
        transacao: Linha como os leitores devolvem (OFX, XLS do Sicredi ou do Sicoob).
        regras: Regras a usar; sem elas, as versionadas.

    Returns:
        Classificacao: a categoria e o padrão que decidiu.
    """
    valor = float(transacao.get("valor") or 0.0)
    textos = {"descricao": normalizar(transacao.get("descricao")),
              "historico": normalizar(transacao.get("historico"))}
    for regra in regras if regras is not None else regras_padrao():
        if regra.casa(textos, valor):
            return Classificacao(regra.categoria, regra.padrao.pattern)
    if valor > 0:
        return Classificacao(OFERTA, "padrão: crédito sem regra")
    return Classificacao(DESCONHECIDA, "padrão: débito sem regra")
