"""
Baixa das outras provisões da Contas a Pagar pelo extrato: boletos e PIX a fornecedores.

Diferente da energia, o extrato não traz um código que aponte a provisão: só o valor, a
data e o nome do beneficiário (a grade da TES01501 não mostra CNPJ). Por isso a decisão
exige as três coisas juntas e olha também as provisões já pagas: o vencimento mais perto
do pagamento decide, e se ele já está Pago o pagamento é dado como baixado. Sem isso, a
parcela do mês seguinte, de mesmo valor e fornecedor, seria baixada no lugar da certa.

Um pagamento também pode quitar várias provisões do mesmo fornecedor e vencimento (vai
para a baixa em lote agrupada). Qualquer dúvida vira pendência explicada, nunca baixa.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from controllers.baixa_energia import APROVADO, LANCADO, PAGO, guid_valido
from controllers.prova_real import moeda, valor_br

BAIXAR = "baixar"
JA_BAIXADA = "ja_baixada"
SEM_PROVISAO = "sem_provisao"
EMPATE = "empate"
VALOR_DIFERENTE = "valor_diferente"
INTERMEDIARIO = "intermediario"

# Resultado da execução de uma decisão BAIXAR no SIGA (as outras guardam a própria ação)
BAIXADA = "baixada"
APROVADA_SEM_BAIXA = "aprovada_sem_baixa"
FALHOU = "falhou"
NAO_AUTORIZADA = "nao_autorizada"

BOLETO = "boleto"
PIX = "pix"

TOLERANCIA = 0.01
# Vencimento a até 10 dias do pagamento; dois candidatos a menos de 3 dias um do outro empatam
JANELA_DIAS = 10
FOLGA_DIAS = 3
# Pago depois do vencimento com até 5% a mais: provável juros, que fica para a pessoa decidir
JUROS_MAXIMO = 0.05

_RE_PAGAMENTO = re.compile(r"^(LIQUIDACAO BOLETO|PAGAMENTO PIX)\S*.*?\b(\d{14}|\d{11})\s+(.+)$", re.IGNORECASE)
# Quem recebe o boleto no lugar do fornecedor: o nome do banco não serve para achar a provisão
_RE_INTERMEDIARIO = re.compile(r"SUPPLIER|FUNDO DE INVESTIMENTO|\bFIDC\b|DIREITOS CR", re.IGNORECASE)
# Palavras que não identificam o fornecedor (natureza jurídica, ramo, ligação)
_PALAVRAS_VAZIAS = set(
    "LTDA EPP EIRELI CIA DOS DAS COMERCIO COML COMERCIAL IND INDUSTRIA MATERIAIS EQUIPAMENTOS "
    "SERVICOS DISTRIBUIDORA BRASIL MATRIZ".split())


@dataclass(frozen=True)
class PagamentoExtrato:
    """Boleto ou PIX pago no extrato (valor positivo)."""

    data: str
    valor: float
    nome: str
    documento: str
    tipo: str


@dataclass(frozen=True)
class ParcelaSiga:
    """Linha da Contas a Pagar (TES01501) de qualquer fornecedor, menos a Energisa.

    Tem os mesmos campos que o bot confere na tela (`numero`, `valor`, `guid`) da
    `ProvisaoSiga` da energia, para usar as mesmas rotinas de aprovação e conferência.
    """

    numero: str
    fornecedor: str
    valor: float
    status: str
    guid: str
    vencimento: str
    pago: float = 0.0


@dataclass(frozen=True)
class DecisaoPagamento:
    """O que fazer com um pagamento do extrato, com o motivo para o usuário."""

    pagamento: PagamentoExtrato
    acao: str
    motivo: str = ""
    parcelas: tuple[ParcelaSiga, ...] = ()

    @property
    def a_aprovar(self) -> list[ParcelaSiga]:
        """Parcelas Lançado: a baixa em lote do SIGA só aceita Aprovado."""
        return [p for p in self.parcelas if p.status == LANCADO] if self.acao == BAIXAR else []


@dataclass(frozen=True)
class ResultadoPagamento:
    """O que aconteceu com um pagamento; `situacao` é BAIXADA, FALHOU... ou a ação da decisão."""

    decisao: DecisaoPagamento
    situacao: str
    detalhe: str = ""


def ler_pagamentos(transacoes: list[dict[str, Any]]) -> list[PagamentoExtrato]:
    """Boletos (LIQUIDACAO BOLETO) e PIX (PAGAMENTO PIX) do extrato que trazem CNPJ/CPF e nome."""
    pagamentos = []
    for t in transacoes:
        valor = t.get("valor") or 0
        casa = _RE_PAGAMENTO.match(" ".join(str(t.get("descricao", "")).split()))
        if valor >= 0 or not casa:
            continue
        tipo = BOLETO if casa.group(1).upper().startswith("LIQUIDACAO") else PIX
        pagamentos.append(PagamentoExtrato(str(t.get("data", "")), round(-float(valor), 2),
                                           casa.group(3).strip(), casa.group(2), tipo))
    return pagamentos


def parcelas_da_grade(linhas: list[dict[str, Any]] | None) -> list[ParcelaSiga]:
    """Parcelas da grade da TES01501, sem a Energisa (baixada pelo fluxo da energia)."""
    parcelas = []
    for linha in linhas or []:
        fornecedor = str(linha.get("fornecedor", "")).strip()
        valor = valor_br(linha.get("valor"))
        guid = str(linha.get("guid", "")).strip()
        if "ENERGISA" in fornecedor.upper() or valor is None or valor <= 0 or not guid_valido(guid):
            continue
        parcelas.append(ParcelaSiga(str(linha.get("numero", "")).strip(), fornecedor, valor,
                                    str(linha.get("status", "")).strip(), guid,
                                    str(linha.get("vencimento", "")).strip(), valor_br(linha.get("pago")) or 0.0))
    return parcelas


def periodo_de_vencimento(data_inicial: str, data_final: str) -> tuple[str, str] | None:
    """Vencimentos a ler na TES01501 para um extrato: a janela de `decidir_pagamentos`."""
    ini, fim = _data(data_inicial), _data(data_final)
    if not ini or not fim:
        return None
    return ((ini - timedelta(days=JANELA_DIAS)).strftime("%d/%m/%Y"),
            (fim + timedelta(days=JANELA_DIAS)).strftime("%d/%m/%Y"))


def mesmo_fornecedor(nome_banco: str, fornecedor_siga: str) -> bool:
    """O nome do beneficiário no banco é o do fornecedor no SIGA?

    Compara palavras: a primeira de cada lado tem de bater e, quando os dois têm duas ou
    mais, pelo menos duas. Abreviação conta ("DOUR" = "DOURADOS", "COML" é ignorada).
    """
    a, b = _palavras(nome_banco), _palavras(fornecedor_siga)
    if not a or not b or not _parecidas(a[0], b[0]):
        return False
    comuns = sum(1 for p in a if any(_parecidas(p, q) for q in b))
    return comuns >= min(2, len(a), len(b))


def decidir_pagamentos(pagamentos: list[PagamentoExtrato], parcelas: list[ParcelaSiga]) -> list[DecisaoPagamento]:
    """Decide cada pagamento do extrato; cada parcela é usada por um pagamento só.

    Primeiro casam os pagamentos de uma parcela só e depois as somas, para um PIX avulso
    não ser engolido pelo lote do mesmo fornecedor e vencimento.
    """
    usadas: set[str] = set()
    decisoes: dict[int, DecisaoPagamento] = {}
    ordem = sorted(range(len(pagamentos)), key=lambda i: _data(pagamentos[i].data) or datetime.min)
    for i in ordem:
        decisao = _decidir_um(pagamentos[i], parcelas, usadas)
        if decisao:
            decisoes[i] = decisao
    for i in ordem:
        if i not in decisoes:
            decisoes[i] = _decidir_soma(pagamentos[i], parcelas, usadas)
    return [decisoes[i] for i in range(len(pagamentos))]


def _decidir_um(pg: PagamentoExtrato, parcelas: list[ParcelaSiga], usadas: set[str]) -> DecisaoPagamento | None:
    """Pagamento de uma parcela só, ou None para tentar a soma depois."""
    if _RE_INTERMEDIARIO.search(pg.nome):
        provavel = [p for p in _na_janela(pg, parcelas, usadas) if abs(p.valor - pg.valor) <= TOLERANCIA]
        sugestao = f"; provável: {_descricao(provavel[0])}" if len(provavel) == 1 else ""
        return DecisaoPagamento(pg, INTERMEDIARIO, f"pago a {pg.nome}, que não é o fornecedor{sugestao}")
    candidatas = sorted((p for p in _do_fornecedor(pg, parcelas, usadas) if _quita(pg, p)),
                        key=lambda p: _distancia(pg, p))
    if not candidatas:
        return None
    if len(candidatas) > 1 and _distancia(pg, candidatas[1]) - _distancia(pg, candidatas[0]) < FOLGA_DIAS:
        lista = " e ".join(_descricao(p) for p in candidatas[:2])
        return DecisaoPagamento(pg, EMPATE, f"duas provisões de {moeda(pg.valor)} com vencimento próximo: {lista}")
    return _decisao_das(pg, (candidatas[0],), usadas)


def _decidir_soma(pg: PagamentoExtrato, parcelas: list[ParcelaSiga], usadas: set[str]) -> DecisaoPagamento:
    """Pagamento que soma todas as parcelas do fornecedor num vencimento, ou a pendência."""
    if _RE_INTERMEDIARIO.search(pg.nome):
        return DecisaoPagamento(pg, INTERMEDIARIO, f"pago a {pg.nome}, que não é o fornecedor")
    do_fornecedor = _do_fornecedor(pg, parcelas, usadas)
    grupos: dict[str, list[ParcelaSiga]] = {}
    for p in do_fornecedor:
        grupos.setdefault(p.vencimento, []).append(p)
    somam = [s for g in grupos.values() for s in _somas(g, pg.valor)]
    if len(somam) == 1:
        return _decisao_das(pg, tuple(somam[0]), usadas)
    if len(somam) > 1:
        return DecisaoPagamento(pg, EMPATE, f"mais de um vencimento soma {moeda(pg.valor)}")
    data = _data(pg.data)
    juros = [p for p in do_fornecedor if p.valor < pg.valor <= p.valor * (1 + JUROS_MAXIMO)
             and data and (_data(p.vencimento) or data) < data]
    if len(juros) == 1:
        p = juros[0]
        a_mais = f"{moeda(pg.valor - p.valor)} a mais que a provisão {_descricao(p)}"
        if p.status == PAGO:
            usadas.add(p.guid)
            return DecisaoPagamento(pg, JA_BAIXADA, f"{a_mais}, já paga no SIGA (com juros?)", (p,))
        return DecisaoPagamento(pg, VALOR_DIFERENTE, f"pago {a_mais} (juros?): baixe à mão com os juros")
    return DecisaoPagamento(pg, SEM_PROVISAO, f"nenhuma provisão de {moeda(pg.valor)} para {pg.nome} "
                                              f"com vencimento a até {JANELA_DIAS} dias")


def _quita(pg: PagamentoExtrato, p: ParcelaSiga) -> bool:
    """A parcela tem o valor do pagamento (a paga conta também pelo valor pago, com juros)."""
    return abs(p.valor - pg.valor) <= TOLERANCIA or (p.status == PAGO and abs(p.pago - pg.valor) <= TOLERANCIA)


def _somas(grupo: list[ParcelaSiga], valor: float) -> list[list[ParcelaSiga]]:
    """Parcelas de um vencimento que somam o pagamento: todas, ou todas menos uma.

    "Menos uma" cobre a parcela paga em outro pagamento (um PIX avulso no mesmo dia, de
    outro extrato) e só vale se uma única parcela, ao sair, fecha a soma.
    """
    if len(grupo) < 2:
        return []
    if abs(sum(p.valor for p in grupo) - valor) <= TOLERANCIA:
        return [grupo]
    sem_uma = [[q for q in grupo if q is not p] for p in grupo]
    fecham = [g for g in sem_uma if len(g) > 1 and abs(sum(q.valor for q in g) - valor) <= TOLERANCIA]
    return fecham if len(fecham) == 1 else []


def _decisao_das(pg: PagamentoExtrato, escolhidas: tuple[ParcelaSiga, ...], usadas: set[str]) -> DecisaoPagamento:
    status = {p.status for p in escolhidas}
    descricao = ", ".join(_descricao(p) for p in escolhidas)
    if status == {PAGO}:
        usadas.update(p.guid for p in escolhidas)
        return DecisaoPagamento(pg, JA_BAIXADA, f"{descricao} já está paga no SIGA", escolhidas)
    if status <= {LANCADO, APROVADO}:
        usadas.update(p.guid for p in escolhidas)
        return DecisaoPagamento(pg, BAIXAR, descricao, escolhidas)
    return DecisaoPagamento(pg, EMPATE, f"{descricao} com situação {', '.join(sorted(status))} no SIGA")


def _na_janela(pg: PagamentoExtrato, parcelas: list[ParcelaSiga], usadas: set[str]) -> list[ParcelaSiga]:
    return [p for p in parcelas if p.guid not in usadas and _distancia(pg, p) <= JANELA_DIAS]


def _do_fornecedor(pg: PagamentoExtrato, parcelas: list[ParcelaSiga], usadas: set[str]) -> list[ParcelaSiga]:
    return [p for p in _na_janela(pg, parcelas, usadas) if mesmo_fornecedor(pg.nome, p.fornecedor)]


def _distancia(pg: PagamentoExtrato, p: ParcelaSiga) -> int:
    """Dias entre o pagamento e o vencimento (sem data, fica fora de qualquer janela)."""
    a, b = _data(pg.data), _data(p.vencimento)
    return abs((a - b).days) if a and b else 10**6


def _descricao(p: ParcelaSiga) -> str:
    return f"{p.numero} de {p.fornecedor} ({moeda(p.valor)}, vence {p.vencimento})"


def _palavras(nome: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().upper()
    return [p for p in re.findall(r"[A-Z]{3,}", sem_acento) if p not in _PALAVRAS_VAZIAS]


def _parecidas(a: str, b: str) -> bool:
    curta, longa = sorted((a, b), key=len)
    return curta == longa or (len(curta) >= 4 and longa.startswith(curta))


def _data(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y")
    except (ValueError, AttributeError):
        return None


def motivo_aprovacao(decisao: DecisaoPagamento, conta_codigo: str) -> str:
    """Motivo gravado na aprovação: quem aprovou e a prova (o pagamento no extrato)."""
    pg = decisao.pagamento
    return (f"Aprovado automaticamente pelo AutoSIGA: {pg.tipo} de {moeda(pg.valor)} pago em {pg.data} "
            f"a {pg.nome} ({pg.documento}), no extrato da conta {conta_codigo}.")


def resumo_decisao(d: DecisaoPagamento) -> tuple[str, str]:
    """Nível ("ok", "alerta" ou "neutro") e a frase da decisão, para a prévia e o painel."""
    base = f"{d.pagamento.data} · {moeda(d.pagamento.valor)} · {d.pagamento.nome} · "
    if d.acao == BAIXAR:
        passo = "aprovar e baixar" if d.a_aprovar else "baixar"
        lote = " em lote" if len(d.parcelas) > 1 else ""
        return "ok", f"💳 {base}{passo}{lote} {d.motivo}"
    if d.acao == JA_BAIXADA:
        return "neutro", f"✔ {base}{d.motivo}"
    return "alerta", f"⚠ {base}não baixado: {d.motivo}"


def resultados_sem_execucao(decisoes: list[DecisaoPagamento],
                            situacao_baixar: str = NAO_AUTORIZADA) -> list[ResultadoPagamento]:
    """Resultados das decisões que não passam pelo SIGA (e das BAIXAR não executadas)."""
    return [ResultadoPagamento(d, situacao_baixar if d.acao == BAIXAR else d.acao, d.motivo) for d in decisoes]


def resumo_resultado(r: ResultadoPagamento) -> tuple[str, str]:
    """Nível e frase de um pagamento depois da execução, para o painel e o Excel."""
    d = r.decisao
    base = f"{d.pagamento.data} · {moeda(d.pagamento.valor)} · {d.pagamento.nome} · "
    provisoes = ", ".join(p.numero for p in d.parcelas)
    if r.situacao == BAIXADA:
        return "ok", f"💳 {base}provisão {provisoes} baixada"
    if r.situacao == APROVADA_SEM_BAIXA:
        return "alerta", f"⚠ {base}provisão {provisoes} aprovada, baixa pendente: {r.detalhe}"
    if r.situacao == FALHOU:
        return "alerta", f"⚠ {base}provisão {provisoes} não baixada: {r.detalhe}"
    if r.situacao == NAO_AUTORIZADA:
        return "neutro", f"— {base}provisão {provisoes}: baixa não autorizada por você"
    return resumo_decisao(d)


def linhas_do_painel(resultados: list[ResultadoPagamento] | None) -> list[tuple[str, str]]:
    """Linhas dos boletos e PIX de um extrato no painel: o total baixado e cada pendência.

    Os sem provisão entram só como contagem: a conciliação já lista cada um como movimento
    do banco sem lançamento no SIGA.
    """
    resultados = resultados or []
    contagem = {s: sum(1 for r in resultados if r.situacao == s) for s in (BAIXADA, JA_BAIXADA, SEM_PROVISAO)}
    linhas = []
    if contagem[BAIXADA]:
        linhas.append(("ok", f"💳 {contagem[BAIXADA]} boleto(s)/PIX baixado(s) na Contas a Pagar"))
    if contagem[JA_BAIXADA]:
        linhas.append(("neutro", f"✔ {contagem[JA_BAIXADA]} boleto(s)/PIX já estavam baixados no SIGA"))
    if contagem[SEM_PROVISAO]:
        linhas.append(("neutro", f"— {contagem[SEM_PROVISAO]} boleto(s)/PIX sem provisão na Contas a Pagar"))
    linhas += [resumo_resultado(r) for r in resultados if r.situacao not in contagem]
    return linhas
