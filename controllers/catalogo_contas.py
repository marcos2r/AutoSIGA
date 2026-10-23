"""
Catálogo das contas bancárias do SIGA (grupos 101 e 103) e leitura dos rótulos.

Regra pura, sem I/O: transforma o texto que o bot lê no SIGA (opções do `select#f_conta`
da TES01701 ou linhas da grade do Plano de Contas CTB00301) em `ContaSiga`. Os rótulos
são texto livre e variam (`AG:0101` / `AG: 0101`, CC com e sem hífen), por isso a
comparação de contas usa só os dígitos.
"""

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

GRUPO_CORRENTE = "101"
GRUPO_APLICACAO = "103"
GRUPOS_BANCARIOS = (GRUPO_CORRENTE, GRUPO_APLICACAO)
TIPOS_LOCALIDADE = ("ADM", "DR", "PIA")

# Menor trecho de dígitos aceito para dizer que duas contas são a mesma: evita que
# uma CC curta (ou só o dígito verificador) case por acaso com o fim de outra.
_MIN_DIGITOS_CC = 4

_RE_CODIGO_TESOURARIA = re.compile(r"^\s*(\d{4,6})\s*-\s*(.*)$", re.DOTALL)
_RE_AGENCIA = re.compile(r"\bAG\s*\.?\s*:?\s*(\d[\d.\-]*)", re.IGNORECASE)
_RE_CC = re.compile(r"\bC\s*\.?\s*C\s*\.?\s*:?\s*(\d[\d.\-\s]*\d|\d)", re.IGNORECASE)


@dataclass(frozen=True)
class ContaSiga:
    """Uma conta bancária do plano de contas do SIGA.

    Attributes:
        codigo: Código da Tesouraria (ex.: "10130"), igual ao Cód. Reduzido sem espaço.
        grupo: "101" (conta corrente) ou "103" (aplicação).
        localidade: Como o SIGA mostra (ex.: "ADM - DOURADOS - MS").
        banco: Nome do banco no rótulo (ex.: "SICREDI").
        agencia: Só os dígitos da agência.
        cc: Só os dígitos da conta, com o DV, sem zeros à esquerda.
        finalidade: Texto depois da conta no rótulo (ex.: "CAPTAÇÃO", "POUPANÇA").
        ativa: False quando o SIGA marca a conta como inativa.
    """

    codigo: str
    grupo: str
    localidade: str
    banco: str = ""
    agencia: str = ""
    cc: str = ""
    finalidade: str = ""
    ativa: bool = True

    @property
    def rotulo_curto(self) -> str:
        """Texto do combo do card: "10130 · CAPTAÇÃO"."""
        return f"{self.codigo} · {self.finalidade}" if self.finalidade else self.codigo

    def para_dict(self) -> dict[str, Any]:
        """Formato gravado no config.json."""
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> "ContaSiga":
        """Reconstrói a conta a partir do config.json, ignorando chaves desconhecidas."""
        return cls(
            codigo=str(dados.get("codigo", "")),
            grupo=str(dados.get("grupo", "")),
            localidade=str(dados.get("localidade", "")),
            banco=str(dados.get("banco", "")),
            agencia=str(dados.get("agencia", "")),
            cc=str(dados.get("cc", "")),
            finalidade=str(dados.get("finalidade", "")),
            ativa=bool(dados.get("ativa", True)),
        )


@dataclass
class Catalogo:
    """Contas lidas do SIGA e de onde vieram.

    Attributes:
        contas: Contas bancárias ativas e inativas.
        lido_em: Data e hora ISO da leitura ("" quando nunca foi lido).
        fonte: "CTB00301" ou "TES01701".
        localidades_sem_acesso: Localidades que o bot não conseguiu abrir.
    """

    contas: list[ContaSiga] = field(default_factory=list)
    lido_em: str = ""
    fonte: str = ""
    localidades_sem_acesso: list[str] = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not self.contas

    def localidades(self) -> list[str]:
        """Localidades com alguma conta ativa, na ordem ADM, DR, PIA."""
        nomes = {c.localidade for c in self.contas if c.ativa and c.localidade}
        return sorted(nomes, key=_ordem_localidade)

    def contas_de(self, grupo: str, localidade: str | None = None) -> list[ContaSiga]:
        """Contas ativas de um grupo, opcionalmente só de uma localidade."""
        return [c for c in self.contas
                if c.ativa and c.grupo == grupo
                and (localidade is None or mesma_localidade(c.localidade, localidade))]

    def buscar(self, codigo: str) -> ContaSiga | None:
        """Conta ativa com esse código, ou None."""
        codigo = so_digitos(codigo)
        return next((c for c in self.contas if c.ativa and c.codigo == codigo), None)

    def sem_acesso_a(self, localidade: str) -> bool:
        """True se a localidade ficou de fora da leitura por falta de acesso."""
        return any(mesma_localidade(localidade, s) for s in self.localidades_sem_acesso)


