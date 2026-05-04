from ofxparse import OfxParser

class OfxReader:
    """Responsável por processar arquivos físicos OFX em objetos Python."""
    
    @staticmethod
    def parse_file(caminho):
        """Lê um arquivo OFX e extrai dados e transações para um dicionário estruturado.
        
        Args:
            caminho (str): Caminho absoluto ou relativo para o arquivo .ofx.
            
        Returns:
            dict: Dicionário padronizado com os metadados da conta e a lista de transações.
            
        Raises:
            Exception: Caso ocorra erro de I/O ou parsing da sintaxe OFX.
        """
        with open(caminho, 'rb') as f:
            ofx = OfxParser.parse(f)
        
        conta = ofx.account
        extrato = conta.statement
        
        dados_ofx = {
            "banco": getattr(conta, 'routing_number', ''),
            "conta_id": getattr(conta, 'account_id', ''),
            "moeda": getattr(extrato, 'currency', ''),
            "saldo_atual": float(extrato.balance) if hasattr(extrato, 'balance') else 0.0,
            "data_inicial": extrato.start_date.strftime("%d/%m/%Y") if hasattr(extrato, 'start_date') and extrato.start_date else None,
            "data_final": extrato.end_date.strftime("%d/%m/%Y") if hasattr(extrato, 'end_date') and extrato.end_date else None,
            "transacoes": []
        }
        
        for tx in extrato.transactions:
            dados_ofx["transacoes"].append({
                "id": getattr(tx, 'id', ''),
                "data": tx.date.strftime("%d/%m/%Y") if tx.date else '',
                "valor": float(tx.amount) if tx.amount else 0.0,
                "tipo": getattr(tx, 'type', ''),
                "descricao": getattr(tx, 'memo', getattr(tx, 'payee', ''))
            })
            
        return dados_ofx
