"""
De onde vem a diferença da prova real de um extrato, para o painel e o Excel.

A diferença (SIGA menos banco) é a soma do que não tem par: cada lançamento do SIGA sem
par no banco conta com o próprio valor, e cada movimento do banco sem lançamento no SIGA
conta com o valor trocado de sinal. O que sobra depois disso não está nos movimentos do
período (saldo inicial diferente, lançamento fora do período) e aparece como "sem
explicação". Só lê e explica; nada aqui decide lançar.
"""

import re
from dataclasses import dataclass

from controllers.baixa_energia import linhas_do_painel
from controllers.prova_real import DIVERGE, TOLERANCIA, MovimentoBanco, MovimentoSiga, ResultadoExtrato, moeda

_RE_ENERGIA = re.compile(r"DEBITO\s+CONVENIOS-ENERGI", re.IGNORECASE)
_TIPOS = {"CORRENTE": "Conta corrente", "APLICACAO": "Aplicação"}
_RECUO = "   "

ORIGEM_SOBRA = "No SIGA sem par no banco"
ORIGEM_ENERGIA = "Débito de energia sem baixa no SIGA"
ORIGEM_FALTA = "No banco sem lançamento no SIGA"
ORIGEM_RESTO = "Sem explicação nos movimentos do período"


@dataclass(frozen=True)
class Composicao:
    """A diferença de um extrato separada pela origem.

    Attributes:
        sobras: Lançamentos do SIGA sem par no banco.
        energia: Débitos de energia do banco sem a saída no SIGA (fatura não baixada).
        outros: Os demais movimentos do banco sem lançamento no SIGA.
        sem_explicacao: Parte da diferença que os movimentos do período não explicam.
    """

    sobras: list[MovimentoSiga]
    energia: list[MovimentoBanco]
    outros: list[MovimentoBanco]
    sem_explicacao: float


def compor_diferenca(diferenca: float, sobras: list[MovimentoSiga], faltas: list[MovimentoBanco]) -> Composicao:
    """Separa a diferença em sobras do SIGA, débitos de energia, outras faltas e o resto."""
    energia = [f for f in faltas if _RE_ENERGIA.search(f.descricao)]
    outros = [f for f in faltas if not _RE_ENERGIA.search(f.descricao)]
    explicado = sum(s.valor for s in sobras) - sum(f.valor for f in faltas)
    resto = round(diferenca - explicado, 2)
    return Composicao(sobras, energia, outros, resto if abs(resto) > TOLERANCIA else 0.0)


def tipo_legivel(tipo: str) -> str:
    """"CORRENTE" → "Conta corrente"; tipo desconhecido fica como veio."""
    return _TIPOS.get(tipo, tipo)


def cabecalho_extrato(r: ResultadoExtrato) -> str:
    """Conta, localidade, tipo e período do extrato, na ordem em que o usuário procura."""
    partes = [r.conta_siga or r.conta_id, r.localidade, tipo_legivel(r.tipo), r.periodo]
    return " · ".join(p for p in partes if p)


def itens_da_diferenca(r: ResultadoExtrato) -> list[tuple[str, str, float | None, str, float]]:
    """Cada item sem par do extrato, para o Excel: (data, descrição, valor, origem, efeito na diferença).

    Com o saldo divergente, entra a composição inteira (com o resto sem explicação); nos
    outros casos, só os lançamentos do SIGA sem par, que merecem conferência mesmo assim.
    """
    if r.saldo.status != DIVERGE or r.sobras is None or r.faltas is None:
        return [(s.data, s.historico, s.valor, ORIGEM_SOBRA, s.valor) for s in r.sobras or []]
    c = compor_diferenca(r.saldo.diferenca, r.sobras, r.faltas)
    itens: list[tuple[str, str, float | None, str, float]] = [
        (s.data, s.historico, s.valor, ORIGEM_SOBRA, s.valor) for s in c.sobras]
    itens += [(f.data, f.descricao, f.valor, ORIGEM_ENERGIA, -f.valor) for f in c.energia]
    itens += [(f.data, f.descricao, f.valor, ORIGEM_FALTA, -f.valor) for f in c.outros]
    if c.sem_explicacao:
        itens.append(("", "", None, ORIGEM_RESTO, c.sem_explicacao))
    return itens


def linhas_do_extrato(r: ResultadoExtrato) -> list[tuple[str, str]]:
    """Linhas de detalhe de um extrato no painel: a composição da diferença e as baixas de energia.

    Returns:
        list[tuple[str, str]]: (nível, texto); o nível só escolhe a cor.
    """
    baixas = linhas_do_painel(r.baixas)
    if r.saldo.status != DIVERGE or r.sobras is None or r.faltas is None:
        return baixas
    c = compor_diferenca(r.saldo.diferenca, r.sobras, r.faltas)
    linhas = [("neutro", f"{_RECUO}De onde vem a diferença de {moeda(r.saldo.diferenca)}:")]
    if c.sobras:
        linhas.append(("alerta", f"{_RECUO}• {_efeito(sum(s.valor for s in c.sobras))}: "
                                 f"{len(c.sobras)} lançamento(s) no SIGA sem par no banco"))
        linhas += [("alerta", f"{_RECUO * 2}{s.data} · {s.historico or 'sem histórico'} · {moeda(s.valor)}")
                   for s in c.sobras]
    if c.energia:
        # Cada débito já aparece nas baixas logo abaixo, com o motivo; aqui só o total
        detalhe = " (detalhe nas baixas abaixo)" if r.baixas else ""
        linhas.append(("alerta", f"{_RECUO}• {_efeito(-sum(f.valor for f in c.energia))}: "
                                 f"{len(c.energia)} débito(s) de energia sem baixa no SIGA{detalhe}"))
        if not r.baixas:
            linhas += [("alerta", f"{_RECUO * 2}{f.data} · {_curta(f.descricao)} · {moeda(f.valor)}")
                       for f in c.energia]
    if c.outros:
        linhas.append(("alerta", f"{_RECUO}• {_efeito(-sum(f.valor for f in c.outros))}: "
                                 f"{len(c.outros)} movimento(s) do banco sem lançamento no SIGA"))
        linhas += [("alerta", f"{_RECUO * 2}{f.data} · {_curta(f.descricao)} · {moeda(f.valor)}")
                   for f in c.outros]
    if c.sem_explicacao:
        linhas.append(("alerta", f"{_RECUO}• {_efeito(c.sem_explicacao)}: sem explicação nos movimentos do "
                                 "período (confira o saldo inicial e lançamentos fora do período)"))
    return linhas + baixas


def _efeito(valor: float) -> str:
    """Quanto o item soma à diferença, com sinal explícito."""
    return f"{'+' if valor >= 0 else '−'}{moeda(abs(valor))}"


def _curta(descricao: str, limite: int = 60) -> str:
    texto = " ".join((descricao or "sem descrição").split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"
