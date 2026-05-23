"""
Módulo de Leitura de Extratos XLS (Model).

Este módulo é responsável por fazer o parsing de planilhas eletrônicas XLS geradas
pelo banco SICREDI contendo os extratos das contas de aplicação financeira.
Utiliza a biblioteca 'xlrd' para ler a estrutura de planilhas antigas (BIFF8).
"""

import os
import xlrd
import logging
from typing import Dict, Any, List

class XlsReader:
    """
    Responsável por processar arquivos físicos XLS em dicionários padronizados.
    
    A classe encapsula as rotinas de abertura do arquivo binário OLE do Excel,
    varredura de metadados, identificação inteligente de produtos (Poupança ou CDB)
    e normalização contábil dos lançamentos de rendimento.
    """
    
    @staticmethod
    def parse_file(caminho: str) -> Dict[str, Any]:
        """
        Abre e decodifica a planilha de extrato de aplicação do SICREDI.
        
        Realiza a leitura de metadados das primeiras linhas para detectar
        a conta bancária e o produto de investimento, mapeando as colunas
        e limpando as strings financeiras padrão Brasil ('1.234,56') para float.
        
        Args:
            caminho (str): Caminho físico absoluto ou relativo do arquivo XLS.
            
        Returns:
            dict: Dicionário contendo os metadados do extrato e a lista de transações
                  filtrada exclusivamente para lançamentos de rendimento.
                  Estrutura de retorno:
                  {
                      "banco": "748",
                      "conta_id": str,
                      "tipo_extrato": "APLICACAO",
                      "produto": str (ex: "SICREDINVEST AUTOMATICO" ou "POUPANCA TRADICIONAL"),
                      "data_inicial": str (DD/MM/YYYY) ou None,
                      "data_final": str (DD/MM/YYYY) ou None,
                      "transacoes": [
                          {
                              "data": str (DD/MM/YYYY),
                              "valor": float,
                              "descricao": str,
                              "documento": str
                          },
                          ...
                      ]
                  }
                  
        Raises:
            FileNotFoundError: Se o arquivo não existir.
            ValueError: Se o arquivo não for compatível com os formatos Sicredi suportados.
            Exception: Se ocorrer erro na abertura da estrutura do Excel.
        """
        if not os.path.exists(caminho):
            raise FileNotFoundError(f"O arquivo {caminho} não foi encontrado no disco.")
            
        try:
            workbook = xlrd.open_workbook(caminho)
        except Exception as e:
            raise IOError(f"Falha ao abrir a planilha Excel. Verifique se o arquivo está corrompido: {e}")
            
        # O extrato do Sicredi gera os dados sempre na primeira aba (normalmente chamada 'Relatorio')
        if not workbook.sheet_names():
            raise ValueError("O arquivo de extrato não contém nenhuma planilha ativa.")
            
        sheet = workbook.sheet_by_index(0)
        
        # 1. Varredura Inicial de Metadados (Cabeçalho da Planilha)
        conta_id = ""
        produto = ""
        dados_periodo = ""
        
        # Lemos as primeiras 12 linhas em busca das informações essenciais da conta e do produto
        max_metadados = min(12, sheet.nrows)
        for r in range(max_metadados):
            for c in range(sheet.ncols):
                val = str(sheet.cell_value(r, c)).strip()
                
                # Captura do número da conta bancária
                if "Conta Corrente:" in val or "Conta Poupança:" in val:
                    # O valor geralmente está na coluna ao lado
                    if c + 1 < sheet.ncols:
                        conta_id = str(sheet.cell_value(r, c + 1)).strip()
                elif "Conta Poupana:" in val:  # Trata caracteres quebrados na decodificação
                    if c + 1 < sheet.ncols:
                        conta_id = str(sheet.cell_value(r, c + 1)).strip()
                        
                # Captura de qual produto financeiro se trata
                if "Produto:" in val:
                    if c + 1 < sheet.ncols:
                        produto = str(sheet.cell_value(r, c + 1)).strip()
                elif "Extrato de Aplica" in val:
                    # Identifica se é poupança ou CDB simplificado
                    if "Poupan" in val:
                        produto = "POUPANCA TRADICIONAL"
                    elif "Simplificado" in val or "Dep" in val:
                        produto = "SICREDINVEST AUTOMATICO"
                        
                # Captura de qual período se referem as informações
                if "referentes ao per" in val:
                    dados_periodo = val
                    
        # Se não encontrou o número da conta, levanta erro rápido (Fail Fast)
        if not conta_id:
            # Varre novamente procurando de forma genérica
            for r in range(max_metadados):
                for c in range(sheet.ncols):
                    val = str(sheet.cell_value(r, c)).strip()
                    if "58308-2" in val or "-" in val and len(val) >= 5 and c > 0:
                        # Tenta extrair a conta do Sicredi
                        conta_id = val
                        break
            if not conta_id:
                raise ValueError("Não foi possível identificar o número da Conta no arquivo XLS.")
                
        # Garante nome do produto se não achou explícito
        if not produto:
            # Fallback lógico baseado em padrões do cabeçalho
            content_str = ""
            for r in range(max_metadados):
                content_str += " ".join([str(sheet.cell_value(r, cx)) for cx in range(sheet.ncols)])
            if "POUPANCA" in content_str.upper():
                produto = "POUPANCA TRADICIONAL"
            else:
                produto = "SICREDINVEST AUTOMATICO"
                
        # 2. Localização do Cabeçalho de Dados
        linha_cabecalho = -1
        idx_data = -1
        idx_historico = -1
        idx_valor = -1
        
        # Procuramos a linha que inicia a tabela de movimentações contendo 'Data', 'Histórico' e 'Valor'
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                val = str(sheet.cell_value(r, c)).strip().upper()
                if "DATA" in val and "HIST" in val or "VALOR" in val:
                    # Encontramos a linha de colunas
                    linha_cabecalho = r
                    break
            if linha_cabecalho != -1:
                break
                
        if linha_cabecalho == -1:
            raise ValueError("Não foi possível localizar as colunas de movimentação ('Data', 'Histórico') no XLS.")
            
        # Mapeamos os índices exatos de cada coluna na linha encontrada
        for c in range(sheet.ncols):
            val = str(sheet.cell_value(linha_cabecalho, c)).strip().upper()
            if "DATA" in val:
                idx_data = c
            elif "HIST" in val:
                idx_historico = c
            elif "VALOR" in val:
                idx_valor = c
                
        if idx_data == -1 or idx_historico == -1 or idx_valor == -1:
            raise ValueError("As colunas essenciais ('Data', 'Histórico', 'Valor') não foram identificadas corretamente.")
            
        # 3. Extração das Transações Financeiras de Rendimento
        transacoes: List[Dict[str, Any]] = []
        
        # Filtros de rendimento suportados por tipo de produto
        if "POUPANCA" in produto.upper():
            historicos_rendimento = ["CAPITALIZ. REND. JR", "CAPITALIZ. REND. CM", "CAPITALIZ. REND."]
        else:
            # Sicredinvest ou fundos CDI
            historicos_rendimento = ["RENDIMENTOS", "CRED REND", "JUROS"]
            
        # Começa a leitura a partir da linha imediatamente posterior ao cabeçalho
        for r in range(linha_cabecalho + 1, sheet.nrows):
            # Condição de parada: se encontrar células vazias na coluna da data ou histórico,
            # ou se encontrar a linha de 'Total', interrompe a leitura da tabela.
            data_val = str(sheet.cell_value(r, idx_data)).strip()
            hist_val = str(sheet.cell_value(r, idx_historico)).strip()
            valor_val = str(sheet.cell_value(r, idx_valor)).strip()
            
            if not data_val or not hist_val or "TOTAL" in hist_val.upper() or "SALDO ATUAL" in hist_val.upper():
                continue
                
            # Verifica se o lançamento representa um Rendimento financeiro de fato
            hist_upper = hist_val.upper()
            e_rendimento = any(k in hist_upper for k in historicos_rendimento)
            if not e_rendimento:
                continue
                
            try:
                # O valor no XLS pode vir como número nativo do Excel (float) ou texto formatado brasileiro ('78,41')
                raw_cell = sheet.cell(r, idx_valor)
                if raw_cell.ctype == xlrd.XL_CELL_NUMBER:
                    valor_float = float(raw_cell.value)
                else:
                    # Sanitiza texto: remove separadores de milhar (ponto) e substitui vírgula por ponto
                    valor_limpo = valor_val.replace(".", "").replace(",", ".").strip()
                    valor_float = float(valor_limpo)
                    
                # Rendimentos são sempre entradas positivas na conta de aplicação
                valor_float = abs(valor_float)
                
                # Insere na lista padronizada
                transacoes.append({
                    "data": data_val,
                    "valor": valor_float,
                    "descricao": hist_val,
                    "documento": "0"  # Extratos de aplicação XLS do Sicredi não possuem número de documento
                })
            except Exception as e:
                logging.error(f"Erro ao converter linha {r} do XLS (Valor: {valor_val}): {e}")
                
        # Parse básico das datas limites
        data_in = None
        data_fi = None
        # Tenta inferir o período a partir da string de dados "período 05/2026 a 05/2026"
        if dados_periodo:
            # Geralmente no formato "Dados referentes ao período MM/AAAA a MM/AAAA"
            partes = dados_periodo.split()
            # Busca strings que representem o mês/ano limpando pontos ou vírgulas colados
            meses_anos = [p.replace(".", "").replace(",", "").strip() for p in partes if "/" in p]
            if len(meses_anos) >= 2:
                # Tenta fixar os extremos
                data_in = f"01/{meses_anos[0]}"
                # Para a data final, colocamos no final do mês. Como é apenas para o login do SIGA,
                # usar '30/MM/AAAA' ou '31/MM/AAAA' resolve o calendário.
                data_fi = f"30/{meses_anos[1]}"
                
        # Se tiver transações, podemos pegar as datas reais delas para maior precisão
        if transacoes:
            datas_ordenadas = sorted(transacoes, key=lambda tx: tuple(map(int, reversed(tx["data"].split("/")))) if "/" in tx["data"] else tx["data"])
            if not data_in:
                data_in = datas_ordenadas[0]["data"]
            if not data_fi:
                data_fi = datas_ordenadas[-1]["data"]
                
        return {
            "banco": "748",  # Sicredi
            "conta_id": conta_id,
            "tipo_extrato": "APLICACAO",
            "produto": produto,
            "data_inicial": data_in,
            "data_final": data_fi,
            "transacoes": transacoes
        }
