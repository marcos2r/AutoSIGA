"""
Módulo de Conciliação Contábil (Controller).

Este módulo contém a lógica de negócio principal do sistema de checagem.
Ele cruza duas matrizes de dados (OFX do Banco x Tabela HTML do SIGA) e
identifica exatamente quais transações estão no banco mas ainda não 
foram lançadas no sistema.
"""

import logging

class Conciliador:
    """
    Responsável por comparar transações financeiras e identificar pendências.
    
    A classe encapsula a lógica pesada de validação, tratamento numérico
    e filtros de palavras-chave, desvinculando essa responsabilidade da interface.
    """
    
    @staticmethod
    def conciliar(ofx_txs, siga_txs_raw):
        """
        Cruza os dados do Banco (.OFX) com os dados Web (SIGA) para encontrar pendências.
        
        Executa uma checagem reversa bidirecional, avaliando entradas positivas
        e saídas negativas. Compara datas (intolerância total) e valores 
        (tolerando diferenças de precisão de ponto flutuante de até 1 centavo).
        
        Apenas transações do OFX que correspondam a Resgates ou Aplicações 
        são avaliadas (filtradas por um dicionário de palavras-chave).
        
        Args:
            ofx_txs (list): Lista de dicionários das transações limpas do OFX.
            siga_txs_raw (list): Lista de dicionários extraídos brutos da 
                                 tabela HTML nativa do portal SIGA.
            
        Returns:
            list: Array contendo dicionários de transações exclusivas do banco
                  que ainda precisam ser injetadas no SIGA.
        """
        # Se o OFX vier vazio, retornamos imediatamente (não há pendências a lançar)
        if not ofx_txs:
            return []
            
        # Proteção básica contra entrada nula vinda do Web Scraper
        if not siga_txs_raw:
            siga_txs_raw = []
            
        # 1. Fase de Normalização e Sanitização dos Dados do SIGA
        siga_txs = []
        for entry in siga_txs_raw:
            ent_str = entry.get('entrada', '').strip()
            sai_str = entry.get('saida', '').strip()
            
            # Limpa marcadores nulos do HTML manual ('-' ou '0,00' significam zerado)
            if ent_str in ['-', '', '0,00', '0.00']: ent_str = None
            if sai_str in ['-', '', '0,00', '0.00']: sai_str = None
            
            is_saida = False
            val_str = None
            
            # Identifica a polaridade da transação (Entrada = +, Saída = -)
            if ent_str:
                val_str = ent_str
            elif sai_str:
                val_str = sai_str
                is_saida = True
                
            # Se não houver valor em ambas as colunas, ignora a linha da tabela
            if not val_str:
                continue
                
            try:
                # Transforma strings brasileiras '3.000,00' ou '-150,00' em float nativo
                val_str_limpo = val_str.replace('.', '').replace(',', '.')
                # abs() previne duplo negativo caso o SIGA já traga o sinal na string de Saída
                val_float = abs(float(val_str_limpo))
                
                if is_saida:
                    val_float = -val_float
                    
                siga_txs.append({
                    'data': entry.get('data', '').strip(),
                    'valor': val_float,
                    'matched': False # Flag para evitar que uma mesma transação invalide duas do OFX
                })
            except Exception as e:
                logging.error(f"Erro ao converter valor numérico do SIGA: {val_str} - {e}")
                
        # 2. Fase de Cruzamento (Conciliação)
        a_lancar = []
        
        # Filtro de negócio: O robô só assume responsabilidade por transferências interbancárias
        # de investimento. Depósitos em espécie e transferências PIX normais são ignorados.
        kw_investimentos = ['APLIC', 'RESG', 'RDC', 'CDB', 'POUP', 'INVEST']
        
        for tx in ofx_txs:
            tx_data = tx.get("data", "")
            tx_valor = tx.get("valor", 0.0)
            tx_desc = tx.get("descricao", "").upper()
            
            # Verifica se a descrição do banco contém alguma das palavras-chave
            eh_investimento = any(kw in tx_desc for kw in kw_investimentos)
            if not eh_investimento:
                continue 
            
            matched = False
            for stx in siga_txs:
                # Procura por uma transação não pareada, no mesmo dia
                if not stx['matched'] and stx['data'] == tx_data:
                    # Tolerância de 1 centavo para atenuar bugs de arredondamento IEEE 754 em floats
                    if abs(stx['valor'] - tx_valor) <= 0.01:
                        stx['matched'] = True
                        matched = True
                        break
            
            # Se terminou a varredura e não encontrou "par" perfeito no SIGA,
            # então esta é uma transação nova que o robô precisará inserir.
            if not matched: 
                a_lancar.append(tx)
                
        return a_lancar
