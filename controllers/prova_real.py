"""
Prova real da conciliação: confere o saldo do SIGA com o do banco e aponta os
lançamentos do SIGA que não têm par no extrato.

Só lê e informa. Nada aqui lança, apaga ou corrige no SIGA: a diferença é mostrada
ao usuário, que decide o que fazer.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from controllers.baixa_energia import ResultadoBaixa

CONFERE = "confere"
DIVERGE = "diverge"
NAO_CONFERIDO = "nao_conferido"

# Situação do extrato no fim do lote
CONCILIADO = "conciliado"
PENDENTE = "pendente"
CONTA_NAO_ENCONTRADA = "conta_nao_encontrada"
MES_FECHADO = "mes_fechado"
RECUSADO = "recusado"

TOLERANCIA = 0.01
# Lançamento manual com a data do dia útil seguinte ou anterior (fim de semana, feriado)
DIAS_TOLERANCIA = 3

# Sinal de cada movimento do XLS de aplicação na conta 103 do SIGA
_SINAL_MOVIMENTO = {"APLICACAO": 1, "RESGATE": -1, "RENDIMENTO": 1}
_VAZIOS = ("", "-", "0,00", "0.00")


@dataclass
class MovimentoSiga:
    """Uma linha de movimento da grade da TES01701, com o valor já com sinal."""

    data: str
    valor: float
    historico: str = ""


@dataclass
class ResultadoSaldo:
    """Comparação do saldo final do banco com o do SIGA.

    Attributes:
        status: CONFERE, DIVERGE ou NAO_CONFERIDO.
        saldo_banco: Saldo final do extrato, ou None.
        saldo_siga: Saldo final da grade do SIGA, ou None.
        diferenca: SIGA menos banco (0.0 quando não conferido).
        motivo: Por que não foi conferido (vazio nos outros casos).
    """

    status: str
    saldo_banco: float | None = None
    saldo_siga: float | None = None
    diferenca: float = 0.0
    motivo: str = ""


@dataclass
class ResultadoExtrato:
    """O que aconteceu com um extrato do lote, para o painel e o relatório."""

    conta_id: str
    conta_siga: str
    localidade: str
    tipo: str
    situacao: str
    lancados: int = 0
    pendentes: int = 0
    saldo: ResultadoSaldo = field(default_factory=lambda: ResultadoSaldo(NAO_CONFERIDO))
    sobras: list[MovimentoSiga] | None = None
    baixas: list["ResultadoBaixa"] | None = None


def valor_br(texto: Any) -> float | None:
    """Converte "10.977,40" ou "-27,50" em float; "-" sozinho é zero.

    Returns:
        O valor, ou None se o texto não for um número.
    """
    limpo = str(texto if texto is not None else "").strip()
    if limpo in ("", "-"):
        return 0.0
    try:
        return float(limpo.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def normalizar_linhas_siga(linhas: list[dict[str, Any]] | None) -> list[MovimentoSiga]:
    """Linhas da grade (texto) em movimentos com sinal: entrada positiva, saída negativa.

    Linhas sem valor em Entrada nem em Saída (ex.: "Saldo Anterior") ficam de fora.
    """
    movimentos = []
    for linha in linhas or []:
        entrada = str(linha.get("entrada", "")).strip()
        saida = str(linha.get("saida", "")).strip()
        texto, sinal = (entrada, 1) if entrada not in _VAZIOS else (saida, -1)
        if texto in _VAZIOS:
            continue
        valor = valor_br(texto)
        if valor is None:
            logging.error(f"Erro ao converter valor numérico do SIGA: {texto}")
            continue
        # abs() evita sinal duplo caso o SIGA já traga o "-" na coluna Saída
        movimentos.append(MovimentoSiga(str(linha.get("data", "")).strip(), sinal * abs(valor),
                                        str(linha.get("historico", "")).strip()))
    return movimentos


def conferir_saldo(saldo_banco: float | None, saldo_siga: float | None,
                   tolerancia: float = TOLERANCIA) -> ResultadoSaldo:
    """Compara os saldos finais do banco e do SIGA, com tolerância de 1 centavo."""
    if saldo_banco is None:
        return ResultadoSaldo(NAO_CONFERIDO, None, saldo_siga, motivo="o extrato não traz o saldo")
    if saldo_siga is None:
        return ResultadoSaldo(NAO_CONFERIDO, saldo_banco, None, motivo="saldo do SIGA ilegível")
    diferenca = round(saldo_siga - saldo_banco, 2)
    status = CONFERE if abs(diferenca) <= tolerancia else DIVERGE
    return ResultadoSaldo(status, saldo_banco, saldo_siga, diferenca if status == DIVERGE else 0.0)


def nao_conferido(motivo: str, saldo_banco: float | None = None) -> ResultadoSaldo:
    """Saldo deixado sem conferência, com o motivo para o usuário."""
    return ResultadoSaldo(NAO_CONFERIDO, saldo_banco, motivo=motivo)


def movimentos_do_banco(dados: dict[str, Any]) -> list[tuple[str, float]] | None:
    """Movimentos do extrato como (data, valor com sinal), na visão da conta do SIGA.

    OFX: todas as transações. XLS de aplicação: aplicações, resgates e rendimentos
    (`movimentos`), porque `transacoes` só tem os rendimentos.

    Returns:
        A lista, ou None se o extrato não tiver os movimentos completos.
    """
    if dados.get("tipo_extrato") == "APLICACAO":
        movimentos = dados.get("movimentos")
        if movimentos is None:
            return None
        return [(m["data"], _SINAL_MOVIMENTO.get(m.get("tipo", ""), 1) * abs(m["valor"])) for m in movimentos]
    return [(t.get("data", ""), t.get("valor", 0.0)) for t in dados.get("transacoes", [])]


def sobras_no_siga(movimentos_banco: list[tuple[str, float]],
                   linhas_siga: list[dict[str, Any]] | None) -> list[MovimentoSiga]:
    """Lançamentos do SIGA sem par no extrato (duplicado, valor errado, estorno esquecido).

    O pareamento é um para um, por valor: primeiro na mesma data e, numa segunda
    passada, com até `DIAS_TOLERANCIA` dias de diferença (lançamento manual com a data do
    dia útil seguinte ou anterior). Dois lançamentos iguais no SIGA para um só no banco
    deixam uma sobra.
    """
    livres = list(movimentos_banco)
    pendentes = []
    for mov in normalizar_linhas_siga(linhas_siga):
        par = next((i for i, (data, valor) in enumerate(livres)
                    if data == mov.data and abs(valor - mov.valor) <= TOLERANCIA), None)
        if par is None:
            pendentes.append(mov)
        else:
            livres.pop(par)

    sobras = []
    for mov in pendentes:
        dia = _data(mov.data)
        perto = [(abs((d - dia).days), i) for i, (data, valor) in enumerate(livres)
                 if dia and (d := _data(data)) and abs((d - dia).days) <= DIAS_TOLERANCIA
                 and abs(valor - mov.valor) <= TOLERANCIA]
        if perto:
            livres.pop(min(perto)[1])
        else:
            sobras.append(mov)
    return sobras


def _data(texto: str) -> datetime | None:
    try:
        return datetime.strptime(str(texto).strip(), "%d/%m/%Y")
    except ValueError:
        return None


def moeda(valor: float | None) -> str:
    """Valor no formato do SIGA ("R$ 1.234,56"); "—" quando ausente."""
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def resumo_resultado(r: ResultadoExtrato) -> tuple[str, str]:
    """Nível ("ok", "alerta" ou "neutro") e a frase do resultado, com ícone e texto.

    O nível só escolhe a cor; a frase sozinha já diz o estado.
    """
    if r.situacao == CONTA_NAO_ENCONTRADA:
        return "alerta", "⛔ Conta não encontrada no SIGA: nada lançado"
    if r.situacao == MES_FECHADO:
        return "neutro", f"— Mês fechado no SIGA: {r.pendentes} item(ns) pendente(s)"
    if r.situacao == RECUSADO:
        return "neutro", f"— Lançamento não autorizado por você: {r.pendentes} item(ns) pendente(s)"
    pendentes = f" · {r.pendentes} item(ns) pendente(s)" if r.pendentes else ""
    if r.saldo.status == CONFERE:
        return ("alerta" if r.pendentes else "ok"), f"✔ Saldo confere ({moeda(r.saldo.saldo_siga)}){pendentes}"
    if r.saldo.status == DIVERGE:
        sobras = f" · {len(r.sobras)} no SIGA sem par no banco" if r.sobras else ""
        return "alerta", (f"⚠ Diferença de {moeda(r.saldo.diferenca)} (SIGA {moeda(r.saldo.saldo_siga)} × "
                          f"banco {moeda(r.saldo.saldo_banco)}){sobras}{pendentes}")
    return ("alerta" if r.pendentes else "neutro"), f"— Não conferido: {r.saldo.motivo}{pendentes}"
