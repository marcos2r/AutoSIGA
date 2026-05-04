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
        with open(caminho, 'rb') as f:
            ofx = OfxParser.parse(f)
        
        conta = ofx.account
        extrato = conta.statement
        
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
            dados_ofx["transacoes"].append({
                "id": getattr(tx, 'id', ''),
                "data": tx.date.strftime("%d/%m/%Y") if tx.date else '',
                "valor": float(tx.amount) if tx.amount else 0.0,
                "tipo": getattr(tx, 'type', ''),
                # Alguns bancos mandam a descrição no 'memo', outros no 'payee'.
                # Essa estrutura garante que não perderemos a descrição.
                "descricao": getattr(tx, 'memo', getattr(tx, 'payee', ''))
            })
            
        return dados_ofx
