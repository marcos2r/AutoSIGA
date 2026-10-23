"""
Módulo de Leitura de Extratos XLS (Model).

Este módulo é responsável por fazer o parsing de planilhas eletrônicas XLS geradas
pelo banco SICREDI contendo os extratos das contas de aplicação financeira.
Utiliza a biblioteca 'xlrd' para ler a estrutura de planilhas antigas (BIFF8).
"""

import calendar
import logging
import os
import re
from typing import Any

import xlrd

# Número de conta Sicredi (ex.: "12345-6"), usado quando o rótulo da conta não é achado
_RE_CONTA = re.compile(r"\d{4,6}-\d")
# Mês/ano do período ("Dados referentes ao período 05/2026 a 05/2026.")
_RE_MES_ANO = re.compile(r"(\d{2})/(\d{4})")
# Data de lançamento; linhas sem ela (resumos e posições abaixo da tabela) são ignoradas
_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")

_MSG_CAPITAL_SOCIAL = "Extrato de Capital Social ainda não é suportado. Retire este arquivo do lote."
_TOLERANCIA_SALDO = 0.01

# Palavras do histórico que indicam o sentido do movimento quando não há coluna de saldo
_HISTORICOS_APLICACAO = ("APLICA", "DEPOSITO", "CRED")
_HISTORICOS_RESGATE = ("RESGAT", "DEB", "IRRF", "IOF")


class ExtratoNaoSuportadoError(ValueError):
    """Planilha reconhecida, mas de um tipo de extrato que o AutoSIGA ainda não processa."""


