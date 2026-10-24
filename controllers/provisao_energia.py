"""
Quais faturas de energia do período ainda precisam de provisão na Contas a Pagar.

O SIGA é a única referência do que já foi lançado: o robô roda em várias máquinas da
mesma administração, e nenhuma sabe o que a outra lançou. Uma fatura conta como
provisionada quando a TES01501 tem uma provisão da Energisa:
- com o mesmo Nº Doc. (o número da fatura, como o robô lança); ou
- lançada à mão, com o código de débito automático da UC no Nº Doc. ("1012345678" para
  o código 00012345678) e o mesmo valor. O mesmo código com outro valor é a fatura de
  outro mês da mesma UC.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from controllers.baixa_energia import TOLERANCIA, ProvisaoSiga, mesmo_documento

LANCAR = "lancar"
JA_LANCADA = "ja_lancada"
JA_LANCADA_MANUAL = "ja_lancada_manual"
SEM_LOCALIDADE = "sem_localidade"
SEM_EMISSAO = "sem_emissao"
SEM_NUMERO = "sem_numero"

# Situação depois de executar
LANCADA = "lancada"
NAO_LANCADA = "nao_lancada"
NAO_AUTORIZADA = "nao_autorizada"

# Código curto demais casaria por acaso com o fim de outro número
_MIN_DIGITOS_CODIGO = 6


@dataclass(frozen=True)
class DecisaoProvisao:
    """O que fazer com uma fatura do período e por quê (texto pronto para o painel)."""

    fatura: dict[str, Any] = field(hash=False)
    acao: str
    motivo: str


def _digitos(texto: Any) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def chave_do_codigo(codigo_debito: str) -> str:
    """Parte significativa do código de débito, como aparece no Nº Doc. lançado à mão."""
    chave = _digitos(codigo_debito).lstrip("0")
    return chave if len(chave) >= _MIN_DIGITOS_CODIGO else ""


def provisao_existente(fatura: dict[str, Any], provisoes: list[ProvisaoSiga]) -> tuple[str, ProvisaoSiga | None]:
    """Procura a provisão da fatura entre as lidas da TES01501.

    Returns:
        tuple: (JA_LANCADA, provisão) pelo número da fatura; (JA_LANCADA_MANUAL, provisão)
        pelo código de débito e valor; (LANCAR, None) se não há nenhuma.
    """
    numero = str(fatura.get("numero_fatura") or "")
    por_numero = [p for p in provisoes if numero and mesmo_documento(p.numero, numero)]
    if por_numero:
        return JA_LANCADA, por_numero[0]
    chave = chave_do_codigo(fatura.get("codigo_debito", ""))
    valor = float(fatura.get("valor") or 0.0)
    manuais = [p for p in provisoes
               if chave and _digitos(p.numero).endswith(chave) and abs(p.valor - valor) <= TOLERANCIA]
    if manuais:
        return JA_LANCADA_MANUAL, manuais[0]
    return LANCAR, None


def _descricao(fatura: dict[str, Any]) -> str:
    numero = fatura.get("numero_fatura") or "sem número"
    origem = f" · {fatura['origem']}" if fatura.get("origem") else ""
    return f"fatura {numero} · UC {fatura.get('uc', '')}{origem}"


def decidir_provisoes(validas: list[dict[str, Any]], sem_localidade: list[dict[str, Any]],
                      sem_emissao: list[dict[str, Any]], provisoes: list[ProvisaoSiga]) -> list[DecisaoProvisao]:
    """Decide, fatura a fatura, o que provisionar.

    Args:
        validas: Faturas do período com UC mapeada para uma localidade.
        sem_localidade: Faturas cuja UC ainda não tem localidade.
        sem_emissao: Faturas sem data de emissão legível (sem competência).
        provisoes: Provisões da Energisa lidas da TES01501.

    Returns:
        list[DecisaoProvisao]: Uma decisão por fatura, na ordem recebida.
    """
    decisoes = []
    for fat in validas:
        if not fat.get("numero_fatura"):
            decisoes.append(DecisaoProvisao(fat, SEM_NUMERO, "o PDF não traz o número da fatura: lance pela aba Energia"))
            continue
        acao, provisao = provisao_existente(fat, provisoes)
        if acao == JA_LANCADA and provisao:
            iguais = sum(1 for p in provisoes if mesmo_documento(p.numero, provisao.numero))
            motivo = f"já provisionada ({provisao.status})"
            if iguais > 1:
                motivo += f"; está lançada {iguais} vezes no SIGA, confira"
        elif acao == JA_LANCADA_MANUAL and provisao:
            motivo = f"já lançada à mão (Nº Doc. {provisao.numero}, {provisao.status})"
        else:
            motivo = f"provisionar em {fat.get('localidade_nome', '')}, vencimento {fat.get('vencimento', '')}"
        decisoes.append(DecisaoProvisao(fat, acao, motivo))
    decisoes += [DecisaoProvisao(f, SEM_LOCALIDADE, "UC sem localidade: cadastre na aba Energia") for f in sem_localidade]
    decisoes += [DecisaoProvisao(f, SEM_EMISSAO, "sem data de emissão legível: lance pela aba Energia")
                 for f in sem_emissao]
    return decisoes


def item_da_previa(d: DecisaoProvisao) -> dict[str, Any]:
    """Linha da prévia ({"data", "valor", "historico"}) para uma fatura a provisionar."""
    fat = d.fatura
    return {"data": fat.get("emissao", ""), "valor": -float(fat.get("valor") or 0.0),
            "historico": f"{_descricao(fat)} · venc. {fat.get('vencimento', '')} · {fat.get('localidade_nome', '')}"}


def linhas_do_painel(decisoes: list[DecisaoProvisao], situacoes: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    """Resumo e pendências da etapa de provisões, como (nível, texto) do painel.

    Args:
        decisoes: Saída de `decidir_provisoes`.
        situacoes: Resultado de cada fatura LANCAR, por número: (LANCADA|NAO_LANCADA|NAO_AUTORIZADA, motivo).
    """
    lancadas = [d for d in decisoes if d.acao == LANCAR and situacoes.get(d.fatura["numero_fatura"], ("",))[0] == LANCADA]
    existentes = [d for d in decisoes if d.acao in (JA_LANCADA, JA_LANCADA_MANUAL)]
    pendentes = [d for d in decisoes if d not in lancadas and d not in existentes]
    nivel = "alerta" if pendentes else "ok"
    linhas = [(nivel, f"⚡ Provisões de energia: {len(lancadas)} lançada(s), {len(existentes)} já estavam no SIGA, "
                      f"{len(pendentes)} pendente(s)")]
    for d in pendentes:
        motivo = situacoes.get(d.fatura.get("numero_fatura") or "", ("", d.motivo))[1] if d.acao == LANCAR else d.motivo
        linhas.append(("alerta", f"   ⚠ {_descricao(d.fatura)}: {motivo}"))
    for d in existentes:
        if "vezes no SIGA" in d.motivo:
            linhas.append(("alerta", f"   ⚠ {_descricao(d.fatura)}: {d.motivo}"))
    return linhas