def _ordem_localidade(localidade: str) -> tuple[int, str]:
    tipo, _ = separar_localidade(localidade)
    posicao = TIPOS_LOCALIDADE.index(tipo) if tipo in TIPOS_LOCALIDADE else len(TIPOS_LOCALIDADE)
    return posicao, localidade


def so_digitos(texto: Any) -> str:
    """Só os dígitos do texto, sem zeros à esquerda ("012345-6" → "123456")."""
    return "".join(ch for ch in str(texto or "") if ch.isdigit()).lstrip("0")


def normalizar_texto(texto: str) -> str:
    """Maiúsculas, sem acento e com espaços simples, para comparar rótulos."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.upper().split())


def cc_bate(cc_catalogo: str, conta_extrato: str) -> bool:
    """Diz se a conta do extrato é a mesma CC do catálogo.

    O OFX da Sicredi traz agência + zeros + CC (16 dígitos) e o XLS só a CC; por isso
    vale igualdade ou um ser o final do outro, com pelo menos 4 dígitos em comum.

    Args:
        cc_catalogo: CC da conta no SIGA (qualquer formato).
        conta_extrato: `conta_id` do extrato (qualquer formato).
    """
    a, b = so_digitos(cc_catalogo), so_digitos(conta_extrato)
    if len(a) < _MIN_DIGITOS_CC or len(b) < _MIN_DIGITOS_CC:
        return False
    return a == b or a.endswith(b) or b.endswith(a)


def separar_localidade(localidade: str) -> tuple[str, str]:
    """Converte "ADM - DOURADOS - MS" no par ("ADM", "DOURADOS - MS") que o bot usa."""
    texto = " ".join((localidade or "").upper().split())
    tipo, _, nome = texto.partition(" - ")
    if not nome:
        return "", texto
    return tipo.strip(), nome.strip()


def mesma_localidade(a: str, b: str) -> bool:
    """Compara localidades tolerando o nome curto salvo pelos mapeamentos antigos.

    "ADM - DOURADOS" (digitado pelo usuário) e "ADM - DOURADOS - MS" (SIGA) são a mesma;
    "DR - DOURADOS" e "ADM - DOURADOS - MS" não são.
    """
    tipo_a, nome_a = separar_localidade(a)
    tipo_b, nome_b = separar_localidade(b)
    if not (tipo_a and tipo_b and nome_a and nome_b) or tipo_a != tipo_b:
        return False
    nome_a, nome_b = normalizar_texto(nome_a), normalizar_texto(nome_b)
    return nome_a == nome_b or nome_a.startswith(nome_b + " ") or nome_b.startswith(nome_a + " ")


def _partes_do_nome(nome: str) -> tuple[str, str, str, str]:
    """Extrai (banco, agência, CC, finalidade) de "SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO"."""
    texto = " ".join((nome or "").split())
    m_ag = _RE_AGENCIA.search(texto)
    m_cc = _RE_CC.search(texto)
    agencia = so_digitos(m_ag.group(1)) if m_ag else ""
    cc = so_digitos(m_cc.group(1)) if m_cc else ""

    fim_banco = min((m.start() for m in (m_ag, m_cc) if m), default=len(texto))
    banco = texto[:fim_banco].strip(" -:")
    finalidade = texto[m_cc.end():].strip(" -:") if m_cc else ""
    return banco, agencia, cc, finalidade


def codigo_do_rotulo(rotulo: str) -> str | None:
    """Código reduzido de uma opção da TES01701 ("10130 - SICREDI ..." → "10130"), ou None."""
    m = _RE_CODIGO_TESOURARIA.match(rotulo or "")
    return m.group(1) if m else None


def escolher_opcao_conta(opcoes: list[dict[str, Any]], codigo: str) -> str | None:
    """Valor da opção ativa do `select#f_conta` cujo código é exatamente `codigo`.

    Compara o código inteiro, nunca um trecho do rótulo: "10130" não pode casar com
    "110130 - ...". Contas do `optgroup` INATIVO são ignoradas.

    Args:
        opcoes: Opções lidas da página ({"texto", "valor", "inativa"}).
        codigo: Código reduzido da conta escolhida no card.

    Returns:
        O `value` da opção, ou None se a conta não estiver na lista.
    """
    alvo = (codigo or "").strip()
    if not alvo:
        return None
    for opcao in opcoes:
        if not opcao.get("inativa") and codigo_do_rotulo(opcao.get("texto", "")) == alvo:
            return str(opcao.get("valor", ""))
    return None


def ler_rotulo_tesouraria(rotulo: str, localidade: str, inativa: bool = False) -> ContaSiga | None:
    """Lê uma opção do `select#f_conta` da TES01701.

    Args:
        rotulo: Texto da opção ("10130 - SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO").
        localidade: Localidade ativa quando a opção foi lida.
        inativa: True quando a opção estava no `optgroup` INATIVO.

    Returns:
        ContaSiga, ou None se não for conta bancária (caixa, grupo diferente de 101/103).
    """
    m = _RE_CODIGO_TESOURARIA.match(rotulo or "")
    if not m:
        return None
    codigo = m.group(1)
    if codigo[:3] not in GRUPOS_BANCARIOS:
        return None
    banco, agencia, cc, finalidade = _partes_do_nome(m.group(2))
    return ContaSiga(codigo=codigo, grupo=codigo[:3], localidade=" ".join(localidade.upper().split()),
                     banco=banco, agencia=agencia, cc=cc, finalidade=finalidade, ativa=not inativa)


def ler_linha_plano_contas(codigo_reduzido: str, nome: str, localidade: str, status: str = "") -> ContaSiga | None:
    """Lê uma linha da grade do Plano de Contas (CTB00301).

    Args:
        codigo_reduzido: Coluna "Cód. Reduzido" ("101 30" equivale a "10130").
        nome: Coluna "Nome" ("SICREDI - AG: 0101 CC: 12345-6 CAPTAÇÃO").
        localidade: Coluna "Localidade" ("ADM - DOURADOS - MS").
        status: Coluna "Status"; "Inativo" marca a conta como inativa.

    Returns:
        ContaSiga, ou None para contas fora dos grupos 101/103 ou de localidade genérica.
    """
    codigo = "".join(ch for ch in codigo_reduzido or "" if ch.isdigit())
    if len(codigo) < 4 or codigo[:3] not in GRUPOS_BANCARIOS:
        return None
    tipo, nome_loc = separar_localidade(localidade)
    # Contas genéricas listam vários tipos ("ADM, SET, PIA..."): não são de uma localidade só
    if tipo not in TIPOS_LOCALIDADE or not nome_loc:
        return None
    banco, agencia, cc, finalidade = _partes_do_nome(nome)
    inativa = "INATIV" in normalizar_texto(status)
    return ContaSiga(codigo=codigo, grupo=codigo[:3], localidade=f"{tipo} - {nome_loc}",
                     banco=banco, agencia=agencia, cc=cc, finalidade=finalidade, ativa=not inativa)


def consolidar(contas: list[ContaSiga]) -> list[ContaSiga]:
    """Remove repetições da leitura pela Tesouraria.

    A ADM também lista a conta corrente da DR. Quando o mesmo código aparece em mais de
    uma localidade, fica a localidade que tem outra conta da mesma CC (a dona); se isso
    não desempatar, ficam todas e a sugestão pede a escolha ao usuário.

    Returns:
        Lista sem duplicatas exatas, na ordem original.
    """
    por_codigo: dict[str, list[ContaSiga]] = {}
    for conta in contas:
        lista = por_codigo.setdefault(conta.codigo, [])
        if not any(mesma_localidade(c.localidade, conta.localidade) for c in lista):
            lista.append(conta)

    manter: set[tuple[str, str]] = set()
    for codigo, versoes in por_codigo.items():
        if len(versoes) > 1:
            donas = [v for v in versoes
                     if v.cc and any(o.codigo != codigo and o.cc == v.cc and mesma_localidade(o.localidade, v.localidade)
                                     for o in contas)]
            if len(donas) == 1:
                versoes = donas
        manter.update((v.codigo, v.localidade) for v in versoes)

    vistos: set[tuple[str, str]] = set()
    resultado = []
    for conta in contas:
        chave = (conta.codigo, conta.localidade)
        if chave in manter and chave not in vistos:
            vistos.add(chave)
            resultado.append(conta)
    return resultado


def mascarar_cc(cc: str) -> str:
    """CC para log, sem expor o número inteiro ("123456" → "12xxx6")."""
    digitos = so_digitos(cc)
    if len(digitos) <= 3:
        return "x" * len(digitos)
    return digitos[:2] + "x" * (len(digitos) - 3) + digitos[-1]


def ler_grade_plano_contas(cabecalho: list[str], linhas: list[list[str]]) -> list[ContaSiga]:
    """Lê a grade `#grid1` da CTB00301 localizando as colunas pelo título, não pela posição.

    Args:
        cabecalho: Textos do `thead` ("Cód. Reduzido", "Nome", "Localidade", "Status"...).
        linhas: Textos das células de cada linha do `tbody`.

    Returns:
        Contas bancárias (101 e 103) da grade; lista vazia se faltar coluna essencial.
    """
    titulos = [normalizar_texto(t) for t in cabecalho]

    def coluna(trecho: str) -> int | None:
        return next((i for i, t in enumerate(titulos) if trecho in t), None)

    i_cod, i_nome, i_loc, i_status = coluna("REDUZIDO"), coluna("NOME"), coluna("LOCALIDADE"), coluna("STATUS")
    if i_cod is None or i_nome is None or i_loc is None:
        return []

    contas = []
    for linha in linhas:
        if len(linha) <= max(i_cod, i_nome, i_loc):
            continue  # linha "Nenhum registro encontrado" tem uma célula só
        status = linha[i_status] if i_status is not None and i_status < len(linha) else ""
        conta = ler_linha_plano_contas(linha[i_cod], linha[i_nome], linha[i_loc], status)
        if conta:
            contas.append(conta)
    return contas
