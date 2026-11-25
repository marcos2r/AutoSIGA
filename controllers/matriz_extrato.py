"""
Matriz do extrato no SIGA mantida em memória durante a conciliação de um extrato.

A grade da TES01701 é lida uma vez no começo do extrato. Cada gravação que o robô faz
(aplicação, resgate, recebimento, transferência, tarifa) entra nela como uma linha
projetada, no mesmo formato da grade, e as etapas seguintes decidem por essa matriz em vez
de reconsultar o SIGA. No fim do extrato o robô relê o SIGA uma vez e a leitura real
substitui a matriz: é ela que faz a prova real.

Só faz sentido porque duas pessoas raramente rodam o robô na mesma conta ao mesmo tempo;
a releitura final é a garantia. Nada aqui grava no SIGA.
"""

from collections.abc import Iterable
from typing import Any

# Marca as linhas que o robô acrescentou sem ler do SIGA (nunca vão para o relatório)
ORIGEM_PROJETADA = "AutoSIGA (gravado nesta execução)"


def formatar_valor(valor: float) -> str:
    """Valor sem sinal no formato da grade ("1.234,56")."""
    return f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def linha_projetada(data: str, valor: float, historico: str = "") -> dict[str, str]:
    """Linha da grade da TES01701 para um lançamento que o robô acabou de gravar.

    Args:
        data: Data do lançamento ("dd/mm/aaaa").
        valor: Valor com sinal na visão da conta (entrada positiva, saída negativa).
        historico: Texto para o log; a conciliação não depende dele.

    Returns:
        dict: Linha com as mesmas chaves que `_JS_LER_GRADE` devolve.
    """
    texto = formatar_valor(valor)
    return {"data": data, "lote": "", "documento": "", "historico": historico, "origem": ORIGEM_PROJETADA,
            "entrada": texto if valor > 0 else "", "saida": texto if valor < 0 else "", "saldo": ""}


def projetar(grade: list[dict[str, Any]] | None,
             gravados: Iterable[tuple[str, float, str]]) -> list[dict[str, Any]]:
    """A matriz com as gravações novas no fim, sem alterar a lista original.

    Args:
        grade: Matriz atual (a leitura do SIGA, talvez já com linhas projetadas).
        gravados: (data, valor com sinal, histórico) de cada gravação confirmada pelo SIGA.

    Returns:
        list: Nova matriz.
    """
    return list(grade or []) + [linha_projetada(d, v, h) for d, v, h in gravados]


def tem_projecao(grade: list[dict[str, Any]] | None) -> bool:
    """True se a matriz tem alguma linha que não veio de uma leitura do SIGA."""
    return any(linha.get("origem") == ORIGEM_PROJETADA for linha in grade or [])
