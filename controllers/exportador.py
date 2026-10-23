"""
Módulo de Exportação Contábil (Controller).

Este módulo contém as regras de formatação e expurgo necessárias para
gerar o arquivo CSV customizado (que leva extensão .txt) de Ofertas,
permitindo a importação manual em lote no sistema legado do SIGA.
"""

import calendar
import logging
from datetime import datetime

from controllers.prova_real import DIVERGE, resumo_resultado


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

        ofertas, qtd_descartadas = Exportador.filtrar_ofertas(transacoes)
        if not ofertas:
            return False, 0, qtd_descartadas

        linhas_limpas = []
        for tx in ofertas:
            # FORMATAR VALOR (sem separador de milhar, virgula p/ centavos. ex: 1530,50)
            # O SIGA legado em ASP classic quebra se mandarmos '1.530,50' ou '1530.50'
            valor_fmt = f"{tx.get('valor', 0.0):.2f}".replace(".", ",")

            # Formato SIGA Csv: DATA;HISTÓRICO;VALOR
            # O histórico (MEMO + NAME) é o texto exportado; a filtragem usa só o MEMO.
            historico = tx.get('historico') or tx.get('descricao', '')
            linhas_limpas.append(f"{tx.get('data', '')};{historico.strip()};{valor_fmt}")

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

    # Palavras bloqueadas que categorizam lançamentos que NÃO são Ofertas puras.
    # Por exemplo: Rendimentos de aplicação, saques aplicados e dinheiro em
    # caixa já lançado direto (depositos ou congregação).
    PALAVRAS_BLOQUEADAS = ["APLICA", "RESGATE", "RENDIMENT", "DEPOSITO", "RESG.", "DEP ", "CONGREGACAO", "TRANSFERENCIA"]

    @staticmethod
    def filtrar_ofertas(transacoes):
        """
        Separa as transações que são ofertas puras (regras IT.TES.05).

        Args:
            transacoes (list): Lista de dicionários contendo transações do OFX.

        Returns:
            tuple: (ofertas, qtd_descartadas), onde ofertas é a lista das transações mantidas.
        """
        ofertas = []
        qtd_descartadas = 0
        for tx in transacoes or []:
            descricao = tx.get("descricao", "").upper()
            # COND. 1: Somente valores POSITIVOS (o SIGA não aceita estornos neste arquivo).
            # COND. 2: Nenhuma palavra bloqueada no MEMO.
            if tx.get("valor", 0.0) <= 0 or any(p in descricao for p in Exportador.PALAVRAS_BLOQUEADAS):
                qtd_descartadas += 1
                continue
            ofertas.append(tx)
        return ofertas, qtd_descartadas

    @staticmethod
    def resumo_ofertas(ofertas):
        """
        Calcula o total e a data de importação (último dia do mês da oferta mais recente).

        Args:
            ofertas (list): Transações já filtradas por `filtrar_ofertas`, com data "dd/mm/aaaa".

        Returns:
            tuple: (total, data_importacao "dd/mm/aaaa", competencia "mm/aaaa"); datas vazias se nenhuma for válida.
        """
        total = round(sum(tx.get("valor", 0.0) for tx in ofertas), 2)
        datas = []
        for tx in ofertas:
            try:
                datas.append(datetime.strptime(tx.get("data", ""), "%d/%m/%Y"))
            except ValueError:
                continue
        if not datas:
            return total, "", ""
        mais_recente = max(datas)
        ultimo_dia = calendar.monthrange(mais_recente.year, mais_recente.month)[1]
        return total, f"{ultimo_dia:02d}/{mais_recente:%m/%Y}", f"{mais_recente:%m/%Y}"

    @staticmethod
    def formatar_moeda(valor):
        """Formata um valor no padrão exibido pelo SIGA (ex: 'R$ 1.234,56')."""
        texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"

    @staticmethod
    def gerar_excel_lote(telemetria, dados_lote, filepath):
        """
        Gera uma planilha Excel formatada (.xlsx) com o resumo do lote de conciliação,
        incluindo transações processadas, status de conferência e pendências.
        """
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = openpyxl.Workbook()

        # 1. Planilha de Resumo Geral
        ws_resumo = wb.active
        ws_resumo.title = "Resumo do Lote"
        ws_resumo.views.sheetView[0].showGridLines = True

        # Cores e Estilos (Alinhado com a identidade visual)
        cor_header = PatternFill(start_color="438EB9", end_color="438EB9", fill_type="solid")
        cor_zebra = PatternFill(start_color="F9FBFD", end_color="F9FBFD", fill_type="solid")
        fonte_titulo = Font(name="Segoe UI", size=16, bold=True, color="438EB9")
        fonte_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        fonte_normal = Font(name="Segoe UI", size=10)
        fonte_bold = Font(name="Segoe UI", size=10, bold=True)

        # Título
        ws_resumo["A1"] = "AutoSIGA - Relatório de Produtividade do Lote"
        ws_resumo["A1"].font = fonte_titulo
        ws_resumo.row_dimensions[1].height = 30

        # Métricas Gerais
        ws_resumo["A3"] = "Métrica"
        ws_resumo["B3"] = "Valor"
        for col in ["A", "B"]:
            ws_resumo[f"{col}3"].fill = cor_header
            ws_resumo[f"{col}3"].font = fonte_header
            ws_resumo[f"{col}3"].alignment = Alignment(horizontal="center")

        dados_metrica = [
            ("Total de Extratos Processados", telemetria.get("total_contas", 0)),
            ("Transações no Extrato (OFX)", telemetria.get("ofx_itens", 0)),
            ("Transações Localizadas no SIGA", telemetria.get("siga_itens", 0)),
            ("Lançamentos Injetados", telemetria.get("injecoes", 0)),
            ("Pendências Finais não Conciliadas", telemetria.get("pendentes", 0)),
            ("Volume Financeiro Conciliado (R$)", telemetria.get("volume_financeiro", 0.0)),
        ]

        for idx, (m, v) in enumerate(dados_metrica, start=4):
            ws_resumo[f"A{idx}"] = m
            ws_resumo[f"B{idx}"] = v
            ws_resumo[f"A{idx}"].font = fonte_normal
            ws_resumo[f"B{idx}"].font = fonte_bold
            if "Volume" in m:
                ws_resumo[f"B{idx}"].number_format = 'R$ #,##0.00'
                ws_resumo[f"B{idx}"].alignment = Alignment(horizontal="right")
            else:
                ws_resumo[f"B{idx}"].alignment = Alignment(horizontal="right")

            # Linha zebrada
            if idx % 2 == 0:
                ws_resumo[f"A{idx}"].fill = cor_zebra
                ws_resumo[f"B{idx}"].fill = cor_zebra

        # 2. Planilha de Detalhamento por Extrato
        ws_detalhe = wb.create_sheet(title="Detalhamento")
        ws_detalhe.views.sheetView[0].showGridLines = True

        headers_det = ["Localidade", "Tipo Extrato", "Conta Bancária", "Total Transações", "Transações SIGA", "Injetados", "Status Final"]
        ws_detalhe.row_dimensions[1].height = 25
        for col_idx, text in enumerate(headers_det, start=1):
            cell = ws_detalhe.cell(row=1, column=col_idx, value=text)
            cell.fill = cor_header
            cell.font = fonte_header
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for row_idx, d in enumerate(dados_lote, start=2):
            ws_detalhe.row_dimensions[row_idx].height = 20
            loc = f"{d.get('tipo_adm', '')} - {d.get('nome_adm', '')}"
            tipo = d.get('tipo_extrato', 'CONTA CORRENTE')
            conta = d.get('conta_id', '')
            total_tx = len(d.get('transacoes', []))
            total_siga = len(d.get('extrato_siga', []))

            # Tenta pegar a quantidade injetada de forma condicional se existirem pendências
            inj = total_tx - len(d.get('pendentes', [])) if 'pendentes' in d else total_tx
            status = "Conciliado 100%" if not d.get('pendentes') else f"{len(d.get('pendentes'))} pendentes"

            ws_detalhe.cell(row=row_idx, column=1, value=loc).font = fonte_normal
            ws_detalhe.cell(row=row_idx, column=2, value=tipo).font = fonte_normal
            ws_detalhe.cell(row=row_idx, column=3, value=conta).font = fonte_normal
            ws_detalhe.cell(row=row_idx, column=4, value=total_tx).font = fonte_normal
            ws_detalhe.cell(row=row_idx, column=5, value=total_siga).font = fonte_normal
            ws_detalhe.cell(row=row_idx, column=6, value=inj).font = fonte_normal

            status_cell = ws_detalhe.cell(row=row_idx, column=7, value=status)
            status_cell.font = fonte_bold
            if "100%" in status:
                status_cell.fill = PatternFill(start_color="DFF0D8", end_color="DFF0D8", fill_type="solid")
                status_cell.font = Font(name="Segoe UI", size=10, bold=True, color="3C763D")
            else:
                status_cell.fill = PatternFill(start_color="F2DEDE", end_color="F2DEDE", fill_type="solid")
                status_cell.font = Font(name="Segoe UI", size=10, bold=True, color="A94442")

            if row_idx % 2 == 0:
                for c in range(1, 7):
                    ws_detalhe.cell(row=row_idx, column=c).fill = cor_zebra

        abas = [ws_resumo, ws_detalhe]
        if telemetria.get("extratos"):
            abas.append(Exportador._aba_prova_real(wb, telemetria["extratos"], cor_header, fonte_header, fonte_normal))

        # Redimensionamento dinâmico das colunas
        for sheet in abas:
            for col in sheet.columns:
                max_len = 0
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

        wb.save(filepath)

    @staticmethod
    def _aba_prova_real(wb, resultados, cor_header, fonte_header, fonte_normal):
        """Aba "Prova Real": saldo do banco × SIGA por extrato e, abaixo, os lançamentos sem par."""
        from openpyxl.styles import Alignment

        ws = wb.create_sheet(title="Prova Real")
        cabecalho = ["Localidade", "Conta SIGA", "Conta Bancária", "Saldo Banco", "Saldo SIGA", "Diferença",
                     "Lançados", "Pendentes", "Resultado"]
        for col, texto in enumerate(cabecalho, start=1):
            cell = ws.cell(row=1, column=col, value=texto)
            cell.fill, cell.font = cor_header, fonte_header
            cell.alignment = Alignment(horizontal="center")

        linha = 2
        for r in resultados:
            valores = [r.localidade, r.conta_siga, r.conta_id, r.saldo.saldo_banco, r.saldo.saldo_siga,
                       r.saldo.diferenca if r.saldo.status == DIVERGE else None, r.lancados, r.pendentes,
                       resumo_resultado(r)[1]]
            for col, valor in enumerate(valores, start=1):
                cell = ws.cell(row=linha, column=col, value=valor)
                cell.font = fonte_normal
                if 4 <= col <= 6:
                    cell.number_format = 'R$ #,##0.00'
            linha += 1

        sobras = [(r, s) for r in resultados for s in (r.sobras or [])]
        if sobras:
            linha += 1
            for col, texto in enumerate(["Lançamentos no SIGA sem par no banco", "Conta SIGA", "Data",
                                         "Histórico", "Valor"], start=1):
                cell = ws.cell(row=linha, column=col, value=texto)
                cell.fill, cell.font = cor_header, fonte_header
            for r, s in sobras:
                linha += 1
                for col, valor in enumerate([r.localidade, r.conta_siga, s.data, s.historico, s.valor], start=1):
                    ws.cell(row=linha, column=col, value=valor).font = fonte_normal
                ws.cell(row=linha, column=5).number_format = 'R$ #,##0.00'
        return ws

