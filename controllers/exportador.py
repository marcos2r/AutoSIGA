import logging

class Exportador:
    """Responsável por processar e exportar transações em formato de texto para o SIGA."""
    
    @staticmethod
    def gerar_txt_ofertas(transacoes, filepath):
        """Compilador léxico em conformidade com as regras IT.TES.05.
        
        Realiza a leitura da lista nativa de transações OFX carregada, itera
        sobre as descrições e expurga registros usando uma cartilha de Blacklist.
        
        Args:
            transacoes (list): Lista de dicionários contendo transações.
            filepath (str): Caminho físico onde o arquivo TXT será salvo.
            
        Returns:
            tuple: (sucesso (bool), linhas_validas (int), qtd_descartadas (int))
            
        Raises:
            Exception: Caso ocorra problema de I/O na gravação do disco.
        """
        if not transacoes:
            return False, 0, 0

        # Palavras bloqueadas que categorizam lançamentos que NÃO são Ofertas
        # Rendimentos de aplicação, saques aplicados e dinheiro em caixa já lançado direto (depositos)
        palavras_bloqueadas = ["APLICA", "RESGATE", "RENDIMENT", "DEPOSITO", "RESG.", "DEP ", "CONGREGACAO"]

        linhas_limpas = []
        qtd_descartadas = 0

        for tx in transacoes:
            valor = tx.get("valor", 0.0)
            descricao = tx.get("descricao", "").upper()
            data = tx.get("data", "")

            # COND. 1: Somente valores POSITIVOS entram no lançamento puro (sem "-").
            if valor <= 0:
                qtd_descartadas += 1
                continue
            
            # COND. 2: Nenhuma palavra bloqueada pode fazer parte da descrição.
            if any(palavra in descricao for palavra in palavras_bloqueadas):
                qtd_descartadas += 1
                continue

            # FORMATAR VALOR (sem separador de milhar, virgula p/ centavos. ex: 1530,50)
            valor_fmt = f"{valor:.2f}".replace(".", ",")
            
            # Formato SIGA Csv: DATA;HISTÓRICO;VALOR
            linha = f"{data};{tx.get('descricao', '').strip()};{valor_fmt}"
            linhas_limpas.append(linha)

        if not linhas_limpas:
            return False, 0, qtd_descartadas

        try:
            # Utiliza utf-8 padrão (sem BOM) para evitar que o importador web ASP do SIGA
            # leia a assinatura invisível do arquivo como os caracteres 'ï»¿' na primeira linha.
            with open(filepath, 'w', encoding='utf-8') as f:
                for l in linhas_limpas:
                    f.write(l + "\n")
            return True, len(linhas_limpas), qtd_descartadas
        except Exception as e:
            logging.error(f"Erro ao salvar arquivo TXT: {e}", exc_info=True)
            raise e