class XlsReader:
    """
    Responsável por processar arquivos físicos XLS em dicionários padronizados.

    A classe encapsula as rotinas de abertura do arquivo binário OLE do Excel,
    varredura de metadados, identificação inteligente de produtos (Poupança ou CDB)
    e normalização contábil dos lançamentos de rendimento.
    """

    @staticmethod
    def parse_file(caminho: str) -> dict[str, Any]:
        """
        Abre e decodifica a planilha de extrato de aplicação do SICREDI.

        Realiza a leitura de metadados das primeiras linhas para detectar
        a conta bancária e o produto de investimento, mapeando as colunas
        e limpando as strings financeiras padrão Brasil ('1.234,56') para float.

        Args:
            caminho (str): Caminho físico absoluto ou relativo do arquivo XLS.

        Returns:
            dict: Dicionário contendo os metadados do extrato, os saldos e as listas
                  de movimentos. Estrutura de retorno:
                  {
                      "banco": "748",
                      "conta_id": str,
                      "tipo_extrato": "APLICACAO",
                      "produto": str (ex: "SICREDINVEST AUTOMATICO" ou "POUPANCA TRADICIONAL"),
                      "data_inicial": str (DD/MM/YYYY) ou None,
                      "data_final": str (DD/MM/YYYY) ou None,
                      "saldo_anterior": float ou None,
                      "saldo_atual": float ou None,
                      "data_saldo": str (DD/MM/YYYY) ou None,
                      "movimentos": [  # todas as linhas, para a prova real
                          {"data": str, "tipo": "APLICACAO"|"RESGATE"|"RENDIMENTO", "valor": float},
                          ...
                      ],
                      "transacoes": [  # só os rendimentos, que o bot lança
                          {"data": str, "valor": float, "descricao": str, "documento": str},
                          ...
                      ]
                  }
                  Os saldos ficam None quando faltam no arquivo ou quando
                  `anterior - resgates + aplicações + rendimentos` não fecha com o atual.

        Raises:
            FileNotFoundError: Se o arquivo não existir.
            ExtratoNaoSuportadoError: Se for um extrato de Capital Social.
            ValueError: Se o arquivo não for compatível com os formatos Sicredi suportados.
        """
        if not os.path.exists(caminho):
            raise FileNotFoundError(f"O arquivo {caminho} não foi encontrado no disco.")

        try:
            workbook = xlrd.open_workbook(caminho)
        except Exception as e:
            raise ValueError(f"O arquivo não pôde ser aberto como planilha Excel (XLS/XLSX) válida. Erro: {e}") from e

        # O extrato do Sicredi gera os dados sempre na primeira aba (normalmente chamada 'Relatorio')
        nomes_abas = workbook.sheet_names()
        if not nomes_abas:
            raise ValueError("A planilha de extrato carregada não contém abas ativas.")
        if any("CAPITAL SOCIAL" in nome.upper() for nome in nomes_abas):
            raise ExtratoNaoSuportadoError(_MSG_CAPITAL_SOCIAL)

        sheet = workbook.sheet_by_index(0)
        if sheet.nrows < 5:
            raise ValueError("A planilha carregada contém poucas linhas para ser um extrato Sicredi válido.")

        max_metadados = min(12, sheet.nrows)
        conta_id, produto, dados_periodo = XlsReader._ler_metadados(sheet, max_metadados)
        colunas = XlsReader._localizar_colunas(sheet)
        movimentos, transacoes, saldo_anterior, saldo_atual, data_saldo = XlsReader._ler_movimentos(
            sheet, colunas, produto
        )

        if not XlsReader._saldos_fecham(saldo_anterior, saldo_atual, movimentos, caminho):
            saldo_anterior = saldo_atual = None

        data_in, data_fi = XlsReader._periodo(dados_periodo, data_saldo, transacoes)

        return {
            "banco": "748",  # Sicredi
            "conta_id": conta_id,
            "tipo_extrato": "APLICACAO",
            "produto": produto,
            "data_inicial": data_in,
            "data_final": data_fi,
            "saldo_anterior": saldo_anterior,
            "saldo_atual": saldo_atual,
            "data_saldo": data_saldo,
            "movimentos": movimentos,
            "transacoes": transacoes,
        }

    @staticmethod
    def _valor_ao_lado(sheet: Any, r: int, c: int) -> str:
        """Devolve a primeira célula preenchida à direita de (r, c), ou "" se não houver."""
        for cx in range(c + 1, sheet.ncols):
            val = str(sheet.cell_value(r, cx)).strip()
            if val:
                return val
        return ""

    @staticmethod
    def _ler_metadados(sheet: Any, max_metadados: int) -> tuple[str, str, str]:
        """
        Varre o cabeçalho da planilha atrás da conta, do produto e do período.

        Args:
            sheet: Aba do xlrd com o extrato.
            max_metadados (int): Quantas linhas do topo examinar.

        Returns:
            tuple[str, str, str]: (conta_id, produto, texto do período).

        Raises:
            ExtratoNaoSuportadoError: Se o título indicar extrato de Capital Social.
            ValueError: Se a conta não for encontrada.
        """
        conta_id = ""
        produto = ""
        dados_periodo = ""

        for r in range(max_metadados):
            for c in range(sheet.ncols):
                val = str(sheet.cell_value(r, c)).strip()

                if "Extrato Capital Social" in val:
                    raise ExtratoNaoSuportadoError(_MSG_CAPITAL_SOCIAL)

                # O rótulo da conta varia ("Conta Corrente:", "Conta Poupança:") e, conforme
                # o produto, o valor fica uma ou duas colunas à direita.
                if val.startswith("Conta Corrente:") or val.startswith("Conta Poupan"):
                    conta_id = XlsReader._valor_ao_lado(sheet, r, c) or conta_id

                if val.startswith("Produto:"):
                    produto = XlsReader._valor_ao_lado(sheet, r, c) or produto
                elif "Extrato de Aplica" in val and not produto:
                    # Identifica se é poupança ou CDB simplificado
                    if "Poupan" in val:
                        produto = "POUPANCA TRADICIONAL"
                    elif "Simplificado" in val or "Dep" in val:
                        produto = "SICREDINVEST AUTOMATICO"

                if "referentes ao per" in val:
                    dados_periodo = val

        # Sem o rótulo, procura um número no formato de conta Sicredi fora da primeira coluna
        if not conta_id:
            for r in range(max_metadados):
                for c in range(1, sheet.ncols):
                    achado = _RE_CONTA.search(str(sheet.cell_value(r, c)))
                    if achado:
                        conta_id = achado.group()
                        break
                if conta_id:
                    break
            if not conta_id:
                raise ValueError("Não foi possível identificar o número da Conta no arquivo XLS.")

        if not produto:
            # Fallback lógico baseado em padrões do cabeçalho
            content_str = " ".join(
                str(sheet.cell_value(r, cx)) for r in range(max_metadados) for cx in range(sheet.ncols)
            )
            produto = "POUPANCA TRADICIONAL" if "POUPANCA" in content_str.upper() else "SICREDINVEST AUTOMATICO"

        return conta_id, produto, dados_periodo

    @staticmethod
    def _localizar_colunas(sheet: Any) -> dict[str, int]:
        """
        Acha a linha de títulos da tabela e os índices das colunas.

        Returns:
            dict[str, int]: Índices de "linha", "data", "historico", "valor" e "saldo"
            (este último -1 quando a planilha não tem coluna de saldo).

        Raises:
            ValueError: Se a tabela ou as colunas essenciais não forem encontradas.
        """
        linha_cabecalho = -1
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                val = str(sheet.cell_value(r, c)).strip().upper()
                if "DATA" in val and "HIST" in val or "VALOR" in val:
                    linha_cabecalho = r
                    break
            if linha_cabecalho != -1:
                break

        if linha_cabecalho == -1:
            raise ValueError("Não foi possível localizar as colunas de movimentação ('Data', 'Histórico') no XLS.")

        colunas = {"linha": linha_cabecalho, "data": -1, "historico": -1, "valor": -1, "saldo": -1}
        for c in range(sheet.ncols):
            val = str(sheet.cell_value(linha_cabecalho, c)).strip().upper()
            if "DATA" in val:
                colunas["data"] = c
            elif "HIST" in val:
                colunas["historico"] = c
            elif "VALOR" in val:
                colunas["valor"] = c
            elif val.startswith("SALDO"):
                colunas["saldo"] = c

        if colunas["data"] == -1 or colunas["historico"] == -1 or colunas["valor"] == -1:
            raise ValueError("As colunas essenciais ('Data', 'Histórico', 'Valor') não foram identificadas corretamente.")
        return colunas

    @staticmethod
    def _texto_data(sheet: Any, r: int, c: int) -> str:
        """Lê a data da célula como DD/MM/AAAA, seja texto ou data nativa do Excel."""
        cell = sheet.cell(r, c)
        if cell.ctype == xlrd.XL_CELL_DATE:
            return xlrd.xldate_as_datetime(cell.value, sheet.book.datemode).strftime("%d/%m/%Y")
        return str(cell.value).strip()

    @staticmethod
    def _valor_float(sheet: Any, r: int, c: int) -> float:
        """
        Converte a célula de valor em float.

        O valor pode vir como número nativo do Excel ou como texto brasileiro ('1.234,56').

        Raises:
            ValueError: Se o texto não for um número.
        """
        cell = sheet.cell(r, c)
        if cell.ctype == xlrd.XL_CELL_NUMBER:
            return float(cell.value)
        return float(str(cell.value).replace(".", "").replace(",", ".").strip())

    @staticmethod
    def _ler_movimentos(
        sheet: Any, colunas: dict[str, int], produto: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None, float | None, str | None]:
        """
        Percorre a tabela de movimentação classificando cada linha.

        O sentido de cada movimento vem, nesta ordem: das palavras de rendimento do
        produto; da variação da coluna de saldo (poupança); das palavras do histórico.

        Returns:
            tuple: (movimentos, transacoes de rendimento, saldo anterior, saldo atual,
            data do saldo atual).
        """
        if "POUPANCA" in produto.upper():
            historicos_rendimento = ["CAPITALIZ. REND. JR", "CAPITALIZ. REND. CM", "CAPITALIZ. REND."]
        else:
            # Sicredinvest ou fundos CDI
            historicos_rendimento = ["RENDIMENTOS", "CRED REND", "JUROS"]

        idx_data, idx_hist = colunas["data"], colunas["historico"]
        idx_valor, idx_saldo = colunas["valor"], colunas["saldo"]

        movimentos: list[dict[str, Any]] = []
        transacoes: list[dict[str, Any]] = []
        saldo_anterior: float | None = None
        saldo_atual: float | None = None
        data_saldo: str | None = None
        saldo_corrente: float | None = None  # coluna Saldo da linha anterior, quando existe

        for r in range(colunas["linha"] + 1, sheet.nrows):
            data_val = XlsReader._texto_data(sheet, r, idx_data)
            hist_val = str(sheet.cell_value(r, idx_hist)).strip()
            hist_upper = hist_val.upper()
            if not _RE_DATA.match(data_val) or not hist_val or "TOTAL" in hist_upper:
                continue

            try:
                valor_float = abs(XlsReader._valor_float(sheet, r, idx_valor))
            except ValueError as e:
                logging.error(f"Erro ao converter linha {r} do XLS (Valor: {sheet.cell_value(r, idx_valor)}): {e}")
                continue

            saldo_linha: float | None = None
            if idx_saldo != -1:
                try:
                    saldo_linha = XlsReader._valor_float(sheet, r, idx_saldo)
                except ValueError:
                    saldo_linha = None

            if "SALDO ANTERIOR" in hist_upper:
                saldo_anterior = valor_float
                saldo_corrente = saldo_linha if saldo_linha is not None else valor_float
                continue
            if "SALDO ATUAL" in hist_upper:
                saldo_atual = saldo_linha if saldo_linha is not None else valor_float
                data_saldo = data_val
                continue

            tipo: str | None
            if any(k in hist_upper for k in historicos_rendimento):
                tipo = "RENDIMENTO"
            elif saldo_linha is not None and saldo_corrente is not None:
                tipo = "RESGATE" if saldo_linha < saldo_corrente else "APLICACAO"
            elif any(k in hist_upper for k in _HISTORICOS_RESGATE):
                tipo = "RESGATE"
            elif any(k in hist_upper for k in _HISTORICOS_APLICACAO):
                tipo = "APLICACAO"
            else:
                tipo = None
            if saldo_linha is not None:
                saldo_corrente = saldo_linha

            if tipo is None:
                # Sem sentido conhecido o movimento fica fora; a autoverificação dos saldos acusa a falta.
                logging.warning(f"Linha {r} do XLS com histórico desconhecido ignorada: {hist_val}")
                continue

            movimentos.append({"data": data_val, "tipo": tipo, "valor": valor_float})
            if tipo == "RENDIMENTO":
                transacoes.append({
                    "data": data_val,
                    "valor": valor_float,
                    "descricao": hist_val,
                    "documento": "0",  # Extratos de aplicação XLS do Sicredi não possuem número de documento
                })

        return movimentos, transacoes, saldo_anterior, saldo_atual, data_saldo

    @staticmethod
    def _saldos_fecham(
        saldo_anterior: float | None, saldo_atual: float | None, movimentos: list[dict[str, Any]], caminho: str
    ) -> bool:
        """
        Confere se `anterior - resgates + aplicações + rendimentos` dá o saldo atual.

        Returns:
            bool: True se os dois saldos existem e fecham dentro da tolerância de 1 centavo.
        """
        if saldo_anterior is None or saldo_atual is None:
            return False
        calculado = saldo_anterior
        for mov in movimentos:
            calculado += -mov["valor"] if mov["tipo"] == "RESGATE" else mov["valor"]
        if abs(calculado - saldo_atual) > _TOLERANCIA_SALDO:
            logging.warning(
                f"Saldos do XLS não fecham em {os.path.basename(caminho)}: calculado {calculado:.2f}, "
                f"informado {saldo_atual:.2f}. A conferência de saldo fica dispensada para este arquivo."
            )
            return False
        return True

    @staticmethod
    def _periodo(
        dados_periodo: str, data_saldo: str | None, transacoes: list[dict[str, Any]]
    ) -> tuple[str | None, str | None]:
        """
        Calcula as datas inicial e final do extrato.

        A data final é a do "Saldo Atual" quando existe; senão, o último dia real
        do mês final do período. Sem período, usa as datas dos rendimentos.

        Returns:
            tuple[str | None, str | None]: (data inicial, data final) em DD/MM/AAAA.
        """
        data_in: str | None = None
        data_fi: str | None = None
        meses_anos = _RE_MES_ANO.findall(dados_periodo)
        if len(meses_anos) >= 2:
            mes_in, ano_in = meses_anos[0]
            mes_fi, ano_fi = meses_anos[1]
            data_in = f"01/{mes_in}/{ano_in}"
            ultimo_dia = calendar.monthrange(int(ano_fi), int(mes_fi))[1]
            data_fi = f"{ultimo_dia:02d}/{mes_fi}/{ano_fi}"
        if data_saldo:
            data_fi = data_saldo

        if transacoes:
            datas_ordenadas = sorted(
                transacoes,
                key=lambda tx: tuple(map(int, reversed(tx["data"].split("/")))) if "/" in tx["data"] else tx["data"],
            )
            if not data_in:
                data_in = datas_ordenadas[0]["data"]
            if not data_fi:
                data_fi = datas_ordenadas[-1]["data"]

        return data_in, data_fi
