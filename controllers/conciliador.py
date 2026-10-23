"""
Módulo de Conciliação Contábil (Controller).

Este módulo contém a lógica de negócio principal do sistema de checagem.
Ele cruza duas matrizes de dados (OFX do Banco x Tabela HTML do SIGA) e
identifica exatamente quais transações estão no banco mas ainda não
foram lançadas no sistema.
"""

from datetime import datetime

from controllers.prova_real import normalizar_linhas_siga


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

        # 1. Normalização dos dados do SIGA (entrada positiva, saída negativa)
        siga_txs = [{'data': m.data, 'valor': m.valor, 'matched': False}  # matched: cada linha casa uma vez só
                    for m in normalizar_linhas_siga(siga_txs_raw)]

        # 2. Fase de Cruzamento (Conciliação)
        a_lancar = []

        # Filtro de negócio: O robô só assume responsabilidade por transferências interbancárias
        # de investimento. Depósitos em espécie e transferências PIX normais são ignorados.
        kw_investimentos = ['APLIC', 'RESG', 'RDC', 'CDB', 'POUP', 'INVEST', 'REND', 'CAPITALIZ']

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


def fora_do_periodo(linhas: list[dict], inicio: str, fim: str) -> list[str]:
    """Datas da grade do SIGA que caem fora do período consultado.

    A TES01701 abre com o filtro do mês atual. Se o período do extrato não for aplicado,
    a grade é de outro mês e todo o extrato parece faltar no SIGA (em 23/10/2026 isso
    duplicou 14 lançamentos de setembro). Qualquer data fora do período invalida a leitura.

    Args:
        linhas: Linhas da grade (`{"data": "dd/mm/aaaa", ...}`).
        inicio: Data inicial do extrato, "dd/mm/aaaa" (vazia: sem conferência).
        fim: Data final do extrato, "dd/mm/aaaa" (vazia: sem conferência).

    Returns:
        list[str]: As datas fora do período, na ordem da grade (vazia se a grade confere).
    """
    try:
        ini, fin = datetime.strptime(inicio, "%d/%m/%Y"), datetime.strptime(fim, "%d/%m/%Y")
    except (TypeError, ValueError):
        return []
    fora = []
    for linha in linhas or []:
        try:
            data = datetime.strptime(str(linha.get("data", "")).strip(), "%d/%m/%Y")
        except ValueError:
            continue  # linha sem data (total, saldo anterior)
        if not ini <= data <= fin:
            fora.append(linha["data"])
    return fora
