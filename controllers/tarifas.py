"""
Tarifas do extrato: o que lançar como despesa em Caixas e Bancos (TES01702), Fase 2.

Decisão pura, sem navegador. Parte das faltas da prova real (movimentos do banco sem
lançamento no SIGA), escolhe as que o classificador marca como TARIFA e monta um
lançamento por linha do extrato, para casar um a um na conferência seguinte.

As contas vêm da configuração (`config.json`, chave "tarifas"); os padrões foram
confirmados pelo usuário em 23/11/2026. "ativo": false no config.json desliga o recurso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from controllers.classificador_extrato import TARIFA, classificar
from controllers.prova_real import MovimentoBanco

# Levantados na TES01702 em 23/11/2026 (docs/regras/siga.md); o usuário confirma antes de ligar
PADRAO = {
    "ativo": True,                 # contas confirmadas pelo usuário em 23/11/2026
    "despesa": "3030",            # 3030 - DESPESAS BANCARIAS
    "historico": "012",           # 012 - DESP.BANCÁRIAS
    "tipo_documento": "AVISO DE DÉBITO",
    "forma_pagamento": "DÉBITO AUTOMÁTICO",
    "centro_custo": "ADM",
}

# Fornecedor obrigatório na TES01702 (visto no teste de 23/11/2026): o próprio banco da conta.
# Cada administração tem o seu cadastro (Dourados usa "SICREDI CENTRO-SUL MS/BA"), então o robô
# pesquisa pelo nome do banco e escolhe entre os resultados o da cidade da administração.
# Código do banco (FEBRABAN) -> termos de busca no cadastro de fornecedores do SIGA
TERMOS_POR_BANCO = {
    "748": ["SICREDI"],
    "756": ["SICOOB", "BANCOOB"],
    "1": ["BANCO DO BRASIL"],
    "104": ["CAIXA ECONOMICA", "CAIXA ECONÔMICA"],
    "237": ["BRADESCO"],
    "341": ["ITAU", "ITAÚ"],
    "33": ["SANTANDER"],
}


def codigo_banco(banco: Any) -> str:
    """Código do banco só com dígitos e sem zeros à esquerda ("0748" → "748")."""
    return "".join(c for c in str(banco or "") if c.isdigit()).lstrip("0")


def termos_do_banco(banco: Any, extras: dict[str, Any] | None = None) -> list[str]:
    """Termos de busca do fornecedor da conta; o config.json ("fornecedores") vem primeiro.

    Returns:
        list[str]: vazia se o banco é desconhecido e não há termo no config.
    """
    codigo = codigo_banco(banco)
    do_config = (extras or {}).get(codigo)
    termos = [do_config] if isinstance(do_config, str) and do_config.strip() else []
    return termos + [t for t in TERMOS_POR_BANCO.get(codigo, []) if t not in termos]


def escolher_fornecedor(resultados: list[str], termo: str, cidade: str) -> int | None:
    """Qual resultado da busca usar: o que traz o termo, preferindo o da cidade da administração.

    Args:
        resultados: Texto de cada resultado do Select2 (nome, endereço, CNPJ).
        termo: O que foi pesquisado (ex.: "SICREDI").
        cidade: Cidade da administração (ex.: "DOURADOS"); vazia aceita o primeiro.

    Returns:
        O índice escolhido, ou None se nenhum resultado traz o termo.
    """
    from controllers.classificador_extrato import normalizar

    alvo, local = normalizar(termo), normalizar(cidade)
    candidatos = [i for i, r in enumerate(resultados) if alvo in normalizar(r)]
    if not candidatos:
        return None
    da_cidade = [i for i in candidatos if local and local in normalizar(resultados[i])]
    return (da_cidade or candidatos)[0]


def cidade_da_localidade(nome_adm: Any) -> str:
    """"DOURADOS - MS" → "DOURADOS": a cidade que aparece no endereço do fornecedor local."""
    return str(nome_adm or "").split(" - ")[0].strip()


def centro_custo_da_localidade(nome_adm: Any, padrao: str = "ADM", tipo_adm: Any = "") -> str:
    """Usa "DR" no rateio quando a conta pertence à Diretoria Regional; senão mantém o padrão."""
    tipo = str(tipo_adm or "").strip().upper()
    nome = str(nome_adm or "").strip().upper()
    if padrao.upper() == "ADM" and (tipo == "DR" or nome == "DR" or nome.startswith(("DR ", "DR-"))):
        return "DR"
    return padrao


@dataclass(frozen=True)
class RegraTarifa:
    """Como a Administração lança tarifa no SIGA."""

    ativo: bool
    despesa: str
    historico: str
    tipo_documento: str
    forma_pagamento: str
    centro_custo: str
    # Termo de busca do fornecedor por código de banco ({"748": "SICREDI CENTRO-SUL"}), opcional
    fornecedores: tuple[tuple[str, str], ...] = ()

    @classmethod
    def da_config(cls, dados: dict[str, Any] | None) -> RegraTarifa:
        """Junta o que está no config.json com os padrões; chave desconhecida é ignorada."""
        valores = {**PADRAO, **{k: v for k, v in (dados or {}).items() if k in PADRAO}}
        extras = (dados or {}).get("fornecedores")
        fornecedores = tuple((codigo_banco(k), str(v)) for k, v in extras.items()) if isinstance(extras, dict) else ()
        return cls(ativo=bool(valores["ativo"]), despesa=str(valores["despesa"]),
                   historico=str(valores["historico"]), tipo_documento=str(valores["tipo_documento"]),
                   forma_pagamento=str(valores["forma_pagamento"]), centro_custo=str(valores["centro_custo"]),
                   fornecedores=fornecedores)


@dataclass(frozen=True)
class LancamentoTarifa:
    """Uma despesa a gravar na TES01702."""

    data: str
    valor: float     # positivo: o valor da despesa
    descricao: str   # vai no complemento, para achar a linha do extrato depois
    documento: str   # Nº Documento: a data sem barras, como no lançamento manual de rendimento


def planejar(faltas: list[MovimentoBanco] | None, regra: RegraTarifa) -> list[LancamentoTarifa]:
    """Tarifas do extrato que ainda não estão no SIGA, uma por linha.

    Returns:
        list[LancamentoTarifa]: vazia se o recurso estiver desligado ou não houver tarifa.
    """
    if not regra.ativo:
        return []
    lancamentos = []
    for f in faltas or []:
        if f.valor >= 0 or classificar({"descricao": f.descricao, "valor": f.valor}).categoria != TARIFA:
            continue
        lancamentos.append(LancamentoTarifa(f.data, round(-f.valor, 2), " ".join(f.descricao.split())[:60],
                                            f.data.replace("/", "")))
    return lancamentos
