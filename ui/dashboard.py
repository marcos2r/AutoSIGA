"""
Janelas de autorização de lançamentos e dashboard de produtividade ao fim do lote.
"""

import time
from tkinter import filedialog, messagebox

import customtkinter as ctk

from controllers.diferenca_extrato import cabecalho_extrato, linhas_do_extrato
from controllers.exportador import Exportador
from controllers.prova_real import resumo_resultado
from ui import tema


class DashboardMixin:
    """Janelas exibidas pela janela principal durante e após a automação."""

    def mostrar_janela_lancamentos(self, lancamentos, contexto=None):
        """
        Prévia (opcional) dos lançamentos que o robô vai gravar num extrato, ou das faturas
        de energia que vai aprovar e baixar (`contexto["tipo"] == "baixas"`).
        A thread do robô espera até o usuário gravar ou pular; fechar a janela é pular.
        """
        contexto = contexto or {}
        tipo = contexto.get("tipo")
        baixas = tipo in ("baixas", "provisoes")  # descrição inteira, sem cortar
        qtd = len(lancamentos)
        titulo, rotulo_ok, rotulo_pular = {
            "baixas": (f"Faturas de Energia a Baixar ({qtd})", f"Aprovar e baixar {qtd} fatura(s)", "Pular as baixas"),
            "provisoes": (f"Faturas de Energia a Provisionar ({qtd})", f"Provisionar {qtd} fatura(s)",
                          "Pular as provisões"),
        }.get(tipo, (f"Lançamentos a Importar ({qtd})", f"Lançar {qtd} itens", "Pular este extrato"))
        janela = ctk.CTkToplevel(self)
        janela.title("Ação Necessária: Lançamentos Pendentes")
        janela.geometry("650x500")
        janela.configure(fg_color="#FFFFFF")
        janela.lift()
        janela.focus_force()
        janela.attributes('-topmost', True)
        janela.grab_set() # Foca os cliques apenas neste modal

        lbl_titulo = ctk.CTkLabel(janela, text=titulo, font=self.fonte_titulo, text_color=self.cor_azul_header)
        lbl_titulo.pack(pady=(20, 2))
        if contexto:
            cabecalho = "Faturas do e-mail sem provisão no SIGA" if tipo == "provisoes"                 else f"Conta {contexto.get('conta', '')} · {contexto.get('localidade', '')}"
            ctk.CTkLabel(janela, text=cabecalho,
                         font=(tema.FONTE, 12), text_color=tema.CINZA_TEXTO).pack(pady=(0, 8))

        frame_scroll = ctk.CTkScrollableFrame(janela, width=600, height=300, fg_color="#F8F9FA", corner_radius=6)
        frame_scroll.pack(padx=20, pady=10, fill="both", expand=True)

        # Dinamicamente cria uma linha colorida (Verde/Vermelho) para cada registro
        for tx in lancamentos:
            frame_item = ctk.CTkFrame(frame_scroll, fg_color="#FFFFFF", corner_radius=4, border_width=1, border_color="#DDDDDD")
            frame_item.pack(fill="x", pady=5, padx=5)

            valor = tx.get("valor", 0.0)
            cor_valor = "#3C763D" if valor >= 0 else "#D9534F"
            valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            ctk.CTkLabel(frame_item, text=tx.get("data", ""), font=("Open Sans", 13, "bold"), width=80).pack(side="left", padx=10, pady=5)
            desc = tx.get("historico") or tx.get("descricao", "")
            ctk.CTkLabel(frame_item, text=desc if baixas else desc[:50], font=("Open Sans", 12), anchor="w",
                         justify="left", wraplength=360).pack(side="left", padx=10, pady=5, fill="x", expand=True)
            ctk.CTkLabel(frame_item, text=valor_fmt, font=("Open Sans", 13, "bold"), text_color=cor_valor).pack(side="right", padx=15, pady=5)

        frame_botoes = ctk.CTkFrame(janela, fg_color="transparent")
        frame_botoes.pack(pady=15)

        ctk.CTkButton(frame_botoes, text=rotulo_ok, command=lambda: self.autorizar_lancamentos(janela),
                      fg_color=tema.AZUL_NAVBAR, hover_color=tema.AZUL_NAVBAR_HOVER, height=40).pack(side="left", padx=10)
        ctk.CTkButton(frame_botoes, text=rotulo_pular, command=lambda: self.cancelar_lancamentos(janela),
                      fg_color=tema.BRANCO, hover_color=tema.CINZA_HOVER, text_color=tema.CINZA_TEXTO,
                      border_width=1, border_color=tema.CINZA_BORDA, height=40).pack(side="right", padx=10)

        janela.protocol("WM_DELETE_WINDOW", lambda: self.cancelar_lancamentos(janela))

    def autorizar_lancamentos(self, janela):
        """Libera o robô para gravar os lançamentos da prévia."""
        if self.bot_instance:
            self.bot_instance.responder_autorizacao(True)
        janela.destroy()

    def cancelar_lancamentos(self, janela):
        """Pula o extrato da prévia: o robô não grava nada nele e segue para o próximo."""
        if self.bot_instance:
            self.bot_instance.responder_autorizacao(False)
        janela.destroy()

    def _secao_provisoes(self, container, linhas):
        """Provisões de energia do período: o resumo e cada fatura que ficou pendente, com o motivo."""
        cores = {"ok": tema.VERDE_TEXTO, "alerta": tema.VERMELHO_TEXTO, "neutro": tema.CINZA_TEXTO}
        ctk.CTkLabel(container, text="PROVISÕES DE ENERGIA (E-MAIL × CONTAS A PAGAR)", font=(tema.FONTE, 10, "bold"),
                     text_color=tema.AZUL_TITULO).pack(anchor="w", padx=27, pady=(4, 2))
        lista = ctk.CTkScrollableFrame(container, height=min(24 * len(linhas), 120), fg_color=tema.BRANCO,
                                       border_width=1, border_color=tema.CINZA_BORDA)
        lista.pack(fill="x", padx=15, pady=(0, 6))
        for nivel, texto in linhas:
            ctk.CTkLabel(lista, text=texto, font=(tema.FONTE, 11), text_color=cores.get(nivel, tema.CINZA_TEXTO),
                         anchor="w", justify="left", wraplength=540).pack(fill="x", padx=6, pady=1)

    def _secao_prova_real(self, container, resultados):
        """Lista o resultado de cada extrato: saldo do SIGA × banco e lançamentos sem par."""
        cores = {"ok": tema.VERDE_TEXTO, "alerta": tema.VERMELHO_TEXTO, "neutro": tema.CINZA_TEXTO}
        ctk.CTkLabel(container, text="PROVA REAL (SALDO DO SIGA × BANCO)", font=(tema.FONTE, 10, "bold"),
                     text_color=tema.AZUL_TITULO).pack(anchor="w", padx=27, pady=(4, 2))
        detalhes = [linhas_do_extrato(r) for r in resultados]
        qtd_linhas = sum(2 + len(d) for d in detalhes)
        lista = ctk.CTkScrollableFrame(container, height=min(26 * qtd_linhas, 260), fg_color=tema.BRANCO,
                                       border_width=1, border_color=tema.CINZA_BORDA)
        lista.pack(fill="x", padx=15, pady=(0, 6))
        for r, detalhe in zip(resultados, detalhes, strict=True):
            nivel, texto = resumo_resultado(r)
            linha = ctk.CTkFrame(lista, fg_color="transparent")
            linha.pack(fill="x", padx=6, pady=3)
            ctk.CTkLabel(linha, text=cabecalho_extrato(r), font=(tema.FONTE, 11, "bold"),
                         text_color=tema.CINZA_TEXTO, anchor="w").pack(fill="x")
            ctk.CTkLabel(linha, text=texto, font=(tema.FONTE, 11), text_color=cores[nivel], anchor="w",
                         justify="left", wraplength=540).pack(fill="x")
            # De onde vem a diferença e as baixas de energia, com cada pendência e o motivo
            for nivel_detalhe, texto_detalhe in detalhe:
                ctk.CTkLabel(linha, text=texto_detalhe, font=(tema.FONTE, 11), text_color=cores[nivel_detalhe],
                             anchor="w", justify="left", wraplength=540).pack(fill="x")

    def mostrar_dashboard_produtividade(self, telemetria, tempo_inicio):
        """Exibe o popup parabenizando a finalização dos trabalhos com métricas e ROI financeiro."""
        janela = ctk.CTkToplevel(self)
        janela.title("Métricas de Produtividade AutoSIGA")
        janela.geometry("540x530")
        janela.configure(fg_color="#F1F5F9")
        janela.lift()
        janela.focus_force()
        janela.attributes('-topmost', True)
        janela.grab_set()

        tipo_lote = telemetria.get("tipo_lote", "extrato")

        tempo_total = time.time() - tempo_inicio
        minutos = int(tempo_total // 60)
        segundos = int(tempo_total % 60)

        ofx_itens = telemetria.get("ofx_itens", 0)
        injecoes = telemetria.get("injecoes", 0)
        total_contas = telemetria.get("total_contas", 1)
        volume_fin = telemetria.get("volume_financeiro", 0.0)
        pendentes = telemetria.get("pendentes", 0)

        # Métrica de ROI Humano:
        if tipo_lote == "energia":
            # 120 segundos para preenchimento de provisão e upload manual de PDF por fatura
            tempo_humano_segundos = injecoes * 120
        else:
            # 30 segundos para checagem manual por item do extrato (conciliação visual)
            # + 60 segundos para digitação manual, cliques no select2 e gravação de cada novo lançamento
            tempo_humano_segundos = (ofx_itens * 30) + (injecoes * 60)

        if tempo_humano_segundos < 60:
            tempo_humano_segundos = 60

        h_minutos = int(tempo_humano_segundos // 60)
        h_segundos = int(tempo_humano_segundos % 60)

        economia_segundos = max(0, tempo_humano_segundos - tempo_total)
        e_minutos = int(economia_segundos // 60)
        e_segundos = int(economia_segundos % 60)

        # ROI Financeiro (Tarifa de R$ 30,00/hora de trabalho administrativo)
        roi_financeiro = (economia_segundos / 3600.0) * 30.0

        # Taxa de Assertividade
        if tipo_lote == "energia":
            total_acao = injecoes + pendentes
            assertividade = (injecoes / total_acao) * 100.0 if total_acao > 0 else 100.0
        else:
            if ofx_itens > 0:
                assertividade = max(0.0, min(100.0, ((ofx_itens - pendentes) / ofx_itens) * 100.0))
            else:
                assertividade = 100.0

        # Formatações brasileiras
        volume_fmt = f"R$ {volume_fin:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        roi_fmt = f"R$ {roi_financeiro:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        frame = ctk.CTkFrame(janela, fg_color="#FFFFFF", corner_radius=8, border_width=1, border_color="#DDDDDD")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text="✅ Missão Cumprida!", font=("Open Sans", 20, "bold"), text_color="#3C763D").pack(pady=(12, 4))

        # Painel central de dados
        frame_tabela = ctk.CTkFrame(frame, fg_color="#F8F9FA", corner_radius=6)
        frame_tabela.pack(padx=15, pady=8, fill="both", expand=True)

        # Auxiliar de linha
        def add_linha(container, label, valor, cor_valor="#333333", negrito=False):
            f_row = ctk.CTkFrame(container, fg_color="transparent")
            f_row.pack(fill="x", padx=12, pady=3)
            font_lbl = ("Open Sans", 11)
            font_val = ("Open Sans", 11, "bold") if negrito else ("Open Sans", 11)

            ctk.CTkLabel(f_row, text=label, font=font_lbl, text_color="#555555").pack(side="left")
            ctk.CTkLabel(f_row, text=valor, font=font_val, text_color=cor_valor).pack(side="right")

        # Bloco 1: Métricas Operacionais
        lbl_secao1 = ctk.CTkLabel(frame_tabela, text="MÉTRICAS OPERACIONAIS", font=("Open Sans", 10, "bold"), text_color="#3D71A8")
        lbl_secao1.pack(anchor="w", padx=12, pady=(10, 4))

        if tipo_lote == "energia":
            add_linha(frame_tabela, "Total de faturas no lote:", f"{total_contas}")
            add_linha(frame_tabela, "Faturas identificadas com UC mapeada:", f"{ofx_itens}")
            add_linha(frame_tabela, "Faturas importadas com sucesso:", f"{injecoes}")
        else:
            add_linha(frame_tabela, "Contas processadas no lote:", f"{total_contas}")
            add_linha(frame_tabela, "Transações de extrato verificadas:", f"{ofx_itens}")
            add_linha(frame_tabela, "Lançamentos importados no SIGA:", f"{injecoes}")
        add_linha(frame_tabela, "Taxa de assertividade:", f"{assertividade:.1f}%", cor_valor="#3C763D" if assertividade > 95 else "#F89406", negrito=True)

        # Divisor
        div = ctk.CTkFrame(frame_tabela, height=1, fg_color="#E5E7EB")
        div.pack(fill="x", padx=10, pady=6)

        # Bloco 2: Métricas Financeiras e ROI
        lbl_secao2 = ctk.CTkLabel(frame_tabela, text="RETORNO & ECONOMIA (ROI)", font=("Open Sans", 10, "bold"), text_color="#3D71A8")
        lbl_secao2.pack(anchor="w", padx=12, pady=(2, 4))

        add_linha(frame_tabela, "Volume financeiro total processado:", volume_fmt, cor_valor="#333333", negrito=True)
        add_linha(frame_tabela, "Tempo gasto pelo AutoSIGA:", f"{minutos}m {segundos}s", cor_valor="#428BCA", negrito=True)
        add_linha(frame_tabela, "Tempo estimado (Manual):", f"{h_minutos}m {h_segundos}s", cor_valor="#D9534F")
        add_linha(frame_tabela, "Tempo economizado:", f"🔥 {e_minutos}m {e_segundos}s", cor_valor="#5CB85C", negrito=True)
        add_linha(frame_tabela, "Retorno financeiro estimado (ROI):", roi_fmt, cor_valor="#5CB85C", negrito=True)

        if telemetria.get("extratos") or telemetria.get("provisoes_energia"):
            # As métricas deixam de ocupar a sobra de altura, senão empurram os botões para fora da janela
            frame_tabela.pack_configure(expand=False, fill="x")
        if telemetria.get("provisoes_energia"):
            self._secao_provisoes(frame, telemetria["provisoes_energia"])
        if telemetria.get("extratos"):
            self._secao_prova_real(frame, telemetria["extratos"])

        # Função para salvar a planilha Excel
        def exportar_planilha():
            filepath = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                initialfile="RELATORIO_PRODUTIVIDADE_AUTOSIGA.xlsx",
                title="Exportar Relatório de Produtividade",
                filetypes=[("Arquivos Excel", "*.xlsx"), ("Todos os Arquivos", "*.*")]
            )
            if filepath:
                try:
                    Exportador.gerar_excel_lote(telemetria, self.dados_processados_lote, filepath)
                    messagebox.showinfo("Sucesso", "Relatório Excel exportado com sucesso!", parent=janela)
                except Exception as ex:
                    messagebox.showerror("Erro ao Exportar", str(ex), parent=janela)

        # Espaçador interno
        ctk.CTkLabel(frame_tabela, text="", font=("Open Sans", 2)).pack()

        # Frame horizontal para botões de rodapé da modal
        frame_acoes = ctk.CTkFrame(frame, fg_color="transparent")
        frame_acoes.pack(pady=(8, 12))

        btn_excel = ctk.CTkButton(
            frame_acoes, text="Exportar Excel (.xlsx)", font=("Open Sans", 13, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=32, width=155,
            command=exportar_planilha
        )
        btn_excel.grid(row=0, column=0, padx=5)

        btn_fechar = ctk.CTkButton(
            frame_acoes, text="Fechar", font=("Open Sans", 13, "bold"),
            fg_color="#428BCA", hover_color="#3071A9", height=32, width=120,
            command=janela.destroy
        )
        btn_fechar.grid(row=0, column=1, padx=5)

        if telemetria.get("extratos"):
            # Altura pelo conteúdo, sem passar da tela, para os botões nunca ficarem de fora
            janela.update_idletasks()
            altura = min(frame.winfo_reqheight() + 48, janela.winfo_screenheight() - 80)
            janela.geometry(f"640x{altura}")
