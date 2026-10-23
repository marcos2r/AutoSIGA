"""
Sugestão das contas do SIGA para um extrato (correspondência de registros).

Determinística e explicável: filtra o catálogo pelos dígitos da CC (bloqueio), pontua os
candidatos por regras fixas (grupo, produto, localidade já usada) e só sugere quando há
um vencedor único. No empate, se abstém e pede a escolha ao usuário: em lançamento
financeiro, abster-se é melhor que errar.
"""

from dataclasses import dataclass, field

from controllers.catalogo_contas import (
    GRUPO_APLICACAO,
    GRUPO_CORRENTE,
    Catalogo,
    ContaSiga,
    cc_bate,
    mesma_localidade,
    normalizar_texto,
)

SUGERIDO = "sugerido"
ESCOLHA = "escolha"
NAO_ENCONTRADO = "nao_encontrado"

_PESO_PRODUTO = 2
_PESO_LOCALIDADE = 1


@dataclass
class Campo:
    """Resultado de um campo do card (corrente ou aplicação).

    Attributes:
        escolhida: Conta sugerida, ou None quando há empate ou nenhum candidato.
        opcoes: Candidatos em ordem de pontuação (a sugerida primeiro).
    """

    escolhida: ContaSiga | None = None
    opcoes: list[ContaSiga] = field(default_factory=list)


@dataclass
class Sugestao:
    """O que o catálogo sugere para um extrato.

    Attributes:
        status: SUGERIDO, ESCOLHA ou NAO_ENCONTRADO.
        localidade: Localidade sugerida ("" quando indefinida).
        corrente: Campo C. Corrente (vazio em extrato de aplicação).
        aplicacao: Campo C. Aplicação.
        motivo: Explicação curta para o usuário.
    """

    status: str
    localidade: str = ""
    corrente: Campo = field(default_factory=Campo)
    aplicacao: Campo = field(default_factory=Campo)
    motivo: str = ""


def _pontos_produto(conta: ContaSiga, produto: str) -> tuple[int, str]:
    """Pontua a finalidade da conta 103 pelo produto do XLS (POUPANCA ↔ POUP, SICREDINVEST ↔ INV/APLIC)."""
    prod = normalizar_texto(produto)
    fin = normalizar_texto(conta.finalidade)
    if not prod or not fin:
        return 0, ""
    if "POUP" in prod and "POUP" in fin:
        return _PESO_PRODUTO, f"produto {produto.strip()} ↔ {conta.finalidade}"
    if "SICREDINVEST" in prod and ("INV" in fin or "APLIC" in fin):
        return _PESO_PRODUTO, f"produto {produto.strip()} ↔ {conta.finalidade}"
    return 0, ""


def _escolher(candidatos: list[ContaSiga], produto: str, localidade_preferida: str) -> tuple[Campo, list[str]]:
    """Ordena os candidatos por pontuação e escolhe só se houver vencedor único."""
    pontuados = []
    for conta in candidatos:
        pontos, motivos = 0, []
        p_prod, m_prod = _pontos_produto(conta, produto)
        if p_prod:
            pontos += p_prod
            motivos.append(m_prod)
        if localidade_preferida and mesma_localidade(conta.localidade, localidade_preferida):
            pontos += _PESO_LOCALIDADE
            motivos.append("localidade já usada nesta conta")
        pontuados.append((pontos, conta, motivos))

    # Ordenação estável: no empate, mantém a ordem do catálogo (código crescente)
    pontuados.sort(key=lambda item: (-item[0], item[1].codigo))
    opcoes = [conta for _, conta, _ in pontuados]
    if not pontuados:
        return Campo(), []
    if len(pontuados) > 1 and pontuados[0][0] == pontuados[1][0]:
        return Campo(None, opcoes), []
    return Campo(pontuados[0][1], opcoes), pontuados[0][2]


