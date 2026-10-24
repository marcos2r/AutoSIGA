"""Localidades de energia sincronizadas com o seletor "Local de Trabalho" do SIGA.

O robô já abre esse seletor para trocar de localidade; a lista de opções vem daqui para
o `config.json`. Só acrescenta e corrige nomes: uma localidade que sumiu da lista pode
ser só falta de acesso do usuário desta máquina, e há UCs relacionadas a ela.
"""

import re

from controllers.catalogo_contas import separar_localidade

# Casa de oração ("BR 10-0054", "XX 10-0563") ou sigla da administração ("ADM", "DR", "SEC")
_RE_CODIGO = re.compile(r"^(?:[A-Z]{2} \d{2}-\d{4}|[A-Z]{2,4})$")


def codigo_localidade_valido(codigo: str) -> bool:
    """Diz se o código tem o formato das localidades do SIGA ("BR 10-0054" ou "ADM")."""
    return bool(_RE_CODIGO.match(" ".join((codigo or "").upper().split())))


def localidades_do_seletor(textos: list[str]) -> list[tuple[str, str]]:
    """Converte as opções do seletor em pares (código, nome), na ordem do SIGA.

    "* Selecione *" e textos fora do padrão ficam de fora. Um código que aparece com
    nomes diferentes (vários "SET - SETOR 0N") é descartado: o código é a chave do
    cadastro e não daria para saber qual nome vale.

    Args:
        textos: Textos das opções, ex.: ["ADM - DOURADOS - MS", "BR 10-0054 - VILA PLANALTO"].

    Returns:
        list[tuple[str, str]]: Pares (código, nome) em maiúsculas, sem repetição.
    """
    pares: list[tuple[str, str]] = []
    for texto in textos:
        codigo, nome = separar_localidade(texto)
        if nome and codigo_localidade_valido(codigo) and (codigo, nome) not in pares:
            pares.append((codigo, nome))
    nomes_por_codigo: dict[str, int] = {}
    for codigo, _ in pares:
        nomes_por_codigo[codigo] = nomes_por_codigo.get(codigo, 0) + 1
    return [(c, n) for c, n in pares if nomes_por_codigo[c] == 1]


def mesclar_localidades(atuais: list[dict], do_siga: list[tuple[str, str]]
                        ) -> tuple[list[dict], list[str], list[str]]:
    """Junta o cadastro local com as localidades lidas do SIGA.

    Args:
        atuais: Cadastro atual, [{"codigo": ..., "nome": ...}].
        do_siga: Pares (código, nome) de `localidades_do_seletor`.

    Returns:
        tuple: (cadastro novo, rótulos das localidades novas, rótulos das renomeadas).
            O nome do SIGA prevalece; nada é removido.
    """
    cadastro = [dict(loc) for loc in atuais]
    por_codigo = {str(loc.get("codigo", "")).upper(): loc for loc in cadastro}
    novas: list[str] = []
    renomeadas: list[str] = []
    for codigo, nome in do_siga:
        loc = por_codigo.get(codigo)
        if loc is None:
            loc = {"codigo": codigo, "nome": nome}
            cadastro.append(loc)
            por_codigo[codigo] = loc
            novas.append(f"{codigo} - {nome}")
        elif str(loc.get("nome", "")).upper() != nome:
            loc["nome"] = nome
            renomeadas.append(f"{codigo} - {nome}")
    return cadastro, novas, renomeadas


def sincronizar_localidades(textos: list[str], config_mgr) -> tuple[list[str], list[str]]:
    """Grava no `config.json` as localidades novas ou renomeadas do seletor do SIGA.

    Args:
        textos: Textos das opções do seletor "Local de Trabalho".
        config_mgr: ConfigManager com `get_localidades_energia`/`salvar_localidades_energia`.

    Returns:
        tuple[list[str], list[str]]: (novas, renomeadas), como "BR 10-0054 - VILA PLANALTO".
    """
    do_siga = localidades_do_seletor(textos)
    if not do_siga:
        return [], []
    cadastro, novas, renomeadas = mesclar_localidades(config_mgr.get_localidades_energia(), do_siga)
    if novas or renomeadas:
        config_mgr.salvar_localidades_energia(cadastro)
    return novas, renomeadas
