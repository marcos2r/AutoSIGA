"""
Baixa das compras do cartão pelo débito da fatura no extrato (Fase 4).

O extrato da conta traz um débito só ("DEB.CTA.FATURA", o total da fatura); no SIGA cada
compra é uma provisão na Contas a Pagar (docs/regras/siga.md: "uma baixa por compra",
histórico PGTO FAT. CARTÃO). Com o XLS da fatura (models/xls_fatura_cartao.py), o robô
sabe quais compras o débito pagou e procura a provisão de cada uma: mesmo valor, data
entre a compra e alguns dias depois do vencimento, preferindo o fornecedor de nome
parecido com o estabelecimento.

A baixa só sai se TODAS as compras acharem provisão sem dúvida: as parcelas vão juntas na
Baixa em Lote Agrupada, que gera um lançamento com o total e casa com o débito do extrato.
Qualquer falta ou empate vira pendência com a lista do que faltou. Decisão pura.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from controllers.baixa_contas_pagar import (
    BAIXAR,
    EMPATE,
    JA_BAIXADA,
    SEM_PROVISAO,
    DecisaoPagamento,
    PagamentoExtrato,
    ParcelaSiga,
    mesmo_fornecedor,
)
from controllers.baixa_energia import APROVADO, LANCADO, PAGO
from controllers.classificador_extrato import FATURA_CARTAO, classificar
from controllers.prova_real import moeda

CARTAO = "cartao"
TOLERANCIA = 0.01
DIAS_ANTES_DA_COMPRA = 5
DIAS_DEPOIS_DO_VENCIMENTO = 15
DIAS_DEBITO_VENCIMENTO = 5  # o débito sai no vencimento ou poucos dias depois (fim de semana)
# Desconto dado na hora da compra: o cartão cobra até 10% a menos que a nota provisionada
DESCONTO_MAXIMO = 0.10
# Fatura com compra paga com desconto: identificada, mas fica para a tesouraria até a baixa com
# desconto ser levantada na tela (TES01519 agrupada ou individual)
COM_DESCONTO = "com_desconto"


def _data(texto: str) -> datetime | None:
    try:
        return datetime.strptime(str(texto).strip(), "%d/%m/%Y")
    except ValueError:
        return None


def debitos_de_fatura(transacoes: list[dict[str, Any]]) -> list[PagamentoExtrato]:
    """Os débitos de fatura do cartão no extrato, como pagamentos (valor positivo)."""
    return [PagamentoExtrato(str(t.get("data", "")), round(-float(t.get("valor") or 0), 2), "FATURA DO CARTAO", "",
                             CARTAO)
            for t in transacoes
            if float(t.get("valor") or 0) < 0 and classificar(t).categoria == FATURA_CARTAO]


def fatura_do_debito(debito: PagamentoExtrato, faturas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A fatura cujo total é o débito e cujo vencimento está perto da data do débito."""
    dia = _data(debito.data)
    for f in faturas:
        venc = _data(f.get("vencimento", ""))
        if (abs(float(f.get("total") or 0) - debito.valor) <= TOLERANCIA and dia and venc
                and -1 <= (dia - venc).days <= DIAS_DEBITO_VENCIMENTO):
            return f
    return None


def decidir_fatura(debito: PagamentoExtrato, fatura: dict[str, Any] | None,
                   parcelas: list[ParcelaSiga], usadas: set[str] | None = None) -> DecisaoPagamento:
    """Decide a baixa de uma fatura inteira: todas as compras com provisão, ou pendência."""
    usadas = usadas if usadas is not None else set()
    if fatura is None:
        return DecisaoPagamento(debito, SEM_PROVISAO, f"débito de fatura de {moeda(debito.valor)} sem o XLS da "
                                                      "fatura no lote: inclua o extrato mensal do cartão")
    venc = _data(fatura["vencimento"])
    escolhidas: list[ParcelaSiga] = []
    faltam, empates = [], []
    descontos: list[tuple[dict[str, Any], ParcelaSiga]] = []
    for compra in fatura["compras"]:
        dia = _data(compra["data"])
        if dia is None or venc is None:
            faltam.append(compra)
            continue
        ini, fim = dia - timedelta(days=DIAS_ANTES_DA_COMPRA), venc + timedelta(days=DIAS_DEPOIS_DO_VENCIMENTO)
        candidatas = [p for p in parcelas
                      if p.guid not in usadas and p not in escolhidas and abs(p.valor - compra["valor"]) <= TOLERANCIA
                      and (pv := _data(p.vencimento)) is not None and ini <= pv <= fim]
        do_mesmo = [p for p in candidatas if mesmo_fornecedor(compra["descricao"], p.fornecedor)]
        lista = do_mesmo or candidatas
        if len(lista) == 1:
            escolhidas.append(lista[0])
        elif lista:
            empates.append(compra)
        elif (com_desconto := _com_desconto(compra, parcelas, usadas, escolhidas, ini, fim)) is not None:
            escolhidas.append(com_desconto)
            descontos.append((compra, com_desconto))
        else:
            faltam.append(compra)
    if faltam or empates:
        partes = []
        if faltam:
            partes.append("sem provisão: " + "; ".join(f"{c['data']} {c['descricao']} {moeda(c['valor'])}"
                                                       for c in faltam))
        if empates:
            partes.append("mais de uma provisão: " + "; ".join(f"{c['data']} {c['descricao']} {moeda(c['valor'])}"
                                                               for c in empates))
        acao = EMPATE if empates and not faltam else SEM_PROVISAO
        return DecisaoPagamento(debito, acao, f"fatura do cartão (vence {fatura['vencimento']}): " + " | ".join(partes))
    if descontos:
        detalhes = "; ".join(f"{c['descricao']}: provisão {p.numero} de {moeda(p.valor)}, pago {moeda(c['valor'])}, "
                             f"desconto {moeda(p.valor - c['valor'])}" for c, p in descontos)
        return DecisaoPagamento(debito, COM_DESCONTO, f"fatura do cartão (vence {fatura['vencimento']}) com desconto "
                                                      f"na compra: {detalhes}. Baixe à mão lançando o desconto",
                                tuple(escolhidas))
    status = {p.status for p in escolhidas}
    descricao = f"fatura do cartão (vence {fatura['vencimento']}): {len(escolhidas)} compra(s)"
    usadas.update(p.guid for p in escolhidas)
    if status == {PAGO}:
        return DecisaoPagamento(debito, JA_BAIXADA, f"{descricao} já pagas no SIGA", tuple(escolhidas))
    if status <= {LANCADO, APROVADO}:
        return DecisaoPagamento(debito, BAIXAR, descricao, tuple(escolhidas))
    return DecisaoPagamento(debito, EMPATE, f"{descricao} com situações misturadas no SIGA ({', '.join(sorted(status))})")


def _com_desconto(compra: dict[str, Any], parcelas: list[ParcelaSiga], usadas: set[str],
                  escolhidas: list[ParcelaSiga], ini: datetime, fim: datetime) -> ParcelaSiga | None:
    """A provisão que a compra pagou com desconto: mesmo fornecedor pelo nome, valor até 10% maior, única."""
    candidatas = [p for p in parcelas
                  if p.guid not in usadas and p not in escolhidas
                  and compra["valor"] < p.valor <= compra["valor"] / (1 - DESCONTO_MAXIMO) + TOLERANCIA
                  and (pv := _data(p.vencimento)) is not None and ini <= pv <= fim
                  and mesmo_fornecedor(compra["descricao"], p.fornecedor)]
    return candidatas[0] if len(candidatas) == 1 else None
