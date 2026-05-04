import logging

class Conciliador:
    """Responsável por comparar transações do banco com o sistema e identificar divergências."""
    
    @staticmethod
    def conciliar(ofx_txs, siga_txs_raw):
        """Cruza os dados do Banco (.OFX) com os dados Web (SIGA) para encontrar pendências.
        
        Executa uma checagem reversa bidirecional, avaliando entradas positivas
        e saídas negativas, comparando as datas e tolerando diferenças de ponto
        flutuante de até 1 centavo.
        
        Args:
            ofx_txs (list): Lista de transações limpas do OFX.
            siga_txs_raw (list): Lista de transações em formato bruto lidas da tabela HTML do SIGA.
            
        Returns:
            list[dict]: Array contendo as transações exclusivas do banco
            que não foram validadas no extrato atual do SIGA.
        """
        # Se um dos dois for vazio, não tem o que conciliar diretamente (ou tudo é pendente, ou nada)
        # O comportamento original era retornar [] se não tivesse extrato siga.
        # Vamos manter a proteção básica, mas na prática a chamadora deve garantir listas.
        if not ofx_txs:
            return []
            
        if not siga_txs_raw:
            siga_txs_raw = []
            
        siga_txs = []
        for entry in siga_txs_raw:
            ent_str = entry.get('entrada', '').strip()
            sai_str = entry.get('saida', '').strip()
            
            # Limpa marcadores nulos do HTML manual ou preenchido
            if ent_str in ['-', '', '0,00', '0.00']: ent_str = None
            if sai_str in ['-', '', '0,00', '0.00']: sai_str = None
            
            is_saida = False
            val_str = None
            
            if ent_str:
                val_str = ent_str
            elif sai_str:
                val_str = sai_str
                is_saida = True
                
            if not val_str:
                continue
                
            try:
                # Transforma 3.000,00 ou -150,00 em float
                val_str_limpo = val_str.replace('.', '').replace(',', '.')
                # Adiciona prevenção extra caso SIGA apresente números negativos nativamente na string
                val_float = abs(float(val_str_limpo))
                
                if is_saida:
                    val_float = -val_float
                    
                siga_txs.append({
                    'data': entry.get('data', '').strip(),
                    'valor': val_float,
                    'matched': False
                })
            except Exception as e:
                logging.error(f"Erro ao converter valor do SIGA: {val_str} - {e}")
                
        # Procura quais itens do OFX não existem no SIGA
        a_lancar = []
        
        # Filtro: nesta primeira versão, consideramos apenas transações de investimento/resgate
        kw_investimentos = ['APLIC', 'RESG', 'RDC', 'CDB', 'POUP', 'INVEST']
        
        for tx in ofx_txs:
            tx_data = tx.get("data", "")
            tx_valor = tx.get("valor", 0.0)
            tx_desc = tx.get("descricao", "").upper()
            
            # Checa se a transação é de aplicação/resgate
            eh_investimento = any(kw in tx_desc for kw in kw_investimentos)
            if not eh_investimento:
                continue # Ignora transferências, PIX e depósitos comuns
            
            matched = False
            for stx in siga_txs:
                if not stx['matched'] and stx['data'] == tx_data:
                    # Tolerância de 1 centavo para problemas de float
                    if abs(stx['valor'] - tx_valor) <= 0.01:
                        stx['matched'] = True
                        matched = True
                        break
            
            if not matched: # Não achou correspondência no SIGA
                a_lancar.append(tx)
                
        return a_lancar
