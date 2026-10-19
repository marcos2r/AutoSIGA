"""
Aba de extratos: seleção e leitura de arquivos, validação do lote e TXT de ofertas.
"""

from tkinter import filedialog, messagebox
import os
import logging
from models.ofx_reader import OfxReader
from models.xls_reader import XlsReader
from controllers.exportador import Exportador
from ui.card_conta_extrato import CardContaExtrato


class LoteExtratosMixin:
    """Montagem e validação do lote de extratos na janela principal."""

    def selecionar_arquivo(self, event=None):
        """Diálogo do sistema operacional para capturar múltiplos extratos (OFX ou XLS)."""
        caminhos_arquivos = filedialog.askopenfilenames(
            title="Selecione os arquivos de extrato (OFX ou XLS)",
            filetypes=[
                ("Extratos Bancários", "*.ofx;*.xls;*.xlsx"),
                ("Arquivos OFX (*.ofx)", "*.ofx"),
                ("Arquivos Excel (*.xls, *.xlsx)", "*.xls;*.xlsx"),
                ("Todos os Arquivos", "*.*")
            ]
        )

        if caminhos_arquivos:
            self.processar_multiplos_arquivos(caminhos_arquivos)

    def processar_multiplos_arquivos(self, caminhos):
        """Processa uma lista de caminhos de arquivos e atualiza a UI com o lote de cards."""
        self.dados_processados_lote = []
        erros = []
        
        # Remove os cards anteriores da interface
        for card in self.cards_lote:
            card.destroy()
        self.cards_lote = []
        
        assinaturas_lote = set()
        arquivos_descartados = []

        for caminho in caminhos:
            try:
                extensao = os.path.splitext(caminho)[1].lower()
                if extensao in ['.xls', '.xlsx']:
                    dados = XlsReader.parse_file(caminho)
                else:
                    dados = OfxReader.parse_file(caminho)
                
                # Assinatura única baseada em conta_id, datas e tipo do extrato
                chave_duplicado = (
                    str(dados.get("conta_id", "")).strip(),
                    str(dados.get("data_inicial", "")).strip(),
                    str(dados.get("data_final", "")).strip(),
                    str(dados.get("tipo_extrato", "")).strip(),
                    str(dados.get("produto", "")).strip()
                )
                
                if chave_duplicado in assinaturas_lote:
                    arquivos_descartados.append(os.path.basename(caminho))
                    continue
                    
                assinaturas_lote.add(chave_duplicado)
                dados["caminho_arquivo"] = caminho
                self.dados_processados_lote.append(dados)
            except Exception as e:
                nome_arq = os.path.basename(caminho)
                erros.append(f"{nome_arq}: {e}")
                logging.error(f"Erro ao processar arquivo {nome_arq}: {e}")
                
        if arquivos_descartados:
            msg_desc = f"Detectados {len(arquivos_descartados)} arquivo(s) duplicados no lote. Eles foram ignorados para evitar conciliação duplicada:\n\n" + "\n".join(arquivos_descartados)
            messagebox.showinfo("Arquivos Duplicados Ignorados", msg_desc)
                
        if erros:
            msg_erro = "Alguns arquivos não puderam ser lidos:\n\n" + "\n".join(erros)
            messagebox.showwarning("Erro de Leitura Parcial", msg_erro)
            
        if self.dados_processados_lote:
            self.lbl_no_data.pack_forget()
            
            # Instancia os novos cards roláveis para cada conta
            for dados in self.dados_processados_lote:
                card = CardContaExtrato(
                    self.scroll_lote, dados, self.config_manager, self.validar_lote_e_atualizar_botoes
                )
                card.pack(fill="x", padx=5, pady=5)
                self.cards_lote.append(card)
                
            qtd = len(self.dados_processados_lote)
            nomes_arquivos = [os.path.basename(d["caminho_arquivo"]) for d in self.dados_processados_lote]
            if len(nomes_arquivos) > 3:
                texto_arquivos = f"{qtd} arquivo(s) selecionado(s):\n" + ", ".join(nomes_arquivos[:3]) + f" ... (+ {qtd - 3} outros)"
            else:
                texto_arquivos = f"{qtd} arquivo(s) selecionado(s):\n" + ", ".join(nomes_arquivos)
            self.label_arquivo.configure(text=texto_arquivos, text_color="#3C763D")
            
            self.validar_lote_e_atualizar_botoes()
        else:
            self.lbl_no_data.pack(pady=40)
            self.label_arquivo.configure(text="Nenhum arquivo selecionado.", text_color="#666666")
            self.botao_conectar.configure(state="disabled")
            self.botao_gerar_txt.configure(state="disabled")
            self.atualizar_status("Nenhum arquivo carregado com sucesso.", "#D9534F")

    def resetar_lote(self, event=None):
        """Limpa toda a seleção de arquivos e reseta o estado da janela principal (atalho Esc)."""
        self.dados_processados_lote = []
        for card in self.cards_lote:
            card.destroy()
        self.cards_lote = []
        self.lbl_no_data.pack(pady=40)
        self.label_arquivo.configure(text="Nenhum arquivo selecionado.", text_color="#666666")
        self.botao_conectar.configure(state="disabled")
        self.botao_gerar_txt.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.atualizar_status("Lote limpo com sucesso. Aguardando novos arquivos.", "#666666")

    def processar_ofx(self, caminho):
        """Mantido para compatibilidade, delega para processar_multiplos_arquivos."""
        self.processar_multiplos_arquivos([caminho])

    def validar_lote_e_atualizar_botoes(self):
        """Verifica se todos os cards do lote estão mapeados e gerencia a ativação dos botões."""
        if not self.cards_lote:
            self.botao_conectar.configure(state="disabled")
            self.botao_gerar_txt.configure(state="disabled")
            return
            
        todos_validos = True
        for card in self.cards_lote:
            info = card.obter_dados_mapeados()
            if not info["valido"]:
                todos_validos = False
                break
                
        if todos_validos:
            self.botao_conectar.configure(state="normal")
            self.atualizar_status("Todos os extratos estão configurados. Pronto para conciliar!", "#3C763D")
        else:
            self.botao_conectar.configure(state="disabled")
            self.atualizar_status("Preencha as configurações pendentes nos cards acima.", "#F89406")
            
        tem_conta_corrente = any(not card.is_aplicacao for card in self.cards_lote)
        if tem_conta_corrente:
            self.botao_gerar_txt.configure(state="normal")
        else:
            self.botao_gerar_txt.configure(state="disabled")

    def gerar_txt_ofertas(self, event=None):
        """Delega a geração de TXT das transações de Conta Corrente do lote ao Controller Exportador."""
        if not self.dados_processados_lote:
            messagebox.showerror("Erro", "Nenhum arquivo processado.")
            return

        # Garante o salvamento dos mapeamentos de todos os cards ativos na tela
        for card in self.cards_lote:
            card.salvar_e_notificar()

        transacoes_acumuladas = []
        contas_acumuladas = []
        for dados in self.dados_processados_lote:
            if dados.get("tipo_extrato") != "APLICACAO":
                transacoes_acumuladas.extend(dados.get("transacoes", []))
                if dados.get("conta_id") not in contas_acumuladas:
                    contas_acumuladas.append(str(dados.get("conta_id", "")))

        if not transacoes_acumuladas:
            messagebox.showerror("Erro", "Nenhuma transação de Conta Corrente encontrada no lote.")
            return

        nome_sugerido = f"OFERTAS_LOTE_{'_'.join(contas_acumuladas[:3])}.txt"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=nome_sugerido,
            title="Salvar arquivo de Ofertas SIGA",
            filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")]
        )

        if filepath:
            try:
                sucesso, qtd_limpas, qtd_desc = Exportador.gerar_txt_ofertas(transacoes_acumuladas, filepath)
                if sucesso:
                    messagebox.showinfo("Sucesso", f"Exportação finalizada!\nOfertas Mantidas: {qtd_limpas}\nDescartadas: {qtd_desc}")
                else:
                    messagebox.showwarning("Aviso", "Não sobrou nenhuma linha de Oferta para gerar arquivo!")
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", str(e))
