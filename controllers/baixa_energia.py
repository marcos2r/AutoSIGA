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

from controllers.prova_real import moeda, valor_br
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

# O código pode faltar: o XLS do banco corta a descrição, e o leitor descarta o código incompleto
_RE_DEBITO_ENERGIA = re.compile(r"DEBITO\s+CONVENIOS-ENERGI(?:.*?\bID\s*(\d+))?", re.IGNORECASE)
_RE_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")

# Resultado da execução de uma decisão BAIXAR no SIGA (as outras decisões guardam a própria ação)
BAIXADA = "baixada"
APROVADA_SEM_BAIXA = "aprovada_sem_baixa"
FALHOU = "falhou"
NAO_AUTORIZADA = "nao_autorizada"


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


@dataclass(frozen=True)
class ResultadoBaixa:
    """O que aconteceu com um débito de energia do extrato.

    `situacao` é BAIXADA, APROVADA_SEM_BAIXA, FALHOU ou NAO_AUTORIZADA para as decisões
    BAIXAR; nas outras, é a própria ação da decisão (ex.: SEM_FATURA).
    """

    decisao: Decisao
    situacao: str
    detalhe: str = ""


def motivo_aprovacao(decisao: Decisao, conta_codigo: str) -> str:
    """Motivo gravado na aprovação: quem aprovou e a prova (o débito do extrato)."""
    d = decisao.debito
    return (f"Aprovado automaticamente pelo AutoSIGA: débito automático de {moeda(d.valor)} em {d.data} "
            f"no extrato da conta {conta_codigo} (código de débito {d.codigo}).")


def guid_valido(guid: str) -> bool:
    """O código da parcela vai na URL da TES01508/TES01506: só aceita o formato de GUID."""
    return bool(_RE_GUID.match(guid or ""))


def provisoes_da_grade(linhas: list[dict[str, Any]] | None) -> list[ProvisaoSiga]:
    """Provisões da Energisa a partir das linhas (texto) da grade da TES01501.

    Linhas de outro fornecedor, sem código de parcela válido ou com valor ilegível ficam de fora.
    """
    provisoes = []
    for linha in linhas or []:
        if "ENERGISA" not in str(linha.get("fornecedor", "")).upper():
            continue
        valor = valor_br(linha.get("valor"))
        guid = str(linha.get("guid", "")).strip()
        if valor is None or valor <= 0 or not guid_valido(guid):
            continue
        provisoes.append(ProvisaoSiga(str(linha.get("numero", "")).strip(), valor,
                                      str(linha.get("status", "")).strip(), guid,
                                      str(linha.get("vencimento", "")).strip()))
    return provisoes


def periodo_de_vencimento(data_inicial: str, data_final: str) -> tuple[str, str] | None:
    """Período de vencimento a consultar na TES01501 para os débitos de um extrato.

    Cobre a mesma janela de `decidir_baixas`: de 40 dias antes do início a 5 dias depois do fim.
    """
    ini, fim = _data(data_inicial), _data(data_final)
    if not ini or not fim:
        return None
    return ((ini - timedelta(days=_DIAS_ANTES_DO_DEBITO)).strftime("%d/%m/%Y"),
            (fim + timedelta(days=_DIAS_DEPOIS_DO_DEBITO)).strftime("%d/%m/%Y"))


def valor_siga(valor: float) -> str:
    """Valor como o SIGA mostra nos campos ("1.234,56")."""
    return moeda(valor).removeprefix("R$ ")


def mesmo_documento(numero_tela: str, numero: str) -> bool:
    """Nº Doc. da tela confere com o da provisão (o SIGA às vezes tira os zeros à esquerda)."""
    return _mesmo_numero(numero_tela or "", numero or "")


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
        tuple: (débitos a casar, decisões ESTORNADO dos débitos anulados por um crédito e
        SEM_FATURA dos débitos sem código).
    """
    debitos: list[DebitoEnergia] = []
    estornos: list[DebitoEnergia] = []
    sem_codigo: list[Decisao] = []
    for tx in transacoes:
        m = _RE_DEBITO_ENERGIA.search(str(tx.get("descricao", "")))
        if not m:
            continue
        valor = float(tx.get("valor", 0.0))
        item = DebitoEnergia(str(tx.get("data", "")), round(abs(valor), 2), m.group(1) or "")
        if not item.codigo:
            if valor < 0:
                sem_codigo.append(Decisao(item, SEM_FATURA, "o extrato não traz o código de débito automático "
                                                            "completo (o XLS do banco corta a descrição); "
                                                            "use o OFX para baixar"))
            continue
        (debitos if valor < 0 else estornos).append(item)

    anulados = []
    for estorno in estornos:
        par = next((d for d in debitos if d.codigo == estorno.codigo and abs(d.valor - estorno.valor) <= TOLERANCIA), None)
        if par:
            debitos.remove(par)
            anulados.append(Decisao(par, ESTORNADO, f"débito de {moeda(par.valor)} estornado pelo banco em {estorno.data}"))
    return debitos, anulados + sem_codigo


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


def resultados_sem_execucao(decisoes: list[Decisao], situacao_baixar: str = NAO_AUTORIZADA) -> list[ResultadoBaixa]:
    """Resultados das decisões que não passam pelo SIGA (e das BAIXAR não executadas)."""
    return [ResultadoBaixa(d, situacao_baixar if d.acao == BAIXAR else d.acao, d.motivo) for d in decisoes]


def resumo_baixa(r: ResultadoBaixa) -> tuple[str, str]:
    """Nível e frase de um débito de energia depois da execução, para o painel e o Excel."""
    d = r.decisao
    base = f"{d.debito.data} · {moeda(d.debito.valor)} · "
    fatura = f"fatura {d.provisao.numero}" if d.provisao else "fatura"
    if r.situacao == BAIXADA:
        return "ok", f"⚡ {base}{fatura} aprovada e baixada" if d.precisa_aprovar else f"⚡ {base}{fatura} baixada"
    if r.situacao == APROVADA_SEM_BAIXA:
        return "alerta", f"⚠ {base}{fatura} aprovada, baixa pendente: {r.detalhe}"
    if r.situacao == FALHOU:
        return "alerta", f"⚠ {base}{fatura} não baixada: {r.detalhe}"
    if r.situacao == NAO_AUTORIZADA:
        return "neutro", f"— {base}{fatura}: baixa não autorizada por você"
    return resumo_decisao(d)


def linhas_do_painel(resultados: list[ResultadoBaixa] | None) -> list[tuple[str, str]]:
    """Linhas de baixa de um extrato no painel: o total baixado e cada pendência.

    Faturas já pagas no SIGA (rodar o mesmo extrato de novo) entram só como contagem.
    """
    resultados = resultados or []
    baixadas = sum(1 for r in resultados if r.situacao == BAIXADA)
    ja_pagas = sum(1 for r in resultados if r.situacao == JA_BAIXADA)
    linhas = []
    if baixadas:
        linhas.append(("ok", f"⚡ {baixadas} fatura(s) de energia baixada(s)"))
    if ja_pagas:
        linhas.append(("neutro", f"✔ {ja_pagas} fatura(s) de energia já estavam pagas no SIGA"))
    linhas += [resumo_baixa(r) for r in resultados if r.situacao not in (BAIXADA, JA_BAIXADA)]
    return linhas
