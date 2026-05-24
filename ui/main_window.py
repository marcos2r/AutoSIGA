"""
Módulo de Interface Gráfica (View).

Este módulo define a janela principal do AutoSIGA utilizando a biblioteca
CustomTkinter para criar uma interface moderna e agradável. 
Aqui ocorre a interação humana, coleta de cliques, configuração de parâmetros
na tela e delegação das tarefas pesadas para as camadas Model, Controller e Bot.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import logging

from models.config_manager import ConfigManager
from models.ofx_reader import OfxReader
from models.xls_reader import XlsReader
from controllers.exportador import Exportador
from bot.siga_bot import SigaBot

# Força o tema claro para combinar com a identidade visual do SIGA
ctk.set_appearance_mode("light")

class MainWindow(ctk.CTk):
    """
    Classe principal que desenha e controla a interface do usuário.
    
    Herda de ctk.CTk, tornando-se a janela raiz do aplicativo.
    É responsável por orquestrar a montagem dos botões, inputs, painéis e 
    gerenciar o estado reativo da aplicação.
    """
    
    def __init__(self):
        """
        Inicializa a janela, define dimensões, paleta de cores e carrega 
        as configurações salvas em sessões anteriores.
        """
        super().__init__()

        # Variáveis de Estado
        self.dados_processados = None
        self.bot_instance = None
        self.config_manager = ConfigManager()

        # Configurações nativas da Janela
        self.title("AutoSIGA v1.2.0 - Importação de Lançamentos")
        self.geometry("600x680")
        self.configure(fg_color="#F1F5F9")
        
        # Intercepta o botão "X" da janela para fechamento gracioso
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Paleta de Cores e Tipografia (Bootstrap Theme like)
        self.fonte_padrao = ("Open Sans", 14)
        self.fonte_titulo = ("Open Sans", 24, "bold")
        self.cor_azul_botao = "#428BCA"
        self.cor_azul_hover = "#3071A9"
        self.cor_laranja_logo = "#F89406"
        self.cor_azul_header = "#438EB9"

        # Inicializa a UI e restaura estado local
        self.construir_interface()
        self.carregar_configuracoes()

    def on_closing(self):
        """
        Gatilho acionado quando o usuário tenta fechar o programa pelo 'X'.
        Encerra o robô (Playwright) em background antes de matar a UI.
        """
        if self.bot_instance:
            self.bot_instance.fechar_browser()
        self.after(500, self.destroy)

    def construir_interface(self):
        """
        Desenha proceduralmente os elementos (widgets) na tela.
        Organiza o layout através de Frames verticais e Grids internos.
        """
        # ==========================================
        # HEADER (Cabeçalho Superior)
        # ==========================================
        self.frame_header = ctk.CTkFrame(self, fg_color=self.cor_azul_header, corner_radius=0, height=70)
        self.frame_header.pack(fill="x", side="top")
        
        self.label_chevron = ctk.CTkLabel(self.frame_header, text="> ", font=self.fonte_titulo, text_color=self.cor_laranja_logo)
        self.label_chevron.pack(side="left", padx=(20, 0), pady=15)
        
        self.label_titulo = ctk.CTkLabel(self.frame_header, text="AutoSIGA", font=self.fonte_titulo, text_color="#FFFFFF")
        self.label_titulo.pack(side="left", pady=15)

        # ==========================================
        # MAIN CARD (Corpo Central Branco)
        # ==========================================
        self.frame_card = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#DDDDDD")
        self.frame_card.pack(pady=40, padx=40, fill="both", expand=True)

        # Sessão 1: Leitura do Extrato
        self.label_instrucao = ctk.CTkLabel(self.frame_card, text="1. Importe o seu Extrato (OFX ou XLS)", font=("Open Sans", 16, "bold"), text_color="#3D71A8")
        self.label_instrucao.pack(pady=(25, 10))

        self.botao_carregar = ctk.CTkButton(
            self.frame_card, text="Selecionar Extrato (OFX / XLS)", font=("Open Sans", 14, "bold"),
            fg_color=self.cor_azul_botao, hover_color=self.cor_azul_hover, text_color="#FFFFFF",
            corner_radius=4, height=40, command=self.selecionar_arquivo
        )
        self.botao_carregar.pack(pady=5)

        self.label_arquivo = ctk.CTkLabel(self.frame_card, text="Nenhum arquivo selecionado.", font=self.fonte_padrao, text_color="#666666")
        self.label_arquivo.pack(pady=(5, 10))
        
        # Linha Divisória Horizontal
        self.frame_divisor = ctk.CTkFrame(self.frame_card, height=1, fg_color="#EEEEEE")
        self.frame_divisor.pack(fill="x", padx=20, pady=5)

        # Sessão 2: Configurações do SIGA
        self.label_instrucao2 = ctk.CTkLabel(self.frame_card, text="2. Configuração e Conexão", font=("Open Sans", 16, "bold"), text_color="#3D71A8")
        self.label_instrucao2.pack(pady=(5, 5))
        
        # Linha: Localidade (ADM - SÃO PAULO)
        self.frame_localidade = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_localidade.pack(pady=5)

        self.label_localidade = ctk.CTkLabel(self.frame_localidade, text="Localidade:", font=self.fonte_padrao, text_color="#333333")
        self.label_localidade.grid(row=0, column=0, padx=5)

        self.combo_tipo_adm = ctk.CTkComboBox(self.frame_localidade, values=["ADM", "DR", "PIA"], width=70, command=self._ao_alterar_localidade)
        self.combo_tipo_adm.grid(row=0, column=1, padx=5)
        
        self.label_hifen = ctk.CTkLabel(self.frame_localidade, text="-", font=self.fonte_padrao, text_color="#333333")
        self.label_hifen.grid(row=0, column=2)

        self.entry_nome_adm = ctk.CTkEntry(self.frame_localidade, placeholder_text="Ex: SÃO PAULO", width=180)
        self.entry_nome_adm.grid(row=0, column=3, padx=5)
        self.entry_nome_adm.bind("<FocusOut>", lambda e: self._ao_alterar_localidade())
        
        # Feedback de Auto-Preenchimento
        self.label_info_conta = ctk.CTkLabel(self.frame_card, text="Aguardando extrato para carregar contas...", font=("Open Sans", 12), text_color="#999999")
        self.label_info_conta.pack(pady=(15, 0))

        # Linha: Contas do SIGA
        self.frame_contas = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_contas.pack(pady=5)

        self.label_cc = ctk.CTkLabel(self.frame_contas, text="Conta Corrente:", font=self.fonte_padrao, text_color="#333333")
        self.label_cc.grid(row=0, column=0, padx=5, pady=5, sticky="e")
        
        self.entry_conta_corrente = ctk.CTkEntry(self.frame_contas, placeholder_text="ID do SIGA", width=100, state="disabled")
        self.entry_conta_corrente.grid(row=0, column=1, padx=5, pady=5)

        self.label_ca = ctk.CTkLabel(self.frame_contas, text="Conta Aplicação:", font=self.fonte_padrao, text_color="#333333")
        self.label_ca.grid(row=1, column=0, padx=5, pady=5, sticky="e")
        
        self.entry_conta_aplicacao = ctk.CTkEntry(self.frame_contas, placeholder_text="ID do SIGA", width=100, state="disabled")
        self.entry_conta_aplicacao.grid(row=1, column=1, padx=5, pady=5)

        self.btn_limpar_conta = ctk.CTkButton(self.frame_contas, text="Esquecer", width=60, font=("Open Sans", 11), fg_color="#F0AD4E", hover_color="#EEA236", state="disabled", command=self.limpar_contas_siga)
        self.btn_limpar_conta.grid(row=0, column=2, rowspan=2, padx=(10,0))

        # Sessão 3: Botões de Ação Final
        self.frame_botoes = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_botoes.pack(pady=(20, 10))

        self.botao_conectar = ctk.CTkButton(
            self.frame_botoes, text="Conectar ao SIGA", font=("Open Sans", 14, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", text_color="#FFFFFF",
            corner_radius=4, height=40, state="disabled", command=self.iniciar_conexao_siga
        )
        self.botao_conectar.grid(row=0, column=0, padx=5)

        self.botao_gerar_txt = ctk.CTkButton(
            self.frame_botoes, text="Gerar .TXT Ofertas", font=("Open Sans", 14, "bold"),
            fg_color="#D9534F", hover_color="#C9302C", text_color="#FFFFFF",
            corner_radius=4, height=40, state="disabled", command=self.gerar_txt_ofertas
        )
        self.botao_gerar_txt.grid(row=0, column=1, padx=5)
        
        # Barra de Status do Rodapé do Card
        self.label_status_siga = ctk.CTkLabel(self.frame_card, text="Aguardando extrato (OFX ou XLS)...", font=self.fonte_padrao, text_color="#666666")
        self.label_status_siga.pack(pady=(0, 10))

        # ==========================================
        # FOOTER (Assinatura do Software)
        # ==========================================
        self.frame_rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_rodape.pack(side="bottom", fill="x", pady=(0, 10))
        
        texto_rodape = "AutoSIGA v1.2.0 | Arquitetura MVC"
        self.label_rodape = ctk.CTkLabel(self.frame_rodape, text=texto_rodape, font=("Open Sans", 11), text_color="#999999")
        self.label_rodape.pack()

    def atualizar_status(self, texto, cor="#666666"):
        """
        Thread-safe method para atualizar a Label de status inferior.
        Usa o self.after(0) para garantir que a Thread secundária (Bot) 
        possa modificar a UI (Main Thread) sem gerar Segmentation Fault.
        """
        self.after(0, lambda: self.label_status_siga.configure(text=texto, text_color=cor))
        
    def exibir_mensagem_topo(self, tipo, titulo, mensagem):
        """
        Thread-safe method para disparar modais de alerta garantindo
        que aparecerão por cima da janela, mesmo se o programa estiver em foco.
        """
        self.attributes('-topmost', True)
        if tipo == 'info':
            messagebox.showinfo(titulo, mensagem, parent=self)
        elif tipo == 'warning':
            messagebox.showwarning(titulo, mensagem, parent=self)
        self.attributes('-topmost', False)

    def carregar_configuracoes(self):
        """Busca o model de Configurações para repopular os campos da tela."""
        tipo, nome = self.config_manager.get_geral()
        self.combo_tipo_adm.set(tipo)
        if nome:
            self.entry_nome_adm.delete(0, 'end')
            self.entry_nome_adm.insert(0, nome)

    def _ao_alterar_localidade(self, *args):
        """Acionado ao sair do campo texto de localidade para recarregar IDs de conta."""
        if self.dados_processados and "conta_id" in self.dados_processados:
            self.carregar_mapeamento_conta(self.dados_processados["conta_id"])

    def carregar_mapeamento_conta(self, conta_id):
        """Acessa o Model para preencher Conta Corrente e Aplicação no UI."""
        self.entry_conta_corrente.configure(state="normal")
        self.entry_conta_aplicacao.configure(state="normal")
        self.btn_limpar_conta.configure(state="normal")
        
        produto = self.dados_processados.get("produto") if self.dados_processados else None
        if produto:
            self.label_info_conta.configure(text=f"Mapeamento para {produto} (Conta {conta_id})", text_color="#3D71A8")
        else:
            self.label_info_conta.configure(text=f"Mapeamento para Conta Bancária Nº {conta_id}", text_color="#3D71A8")
        
        tipo_adm = self.combo_tipo_adm.get()
        nome_adm = self.entry_nome_adm.get()
        
        novo_tipo, novo_nome, dados = self.config_manager.get_mapeamento_conta(conta_id, tipo_adm, nome_adm, produto=produto)
        
        self.combo_tipo_adm.set(novo_tipo)
        self.entry_nome_adm.delete(0, 'end')
        self.entry_nome_adm.insert(0, novo_nome)
        
        self.entry_conta_corrente.delete(0, 'end')
        self.entry_conta_corrente.insert(0, dados.get("corrente", ""))
        
        self.entry_conta_aplicacao.delete(0, 'end')
        self.entry_conta_aplicacao.insert(0, dados.get("aplicacao", ""))

    def limpar_contas_siga(self):
        """Apaga a correlação salva entre o OFX e os IDs de conta internos."""
        if not self.dados_processados: return
        conta_id = self.dados_processados.get("conta_id")
        if not conta_id: return
        
        self.entry_conta_corrente.delete(0, 'end')
        self.entry_conta_aplicacao.delete(0, 'end')
        
        tipo_adm = self.combo_tipo_adm.get()
        nome_adm = self.entry_nome_adm.get()
        produto = self.dados_processados.get("produto")
        if self.config_manager.limpar_conta(conta_id, tipo_adm, nome_adm, produto=produto):
            messagebox.showinfo("Limpeza", "O lembrete das contas desta localidade foi apagado.")

    def selecionar_arquivo(self):
        """Diálogo do sistema operacional para capturar o extrato (OFX ou XLS)."""
        caminho_arquivo = filedialog.askopenfilename(
            title="Selecione o arquivo do extrato (OFX ou XLS)",
            filetypes=[
                ("Extratos Bancários", "*.ofx;*.xls;*.xlsx"),
                ("Arquivos OFX (*.ofx)", "*.ofx"),
                ("Arquivos Excel (*.xls, *.xlsx)", "*.xls;*.xlsx"),
                ("Todos os Arquivos", "*.*")
            ]
        )

        if caminho_arquivo:
            nome_arquivo = os.path.basename(caminho_arquivo)
            self.label_arquivo.configure(text=f"Arquivo selecionado:\n{nome_arquivo}", text_color="#3C763D")
            self.processar_ofx(caminho_arquivo)

    def processar_ofx(self, caminho):
        """Delega a leitura do extrato (OFX ou XLS) ao model correto e destrava os botões da UI."""
        try:
            extensao = os.path.splitext(caminho)[1].lower()
            if extensao in ['.xls', '.xlsx']:
                self.dados_processados = XlsReader.parse_file(caminho)
                tipo_desc = f"Extrato XLS ({self.dados_processados.get('produto', 'Aplicação')})"
            else:
                self.dados_processados = OfxReader.parse_file(caminho)
                tipo_desc = "Extrato OFX (Conta Corrente)"
                
            self.carregar_mapeamento_conta(self.dados_processados["conta_id"])
            
            # Libera as rotinas da UI baseando-se no tipo do extrato
            self.botao_conectar.configure(state="normal")
            
            if self.dados_processados.get("tipo_extrato") == "APLICACAO":
                # Desabilita o gerador de TXT de ofertas para extratos de aplicação
                self.botao_gerar_txt.configure(state="disabled")
                self.atualizar_status(f"{tipo_desc} lido! Pronto para conciliar no SIGA.", "#3C763D")
            else:
                self.botao_gerar_txt.configure(state="normal")
                self.atualizar_status(f"{tipo_desc} lido! Escolha uma das opções acima.", "#F89406")
                
        except Exception as e:
            self.dados_processados = None
            logging.error(f"Erro ao processar extrato: {e}")
            messagebox.showerror("Erro de Leitura", f"Não foi possível processar o extrato.\n\nDetalhes:\n{e}")

    def gerar_txt_ofertas(self):
        """Delega a geração de TXT do SIGA ao Controller Exportador."""
        if not self.dados_processados:
            messagebox.showerror("Erro", "Nenhum arquivo processado.")
            return

        nome_sugerido = f"OFERTAS_LIMPO_{self.dados_processados.get('conta_id', '1')}.txt"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=nome_sugerido,
            title="Salvar arquivo de Ofertas SIGA",
            filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")]
        )

        if filepath:
            try:
                sucesso, qtd_limpas, qtd_desc = Exportador.gerar_txt_ofertas(self.dados_processados.get("transacoes", []), filepath)
                if sucesso:
                    messagebox.showinfo("Sucesso", f"Exportação finalizada!\nOfertas Mantidas: {qtd_limpas}\nDescartadas: {qtd_desc}")
                else:
                    messagebox.showwarning("Aviso", "Não sobrou nenhuma linha de Oferta para gerar arquivo!")
            except Exception as e:
                messagebox.showerror("Erro ao Salvar", str(e))

    def iniciar_conexao_siga(self):
        """
        Valida os dados da tela e instiga a Thread de automação web.
        
        A delegação para Thread é essencial. Sem isso, o Playwright congelaria 
        totalmente a UI (Not Responding) bloqueando arrastos e cliques.
        """
        nome_adm = self.entry_nome_adm.get().strip().upper()
        if not nome_adm:
            messagebox.showwarning("Atenção", "Por favor, digite o nome da administração (ex: SÃO PAULO).")
            return
            
        corrente = self.entry_conta_corrente.get().strip()
        aplicacao = self.entry_conta_aplicacao.get().strip()
        
        is_aplicacao = (self.dados_processados.get("tipo_extrato") == "APLICACAO") if self.dados_processados else False
        
        if is_aplicacao:
            if not aplicacao:
                messagebox.showwarning("Atenção", "Por favor, preencha a 'Conta Aplicação' do SIGA para esta localidade.")
                return
        else:
            if not corrente or not aplicacao:
                messagebox.showwarning("Atenção", "Preencha a 'Conta Corrente' e a 'Conta Aplicação' do SIGA para esta localidade.")
                return
            
        tipo_adm = self.combo_tipo_adm.get()
        localidade_selecionada = f"{tipo_adm} - {nome_adm}"
        
        # Persiste a intenção do usuário para as próximas runs
        self.config_manager.salvar_geral(tipo_adm, nome_adm)
        conta_id_ofx = self.dados_processados.get("conta_id", "")
        produto = self.dados_processados.get("produto")
        self.config_manager.salvar_mapeamento_conta(conta_id_ofx, tipo_adm, nome_adm, corrente, aplicacao, produto=produto)
        
        self.dados_processados["conta_siga_corrente"] = corrente
        self.dados_processados["conta_siga_aplicacao"] = aplicacao
        
        # Bloqueia reentrância
        self.botao_conectar.configure(state="disabled")
        
        # Destrói navegador órfão antes de abrir um novo
        if getattr(self, 'bot_instance', None) and getattr(self.bot_instance, 'browser_aberto', False):
            self.atualizar_status("Encerrando janela antiga do SIGA...", "#F89406")
            self.bot_instance.fechar_browser()
            self.update()
            time.sleep(2)
            
        self.atualizar_status(f"Abrindo SIGA para {localidade_selecionada}...", "#F89406")
        
        # Mapa de callbacks (Ponte de comunicação: Bot -> UI)
        callbacks = {
            "update_status": self.atualizar_status,
            "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
            "request_authorization": lambda pend: self.after(0, lambda: self.mostrar_janela_lancamentos(pend)),
            "show_dashboard": lambda tel, t: self.after(0, lambda: self.mostrar_dashboard_produtividade(tel, t)),
            "on_finish": lambda: self.after(0, lambda: self.botao_conectar.configure(state="normal"))
        }

        # Inicializa a camada Bot com a Thread assíncrona
        self.bot_instance = SigaBot(self.dados_processados, localidade_selecionada, tipo_adm, nome_adm, callbacks)
        threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

    def mostrar_janela_lancamentos(self, lancamentos):
        """
        Janela Modal que lista visualmente todas as pendências que o robô achou.
        O robô (que está dormindo em Background) só acorda quando o usuário 
        clicar em Autorizar ou Cancelar.
        """
        janela = ctk.CTkToplevel(self)
        janela.title("Ação Necessária: Lançamentos Pendentes")
        janela.geometry("650x500")
        janela.configure(fg_color="#FFFFFF")
        janela.lift()
        janela.focus_force()
        janela.attributes('-topmost', True)
        janela.grab_set() # Foca os cliques apenas neste modal
        
        lbl_titulo = ctk.CTkLabel(janela, text=f"Lançamentos a Importar ({len(lancamentos)})", font=self.fonte_titulo, text_color=self.cor_azul_header)
        lbl_titulo.pack(pady=(20, 10))
        
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
            desc = tx.get("descricao", "")
            ctk.CTkLabel(frame_item, text=desc[:50], font=("Open Sans", 12), anchor="w").pack(side="left", padx=10, pady=5, fill="x", expand=True)
            ctk.CTkLabel(frame_item, text=valor_fmt, font=("Open Sans", 13, "bold"), text_color=cor_valor).pack(side="right", padx=15, pady=5)
            
        frame_botoes = ctk.CTkFrame(janela, fg_color="transparent")
        frame_botoes.pack(pady=15)
        
        ctk.CTkButton(frame_botoes, text="Autorizar Lançamentos", command=lambda: self.autorizar_lancamentos(janela), fg_color="#5CB85C", hover_color="#4CAE4C", height=40).pack(side="left", padx=10)
        ctk.CTkButton(frame_botoes, text="Cancelar", command=lambda: self.cancelar_lancamentos(janela), fg_color="#D9534F", hover_color="#C9302C", height=40).pack(side="right", padx=10)
        
        janela.protocol("WM_DELETE_WINDOW", lambda: self.cancelar_lancamentos(janela))

    def autorizar_lancamentos(self, janela):
        """Muda o semáforo permitindo que o Bot saia do loop e grave."""
        if self.bot_instance:
            self.bot_instance.autorizou_importacao = True
            self.bot_instance.esperando_autorizacao = False
        janela.destroy()
        
    def cancelar_lancamentos(self, janela):
        """Sinaliza aborto para que o Bot jogue a Toalha e não grave nada."""
        if self.bot_instance:
            self.bot_instance.autorizou_importacao = False
            self.bot_instance.esperando_autorizacao = False
        janela.destroy()

    def mostrar_dashboard_produtividade(self, telemetria, tempo_inicio):
        """Exibe o popup parabenizando a finalização dos trabalhos com métricas de ROI."""
        janela = ctk.CTkToplevel(self)
        janela.title("Métricas de Produtividade AutoSIGA")
        janela.geometry("520x430")
        janela.configure(fg_color="#F1F5F9")
        janela.lift()
        janela.focus_force()
        janela.attributes('-topmost', True)
        janela.grab_set()
        
        tempo_total = time.time() - tempo_inicio
        minutos = int(tempo_total // 60)
        segundos = int(tempo_total % 60)
        
        ofx_itens = telemetria.get("ofx_itens", 0)
        injecoes = telemetria.get("injecoes", 0)
        
        # Métrica de ROI Humano:
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
        
        frame = ctk.CTkFrame(janela, fg_color="#FFFFFF", corner_radius=8, border_width=1, border_color="#DDDDDD")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(frame, text="✅ Missão Cumprida!", font=("Open Sans", 22, "bold"), text_color="#3C763D").pack(pady=(15, 5))
        
        # Painel central de dados
        frame_tabela = ctk.CTkFrame(frame, fg_color="#F8F9FA", corner_radius=6)
        frame_tabela.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Auxiliar de linha
        def add_linha(label, valor, cor_valor="#333333", negrito=False):
            f_row = ctk.CTkFrame(frame_tabela, fg_color="transparent")
            f_row.pack(fill="x", padx=15, pady=4)
            font_lbl = ("Open Sans", 12)
            font_val = ("Open Sans", 12, "bold") if negrito else ("Open Sans", 12)
            
            ctk.CTkLabel(f_row, text=label, font=font_lbl, text_color="#666666").pack(side="left")
            ctk.CTkLabel(f_row, text=valor, font=font_val, text_color=cor_valor).pack(side="right")
            
        add_linha("Itens verificados no extrato:", f"{ofx_itens}")
        add_linha("Lançamentos novos efetuados:", f"{injecoes}")
        
        # Divisor
        div = ctk.CTkFrame(frame_tabela, height=1, fg_color="#E5E7EB")
        div.pack(fill="x", padx=10, pady=6)
        
        add_linha("Tempo gasto (AutoSIGA):", f"{minutos}m {segundos}s", cor_valor="#428BCA", negrito=True)
        add_linha("Tempo estimado (Manual):", f"{h_minutos}m {h_segundos}s", cor_valor="#D9534F")
        
        # Divisor de ROI
        div2 = ctk.CTkFrame(frame_tabela, height=1, fg_color="#E5E7EB")
        div2.pack(fill="x", padx=10, pady=6)
        
        # Destaca a economia de tempo
        add_linha("Tempo economizado:", f"🔥 {e_minutos}m {e_segundos}s", cor_valor="#5CB85C", negrito=True)
        
        btn_fechar = ctk.CTkButton(
            frame, text="Fechar", font=("Open Sans", 13, "bold"),
            fg_color="#428BCA", hover_color="#3071A9", height=35, width=120,
            command=janela.destroy
        )
        btn_fechar.pack(pady=(10, 15))
