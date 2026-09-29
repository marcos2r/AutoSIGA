"""
Módulo de Leitura de OFX (Model).

Este módulo é responsável por fazer o parsing de arquivos com a extensão .ofx,
comumente gerados por bancos contendo o extrato bancário financeiro.
Utiliza a biblioteca 'ofxparse' para traduzir o XML contido no OFX em objetos Python.
"""

from ofxparse import OfxParser

class OfxReader:
    """
    Responsável por processar arquivos físicos OFX em dicionários padronizados.
    
    A classe encapsula o acesso à biblioteca 'ofxparse', abstraindo seus objetos
    específicos em dicionários nativos do Python que são mais fáceis de serem
    consumidos pela View e Controllers.
    """
    
    @staticmethod
    def parse_file(caminho):
        """
        Lê um arquivo OFX e extrai dados e transações para um formato estruturado.
        
        Args:
            caminho (str): Caminho absoluto ou relativo para o arquivo .ofx.
            
        Returns:
            dict: Dicionário padronizado com os metadados da conta e a lista de 
                  transações financeiras. Estrutura de retorno:
                  {
                      "banco": str,
                      "conta_id": str,
                      "moeda": str,
                      "saldo_atual": float,
                      "data_inicial": str (DD/MM/YYYY),
                      "data_final": str (DD/MM/YYYY),
                      "transacoes": [
                          {
                              "id": str,
                              "data": str (DD/MM/YYYY),
                              "valor": float,
                              "tipo": str,
                              "descricao": str
                          },
                          ...
                      ]
                  }
            
        Raises:
            Exception: Se o arquivo não existir, não tiver permissão de leitura,
                       ou contiver sintaxe OFX inválida.
        """
        # Abre em modo binário ('rb') porque a biblioteca ofxparse espera bytes, 
        # para lidar de forma nativa com as quebras de linha e encodes do XML bancário.
        try:
            with open(caminho, 'rb') as f:
                ofx = OfxParser.parse(f)
        except Exception as e:
            raise ValueError(f"O arquivo não é um extrato OFX válido ou está corrompido. Detalhe: {e}")
        
        if not ofx or not hasattr(ofx, 'account') or not ofx.account:
            raise ValueError("O extrato OFX não contém dados de conta válidos.")
            
        conta = ofx.account
        extrato = conta.statement
        if not extrato:
            raise ValueError("O extrato OFX não contém bloco de movimentações financeiras.")
        
        # Consolida os cabeçalhos (metadados gerais da conta) em um dicionário simples
        dados_ofx = {
            "banco": getattr(conta, 'routing_number', ''),
            "conta_id": getattr(conta, 'account_id', ''),
            "moeda": getattr(extrato, 'currency', ''),
            "saldo_atual": float(extrato.balance) if hasattr(extrato, 'balance') else 0.0,
            "data_inicial": extrato.start_date.strftime("%d/%m/%Y") if hasattr(extrato, 'start_date') and extrato.start_date else None,
            "data_final": extrato.end_date.strftime("%d/%m/%Y") if hasattr(extrato, 'end_date') and extrato.end_date else None,
            "transacoes": []
        }
        
        # Converte as transações encapsuladas em objetos ofxtransaction para dicionários
        for tx in extrato.transactions:
            memo = (getattr(tx, 'memo', '') or '').strip()
            nome = (getattr(tx, 'payee', '') or '').strip()
            descricao = memo or nome

            dados_ofx["transacoes"].append({
                "id": getattr(tx, 'id', ''),
                "data": tx.date.strftime("%d/%m/%Y") if tx.date else '',
                "valor": float(tx.amount) if tx.amount else 0.0,
                "tipo": getattr(tx, 'type', ''),
                # 'descricao' guarda só o MEMO (tipo da operação) e é a base dos
                # filtros de palavras-chave; nomes de pessoas não podem influenciá-los.
                "descricao": descricao,
                # 'historico' é o texto exibido e exportado. Bancos como o Sicoob
                # enviam um MEMO genérico ("PIX RECEBIDO - OUTRA IF") e o nome do
                # pagador na tag NAME, então ela é anexada quando traz informação nova.
                "historico": OfxReader._montar_historico(descricao, nome)
            })

        return dados_ofx

    @staticmethod
    def _montar_historico(descricao: str, nome: str) -> str:
        """
        Combina o MEMO e o NAME de uma transação em um único histórico legível.

        Args:
            descricao (str): Texto principal da transação (MEMO, ou NAME na ausência dele).
            nome (str): Conteúdo da tag NAME (pagador/favorecido), podendo ser vazio.

        Returns:
            str: "MEMO - NAME" quando o NAME acrescenta informação; caso contrário, só o MEMO.
        """
        if not nome or nome.upper() in descricao.upper():
            return descricao
        return f"{descricao} - {nome}"
