"""
Módulo de Exportação Contábil (Controller).

Este módulo contém as regras de formatação e expurgo necessárias para
gerar o arquivo CSV customizado (que leva extensão .txt) de Ofertas,
permitindo a importação manual em lote no sistema legado do SIGA.
"""

import logging

class Exportador:
    """
    Responsável por processar e exportar transações bancárias para formato texto.
    
    Ele filtra as transações não pertinentes a Ofertas de igrejas (ex: Saques,
    Rendimentos, etc.) e formata os números no padrão brasileiro exigido pelo
    importador ASP do SIGA.
    """
    
    @staticmethod
    def gerar_txt_ofertas(transacoes, filepath):
        """
        Compilador léxico em conformidade com as regras IT.TES.05.
        
        Realiza a leitura da lista nativa de transações OFX carregada, itera
        sobre as descrições e expurga registros indesejados usando uma 
        cartilha de Blacklist.
        
        Args:
            transacoes (list): Lista de dicionários contendo transações do OFX.
            filepath (str): Caminho físico absoluto onde o arquivo TXT será salvo.
            
        Returns:
            tuple: Uma tupla contendo 3 elementos:
                   - sucesso (bool): True se gerou arquivo, False se não sobrou dados.
                   - linhas_validas (int): Quantidade de ofertas mantidas no arquivo.
                   - qtd_descartadas (int): Quantidade de transações ignoradas.
            
        Raises:
            Exception: Caso ocorra problema de I/O na gravação do disco ou falta
                       de permissão na pasta de destino escolhida.
        """
        # Proteção contra lista vazia ou nula
        if not transacoes:
            return False, 0, 0

        # Palavras bloqueadas que categorizam lançamentos que NÃO são Ofertas puras.
        # Por exemplo: Rendimentos de aplicação, saques aplicados e dinheiro em 
        # caixa já lançado direto (depositos ou congregação).
        palavras_bloqueadas = ["APLICA", "RESGATE", "RENDIMENT", "DEPOSITO", "RESG.", "DEP ", "CONGREGACAO"]

        linhas_limpas = []
        qtd_descartadas = 0

        for tx in transacoes:
            valor = tx.get("valor", 0.0)
            descricao = tx.get("descricao", "").upper()
            data = tx.get("data", "")

            # COND. 1: Somente valores POSITIVOS entram no lançamento puro (sem "-").
            # Valores negativos (débitos) são ignorados pois o SIGA não aceita estornos neste arquivo.
            if valor <= 0:
                qtd_descartadas += 1
                continue
            
            # COND. 2: Nenhuma palavra bloqueada pode fazer parte da descrição da string OFX.
            if any(palavra in descricao for palavra in palavras_bloqueadas):
                qtd_descartadas += 1
                continue

            # FORMATAR VALOR (sem separador de milhar, virgula p/ centavos. ex: 1530,50)
            # O SIGA legado em ASP classic quebra se mandarmos '1.530,50' ou '1530.50'
            valor_fmt = f"{valor:.2f}".replace(".", ",")
            
            # Formato SIGA Csv: DATA;HISTÓRICO;VALOR
            linha = f"{data};{tx.get('descricao', '').strip()};{valor_fmt}"
            linhas_limpas.append(linha)

        if not linhas_limpas:
            return False, 0, qtd_descartadas

        try:
            # Utiliza utf-8 padrão (sem BOM) para evitar que o importador web ASP do SIGA
            # leia a assinatura invisível do arquivo e devolva um erro bizarro na linha 1
            # com os caracteres de controle 'ï»¿'.
            with open(filepath, 'w', encoding='utf-8') as f:
                for l in linhas_limpas:
                    f.write(l + "\n")
            return True, len(linhas_limpas), qtd_descartadas
        except Exception as e:
            logging.error(f"Erro ao salvar arquivo TXT das ofertas: {e}", exc_info=True)
            raise e
