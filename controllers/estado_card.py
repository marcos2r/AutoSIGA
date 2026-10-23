"""
Validação das contas digitadas ou escolhidas e estado (selo) do card de extrato.

Fica fora da UI para ser testado sem CustomTkinter: o card só repassa os valores dos
combos e desenha o que esta função devolver.
"""

from dataclasses import dataclass

from controllers.catalogo_contas import (
    GRUPO_APLICACAO,
    GRUPO_CORRENTE,
    TIPOS_LOCALIDADE,
    Catalogo,
    mesma_localidade,
    separar_localidade,
)

CONFIRMADO = "confirmado"
SUGERIDO = "sugerido"
EDITADO = "editado"
ESCOLHA = "escolha"
REVISAR = "revisar"
NAO_ENCONTRADO = "nao_encontrado"
PENDENTE = "pendente"

# Selo: ícone + palavra, nunca só cor (WCAG 1.4.1)
TEXTOS = {
    CONFIRMADO: "✔ Confirmado",
    SUGERIDO: "★ Sugerido pelo SIGA",
    EDITADO: "✎ Confirme a alteração",
    ESCOLHA: "? Escolha necessária",
    REVISAR: "! Revisar",
    NAO_ENCONTRADO: "✖ Não encontrado",
    PENDENTE: "✖ Não configurado",
}

_NOME_GRUPO = {GRUPO_CORRENTE: "conta corrente (101)", GRUPO_APLICACAO: "aplicação (103)"}


@dataclass(frozen=True)
class EstadoCard:
    """O que o card mostra e se o extrato pode ir para a conciliação.

    Attributes:
        chave: Uma das constantes deste módulo (CONFIRMADO, SUGERIDO...).
        mensagem: Explicação ou instrução curta para o usuário ("" quando não há).
        valido: True só quando o mapeamento está confirmado e consistente.
    """

    chave: str
    mensagem: str = ""
    valido: bool = False

    @property
    def texto(self) -> str:
        return TEXTOS[self.chave]


def codigo_do_combo(valor: str) -> str:
    """Código de um valor de combo: "10130 · CAPTAÇÃO" → "10130"; "10130" → "10130"."""
    return (valor or "").replace("·", " ").strip().split(" ")[0].strip()


def checar_localidade(localidade: str) -> str | None:
    """Mensagem de erro da localidade, ou None se ela tem tipo e nome."""
    tipo, nome = separar_localidade(localidade)
    if tipo not in TIPOS_LOCALIDADE or not nome:
        return "Escolha a localidade no formato TIPO - NOME (ex.: ADM - DOURADOS - MS)."
    return None


def checar_codigo(catalogo: Catalogo, codigo: str, grupo: str, localidade: str) -> str | None:
    """Confere se o código pode ser usado no campo do grupo informado.

    Sem catálogo, confere só o grupo (101 corrente, 103 aplicação), o que já impede a
    inversão. Com catálogo, o código precisa existir ativo na localidade, salvo quando
    o usuário não tem acesso a ela (a leitura não pôde conferir).

    Returns:
        Mensagem de erro para o usuário, ou None se o código é aceito.
    """
    nome_grupo = _NOME_GRUPO[grupo]
    if not codigo.isdigit() or not codigo.startswith(grupo) or len(codigo) <= len(grupo):
        return f"O código {codigo} não é de {nome_grupo}."
    if catalogo.vazio or catalogo.sem_acesso_a(localidade):
        return None
    contas = [c for c in catalogo.contas if c.ativa and c.codigo == codigo]
    if not contas:
        return f"O código {codigo} não existe entre as contas ativas do SIGA."
    if not any(mesma_localidade(c.localidade, localidade) for c in contas):
        return f"O código {codigo} é da localidade {contas[0].localidade}, não de {localidade}."
    return None


def avaliar_card(catalogo: Catalogo, aplicacao: bool, localidade: str, corrente: str, aplic: str,
                 confirmado: bool, origem_sugestao: bool = False, tem_opcoes: bool = False,
                 motivo_sugestao: str = "") -> EstadoCard:
    """Decide o selo do card e se ele libera a conciliação.

    Args:
        catalogo: Contas lidas do SIGA (pode estar vazio).
        aplicacao: True em extrato de aplicação (não usa C. Corrente).
        localidade: Valor do combo de localidade ("ADM - DOURADOS - MS").
        corrente: Código da C. Corrente ("" quando vazio).
        aplic: Código da C. Aplicação ("" quando vazio).
        confirmado: True se o mapeamento está salvo e não foi alterado.
        origem_sugestao: True se os valores vieram da sugestão e não foram mexidos.
        tem_opcoes: True se os combos vazios têm opções para escolher.
        motivo_sugestao: Motivo devolvido pela sugestão, mostrado ao usuário.

    Returns:
        EstadoCard com chave, mensagem e validade.
    """
    campos = [] if aplicacao else [(corrente, GRUPO_CORRENTE)]
    campos.append((aplic, GRUPO_APLICACAO))

    faltando = [g for valor, g in campos if not valor]
    erro_loc = checar_localidade(localidade) if localidade else None
    erros = [e for e in [erro_loc] if e]
    if not erro_loc:
        erros += [e for valor, g in campos if valor and (e := checar_codigo(catalogo, valor, g, localidade))]

    if confirmado:
        if erros:
            return EstadoCard(REVISAR, erros[0] + " Escolha a conta certa e confirme de novo.")
        if faltando or not localidade:
            return EstadoCard(PENDENTE, "Mapeamento incompleto. Preencha os campos e confirme.")
        return EstadoCard(CONFIRMADO, valido=True)

    if erros:
        return EstadoCard(NAO_ENCONTRADO, erros[0])
    if not faltando and localidade:
        if origem_sugestao:
            return EstadoCard(SUGERIDO, motivo_sugestao or "Confira e clique em Confirmar.")
        return EstadoCard(EDITADO, "Confira os campos e clique em Confirmar.")
    if tem_opcoes:
        return EstadoCard(ESCOLHA, motivo_sugestao or "Escolha as contas nas listas e clique em Confirmar.")
    if catalogo.vazio:
        return EstadoCard(PENDENTE, motivo_sugestao or
                          "Clique em Buscar no SIGA para preencher sozinho, ou digite a localidade e as contas.")
    return EstadoCard(NAO_ENCONTRADO, motivo_sugestao or "Nenhuma conta do SIGA corresponde a este extrato.")