def sugerir(catalogo: Catalogo, conta_id: str, aplicacao: bool, produto: str = "",
            localidade_preferida: str = "") -> Sugestao:
    """Sugere localidade, C. Corrente e C. Aplicação para um extrato.

    Args:
        catalogo: Contas lidas do SIGA.
        conta_id: Conta do extrato (OFX ou XLS), em qualquer formato.
        aplicacao: True para extrato de aplicação (XLS), que só usa o grupo 103.
        produto: Produto do XLS ("POUPANCA TRADICIONAL", "SICREDINVEST AUTOMATICO").
        localidade_preferida: Localidade de um mapeamento já confirmado desta conta.

    Returns:
        Sugestao com status, campos e motivo.
    """
    candidatos = [c for c in catalogo.contas if c.ativa and cc_bate(c.cc, conta_id)]
    correntes = [c for c in candidatos if c.grupo == GRUPO_CORRENTE]
    aplicacoes = [c for c in candidatos if c.grupo == GRUPO_APLICACAO]

    if aplicacao:
        if not aplicacoes:
            return Sugestao(NAO_ENCONTRADO, motivo=_motivo_nao_encontrado(catalogo, "aplicação"))
        campo, motivos = _escolher(aplicacoes, produto, localidade_preferida)
        localidade = campo.escolhida.localidade if campo.escolhida else _localidade_unica(campo.opcoes)
        if not campo.escolhida:
            return Sugestao(ESCOLHA, localidade, aplicacao=campo,
                            motivo=f"Esta conta tem {len(campo.opcoes)} aplicações no SIGA. "
                                   "Escolha a que corresponde ao extrato.")
        return Sugestao(SUGERIDO, localidade, aplicacao=campo,
                        motivo=_motivo_sugerido("grupo 103", motivos))

    if not correntes:
        return Sugestao(NAO_ENCONTRADO, motivo=_motivo_nao_encontrado(catalogo, "conta corrente"))
    campo_cc, motivos_cc = _escolher(correntes, "", localidade_preferida)
    localidade = campo_cc.escolhida.localidade if campo_cc.escolhida else _localidade_unica(campo_cc.opcoes)

    # A aplicação vem da mesma localidade da corrente quando ela já está definida
    aplic_local = [c for c in aplicacoes if not localidade or mesma_localidade(c.localidade, localidade)]
    campo_ap, _ = _escolher(aplic_local, produto, localidade_preferida)

    if not campo_cc.escolhida:
        return Sugestao(ESCOLHA, localidade, campo_cc, campo_ap,
                        motivo=f"A CC aparece em {len(campo_cc.opcoes)} contas correntes do SIGA. Escolha a certa.")
    if not campo_ap.opcoes:
        return Sugestao(NAO_ENCONTRADO, localidade, campo_cc, campo_ap,
                        motivo="A conta corrente foi encontrada, mas nenhuma aplicação (103) da mesma CC "
                               "na localidade. Escolha a aplicação em Editar.")
    if not campo_ap.escolhida:
        return Sugestao(ESCOLHA, localidade, campo_cc, campo_ap,
                        motivo=f"Esta conta tem {len(campo_ap.opcoes)} aplicações no SIGA. "
                               "Escolha a que corresponde ao extrato.")
    return Sugestao(SUGERIDO, localidade, campo_cc, campo_ap,
                    motivo=_motivo_sugerido("grupo 101 e 103", motivos_cc))


def _localidade_unica(contas: list[ContaSiga]) -> str:
    """A localidade comum a todas as opções, ou "" se forem de localidades diferentes."""
    locais = {c.localidade for c in contas}
    return next(iter(locais)) if len(locais) == 1 else ""


def _motivo_sugerido(grupos: str, extras: list[str]) -> str:
    return "Sugerido pelo SIGA: CC igual; " + "; ".join([grupos, *extras]) + "."


def _motivo_nao_encontrado(catalogo: Catalogo, tipo: str) -> str:
    if catalogo.vazio:
        return "Contas do SIGA ainda não lidas. Clique em Buscar no SIGA ou digite a localidade e as contas."
    texto = (f"Nenhuma {tipo} com esta CC nas localidades que você acessa no SIGA. "
             "Confira se o extrato é da conta certa ou peça à administração para cadastrar a conta.")
    if catalogo.localidades_sem_acesso:
        texto += f" Sem acesso a: {', '.join(catalogo.localidades_sem_acesso)}."
    return texto
