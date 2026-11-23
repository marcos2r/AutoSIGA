"""
Avisos da conciliação que não são erro, mas costumam explicar diferença no fechamento.

A IT.TES.06 aponta como causas comuns a falta de rendimento, de tarifa, de aplicação e de
resgate. Aqui se olha o extrato e o que ficou sem lançamento no SIGA e se devolvem frases
curtas para o painel final. Só lê; nada aqui lança.
"""

from __future__ import annotations

from typing import Any

from controllers.classificador_extrato import RENDIMENTO, TARIFA, classificar
from controllers.prova_real import MovimentoBanco, moeda


def avisos_do_extrato(dados: dict[str, Any], faltas: list[MovimentoBanco] | None) -> list[str]:
    """Avisos de um extrato do lote.

    Args:
        dados: O extrato como os leitores devolvem (`tipo_extrato`, `saldo_atual`, `transacoes`).
        faltas: Movimentos do banco sem lançamento no SIGA (None quando a prova real não os apontou).

    Returns:
        list[str]: Frases para o painel, vazia quando não há o que avisar.
    """
    avisos = []
    transacoes = dados.get("transacoes") or []
    saldo = dados.get("saldo_atual") or 0.0
    tem_rendimento = any(classificar(t).categoria == RENDIMENTO for t in transacoes)
    if dados.get("tipo_extrato") == "APLICACAO" and saldo > 0 and not tem_rendimento:
        avisos.append("Aplicação com saldo e sem rendimento no extrato: se o banco só informa no fim "
                      "do mês, lance o rendimento no último dia da competência (IT.TES.11).")
    tarifas = [f for f in faltas or [] if classificar({"descricao": f.descricao, "valor": f.valor}).categoria == TARIFA]
    if tarifas:
        total = -sum(f.valor for f in tarifas)
        avisos.append(f"{len(tarifas)} tarifa(s) do banco sem lançamento no SIGA ({moeda(total)}): lance como "
                      "despesa em Caixas e Bancos (IT.TES.05).")
    return avisos
