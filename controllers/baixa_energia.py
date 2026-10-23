"""
Baixa das faturas de energia pelo extrato: qual provisão da Contas a Pagar cada débito quita.

O débito do banco traz o código de débito automático da UC; o índice de PDFs liga o
código às faturas, e o número da fatura é o "Nº Doc." da provisão no SIGA. Só se baixa
quando código, valor e número apontam para uma única provisão em aberto. Em qualquer
dúvida, a decisão é uma pendência explicada, nunca uma baixa: em lançamento financeiro,
abster-se é melhor que errar.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from controllers.prova_real import moeda
from models.indice_faturas_energia import FaturaEnergia

BAIXAR = "baixar"
JA_BAIXADA = "ja_baixada"
SEM_FATURA = "sem_fatura"
VALOR_DIFERENTE = "valor_diferente"
EMPATE = "empate"
SEM_PROVISAO = "sem_provisao"
ESTORNADO = "estornado"

LANCADO = "Lançado"
APROVADO = "Aprovado"
PAGO = "Pago"

TOLERANCIA = 0.01
# A fatura vence antes do débito (atraso do banco) ou, no máximo, poucos dias depois
_DIAS_ANTES_DO_DEBITO = 40
_DIAS_DEPOIS_DO_DEBITO = 5

_RE_DEBITO_ENERGIA = re.compile(r"DEBITO\s+CONVENIOS-ENERGI.*?\bID\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class DebitoEnergia:
    """Débito de energia no extrato (valor positivo)."""

    data: str
    valor: float
    codigo: str


@dataclass(frozen=True)
class ProvisaoSiga:
    """Linha da Contas a Pagar (TES01501) de uma fatura de energia.

    Attributes:
        numero: Nº Doc. (o número da fatura).
        valor: Valor da parcela.
        status: "Lançado", "Aprovado" ou "Pago".
        guid: Código da parcela nos links Aprovar/Baixar (`?codigo=<GUID>`).
        vencimento: Dt. Vcto.
    """

    numero: str
    valor: float
    status: str
    guid: str = ""
    vencimento: str = ""


@dataclass(frozen=True)
class Decisao:
    """O que fazer com um débito de energia, com o motivo para o usuário."""

    debito: DebitoEnergia
    acao: str
    motivo: str = ""
    fatura: FaturaEnergia | None = None
    provisao: ProvisaoSiga | None = None

    @property
    def precisa_aprovar(self) -> bool:
        return self.acao == BAIXAR and self.provisao is not None and self.provisao.status == LANCADO


def _data(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y")
    except (ValueError, AttributeError):
        return None


def _mesmo_numero(a: str, b: str) -> bool:
    """O SIGA às vezes guarda o número da fatura sem os zeros à esquerda."""
    return a.strip().lstrip("0") == b.strip().lstrip("0") != ""


def ler_debitos(transacoes: list[dict[str, Any]]) -> tuple[list[DebitoEnergia], list[Decisao]]:
    """Separa os débitos de energia do extrato e anula os que foram estornados.

    Args:
        transacoes: Transações do OFX ({"data", "valor", "descricao"}).

    Returns:
        tuple: (débitos a casar, decisões ESTORNADO dos débitos anulados por um crédito).
    """
    debitos: list[DebitoEnergia] = []
    estornos: list[DebitoEnergia] = []
    for tx in transacoes:
        m = _RE_DEBITO_ENERGIA.search(str(tx.get("descricao", "")))
        if not m:
            continue
        valor = float(tx.get("valor", 0.0))
        item = DebitoEnergia(str(tx.get("data", "")), round(abs(valor), 2), m.group(1))
        (debitos if valor < 0 else estornos).append(item)

    anulados = []
    for estorno in estornos:
        par = next((d for d in debitos if d.codigo == estorno.codigo and abs(d.valor - estorno.valor) <= TOLERANCIA), None)
        if par:
            debitos.remove(par)
            anulados.append(Decisao(par, ESTORNADO, f"débito de {moeda(par.valor)} estornado pelo banco em {estorno.data}"))
    return debitos, anulados


def _decidir(debito: DebitoEnergia, indice: dict[str, list[FaturaEnergia]], provisoes: list[ProvisaoSiga],
             usadas: set[str]) -> Decisao:
    faturas = indice.get(debito.codigo, [])
    if not faturas:
        return Decisao(debito, SEM_FATURA, f"código {debito.codigo} sem fatura conhecida "
                                           "(PDF não importado ou fatura lançada à mão)")

    dia = _data(debito.data)
    na_janela = [f for f in faturas if dia and (v := _data(f.vencimento))
                 and dia - timedelta(days=_DIAS_ANTES_DO_DEBITO) <= v <= dia + timedelta(days=_DIAS_DEPOIS_DO_DEBITO)]
    mesmo_valor = [f for f in na_janela if abs(f.valor - debito.valor) <= TOLERANCIA]
    if not mesmo_valor:
        if na_janela:
            f = na_janela[0]
            return Decisao(debito, VALOR_DIFERENTE, f"fatura {f.numero} é de {moeda(f.valor)} e o débito de "
                                                    f"{moeda(debito.valor)}: possível multa ou juros", fatura=f)
        return Decisao(debito, SEM_FATURA, f"nenhuma fatura da UC {faturas[0].uc} vence perto de {debito.data}")
    if len(mesmo_valor) > 1:
        return Decisao(debito, EMPATE, f"{len(mesmo_valor)} faturas da UC {mesmo_valor[0].uc} com o mesmo valor")

    fatura = mesmo_valor[0]
    da_fatura = [p for p in provisoes if _mesmo_numero(p.numero, fatura.numero)]
    if not da_fatura:
        return Decisao(debito, SEM_PROVISAO, f"fatura {fatura.numero} não está lançada na Contas a Pagar", fatura=fatura)

    abertas = [p for p in da_fatura if p.status in (LANCADO, APROVADO) and abs(p.valor - debito.valor) <= TOLERANCIA
               and p.guid not in usadas]
    if len(abertas) == 1:
        usadas.add(abertas[0].guid)
        return Decisao(debito, BAIXAR, f"fatura {fatura.numero} da UC {fatura.uc}", fatura, abertas[0])
    if len(abertas) > 1:
        return Decisao(debito, EMPATE, f"fatura {fatura.numero} aparece {len(abertas)} vezes em aberto no SIGA",
                       fatura=fatura)
    paga = next((p for p in da_fatura if p.status == PAGO), None)
    if paga:
        return Decisao(debito, JA_BAIXADA, f"fatura {fatura.numero} já está paga no SIGA", fatura, paga)
    return Decisao(debito, VALOR_DIFERENTE, f"a provisão da fatura {fatura.numero} no SIGA tem outro valor",
                   fatura=fatura)


def decidir_baixas(transacoes: list[dict[str, Any]], indice: dict[str, list[FaturaEnergia]],
                   provisoes: list[ProvisaoSiga]) -> list[Decisao]:
    """Decide, para cada débito de energia do extrato, se e qual provisão baixar.

    Args:
        transacoes: Transações do extrato de conta corrente.
        indice: Faturas por código de débito (`montar_indice`).
        provisoes: Provisões da Energisa lidas da TES01501.

    Returns:
        list[Decisao]: Uma por débito, na ordem do extrato; cada provisão é usada uma vez só.
    """
    debitos, decisoes = ler_debitos(transacoes)
    usadas: set[str] = set()
    return decisoes + [_decidir(d, indice, provisoes, usadas) for d in debitos]


def resumo_decisao(d: Decisao) -> tuple[str, str]:
    """Nível ("ok", "alerta" ou "neutro") e a frase da decisão, para a prévia e o painel."""
    base = f"{d.debito.data} · {moeda(d.debito.valor)} · "
    if d.acao == BAIXAR:
        passo = "aprovar e baixar" if d.precisa_aprovar else "baixar"
        return "ok", f"⚡ {base}{passo} {d.motivo}"
    if d.acao == JA_BAIXADA:
        return "neutro", f"✔ {base}{d.motivo}"
    return "alerta", f"⚠ {base}não baixada: {d.motivo}"
