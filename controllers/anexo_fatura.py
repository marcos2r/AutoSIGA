"""
Preparação do Anexo da Fatura de Energia.

Antes de anexar o PDF no SIGA, gera uma cópia com um nome que identifica o lançamento:
conta contábil de despesa + centro de custo (código e nome da localidade).
Ex.: "3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf"
"""

import os
import re
import shutil
import unicodedata

# Conta contábil de despesa usada no rateio das faturas de energia
CONTA_DESPESA_ENERGIA = "3006"
DESCRICAO_DESPESA_ENERGIA = "ENERGIA ELETRICA"

# Caracteres proibidos em nomes de arquivo no Windows
_CARACTERES_INVALIDOS = re.compile(r'[\\/:*?"<>|]')


def _limpar(texto: str) -> str:
    """Remove acentos, caracteres inválidos e espaços repetidos de um trecho do nome."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")
    sem_invalidos = _CARACTERES_INVALIDOS.sub(" ", sem_acento)
    return " ".join(sem_invalidos.split()).upper()


def nome_anexo(localidade_codigo: str, localidade_nome: str) -> str:
    """
    Monta o nome do PDF anexado no SIGA.

    Os acentos são removidos para evitar nomes corrompidos no upload/download do SIGA.

    Args:
        localidade_codigo (str): Código do centro de custo (ex: "BR 10-0516").
        localidade_nome (str): Nome da localidade (ex: "ADM DOURADOS").

    Returns:
        str: Nome do arquivo, ex: "3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf".
    """
    partes = [CONTA_DESPESA_ENERGIA, DESCRICAO_DESPESA_ENERGIA]
    codigo = _limpar(localidade_codigo)
    nome = _limpar(localidade_nome)
    if codigo:
        partes.append(codigo)
    if nome and nome != codigo:
        partes.append(nome)
    return " - ".join(partes) + ".pdf"


def preparar_anexo(caminho_pdf: str, localidade_codigo: str, localidade_nome: str, pasta_destino: str) -> str:
    """
    Copia o PDF da fatura para a pasta de anexos com o nome do lançamento.

    O PDF original (UC_REFERENCIA.pdf) é preservado, pois identifica a fatura
    nas pendências e na pasta organizada.

    Args:
        caminho_pdf (str): PDF original da fatura.
        localidade_codigo (str): Código do centro de custo.
        localidade_nome (str): Nome da localidade.
        pasta_destino (str): Pasta onde a cópia renomeada é criada.

    Returns:
        str: Caminho da cópia renomeada, pronta para o upload.
    """
    os.makedirs(pasta_destino, exist_ok=True)
    destino = os.path.join(pasta_destino, nome_anexo(localidade_codigo, localidade_nome))
    shutil.copy2(caminho_pdf, destino)
    return destino
