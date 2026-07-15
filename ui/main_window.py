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
from version import VERSION

# Força o tema claro para combinar com a identidade visual do SIGA
ctk.set_appearance_mode("light")

class CardContaExtrato(ctk.CTkFrame):
    """
    Componente visual que encapsula a exibição dos dados de um extrato
    e seus respectivos campos de mapeamento do SIGA (Localidade, C. Corrente e C. Aplicação).
    """
    def __init__(self, parent, dados_extrato, config_manager, on_change_callback):
        super().__init__(parent, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=6)
        self.dados_extrato = dados_extrato
        self.config_manager = config_manager
        self.on_change_callback = on_change_callback
        
        self.conta_id = dados_extrato.get("conta_id", "")
        self.produto = dados_extrato.get("produto")
        self.tipo_extrato = dados_extrato.get("tipo_extrato")
        self.is_aplicacao = (self.tipo_extrato == "APLICACAO")
        
        self.inicializando = True
        self.construir_widgets()
        self.carregar_mapeamento()
        self.inicializando = False

    def construir_widgets(self):
        # Nome do arquivo e Info da conta
        tipo_desc = f"Aplicação: {self.produto}" if self.is_aplicacao else "Conta Corrente"
        label_header = f"Conta Bancária: {self.conta_id} ({tipo_desc})"
        
        self.lbl_titulo = ctk.CTkLabel(self, text=label_header, font=("Open Sans", 12, "bold"), text_color="#3D71A8")
        self.lbl_titulo.grid(row=0, column=0, columnspan=5, padx=10, pady=(6, 2), sticky="w")
        
        # Grid para inputs
        # Linha 1: Localidade
        self.lbl_loc = ctk.CTkLabel(self, text="Localidade:", font=("Open Sans", 11))
        self.lbl_loc.grid(row=1, column=0, padx=5, pady=2, sticky="e")
        
        self.combo_tipo = ctk.CTkComboBox(self, values=["ADM", "DR", "PIA"], width=65, height=24, font=("Open Sans", 11))
        self.combo_tipo.grid(row=1, column=1, padx=2, pady=2, sticky="w")
        
        self.entry_nome = ctk.CTkEntry(self, placeholder_text="Ex: SÃO PAULO", width=110, height=24, font=("Open Sans", 11))
        self.entry_nome.grid(row=1, column=2, padx=2, pady=2, sticky="w")
        self.entry_nome.bind("<FocusOut>", lambda e: self.salvar_e_notificar())
        self.entry_nome.bind("<KeyRelease>", lambda e: self._forcar_maiusculo(self.entry_nome))
        self.combo_tipo.configure(command=lambda v: self.salvar_e_notificar())
        
        # Linha 2: Contas SIGA
        self.lbl_cc_ca = ctk.CTkLabel(self, text="C. Corrente / Aplicação:", font=("Open Sans", 11))
        self.lbl_cc_ca.grid(row=2, column=0, padx=5, pady=2, sticky="e")
        
        self.entry_cc = ctk.CTkEntry(self, placeholder_text="C. Corrente", width=85, height=24, font=("Open Sans", 11))
        self.entry_cc.grid(row=2, column=1, padx=2, pady=2, sticky="w")
        self.entry_cc.bind("<FocusOut>", lambda e: self.salvar_e_notificar())
        
        self.entry_ca = ctk.CTkEntry(self, placeholder_text="C. Aplicação", width=85, height=24, font=("Open Sans", 11))
        self.entry_ca.grid(row=2, column=2, padx=2, pady=2, sticky="w")
        self.entry_ca.bind("<FocusOut>", lambda e: self.salvar_e_notificar())
        
        if self.is_aplicacao:
            self.entry_cc.configure(state="disabled", placeholder_text="N/A")
            
        # Indicador de status (Badge)
        self.lbl_status = ctk.CTkLabel(self, text="Pendente", font=("Open Sans", 11, "bold"), text_color="#D9534F", width=70)
        self.lbl_status.grid(row=1, column=3, rowspan=2, padx=10, pady=2)
        
        # Botão esquecer
        self.btn_limpar = ctk.CTkButton(self, text="Limpar", width=50, height=22, font=("Open Sans", 10), fg_color="#F0AD4E", hover_color="#EEA236", command=self.limpar_mapeamento)
        self.btn_limpar.grid(row=1, column=4, rowspan=2, padx=5, pady=2)

    def _forcar_maiusculo(self, entry):
        pos = entry.index("insert")
        texto = entry.get().upper()
        entry.delete(0, "end")
        entry.insert(0, texto)
        entry.icursor(pos)

    def carregar_mapeamento(self):
        tipo_adm, nome_adm = self.config_manager.get_geral()
        novo_tipo, novo_nome, dados = self.config_manager.get_mapeamento_conta(self.conta_id, tipo_adm, nome_adm, produto=self.produto)
        
        self.combo_tipo.set(novo_tipo)
        self.entry_nome.delete(0, 'end')
        self.entry_nome.insert(0, novo_nome.upper())
        
        if not self.is_aplicacao:
            self.entry_cc.delete(0, 'end')
            self.entry_cc.insert(0, dados.get("corrente", ""))
            
        self.entry_ca.delete(0, 'end')
        self.entry_ca.insert(0, dados.get("aplicacao", ""))
        
        self.atualizar_status_visual()

    def atualizar_status_visual(self):
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip()
        cc = self.entry_cc.get().strip() if not self.is_aplicacao else "N/A"
        ca = self.entry_ca.get().strip()
        
        if nome_adm and ca and (self.is_aplicacao or cc):
            self.lbl_status.configure(text="Mapeado", text_color="#3C763D")
            self.configure(border_color="#3C763D")
        else:
            self.lbl_status.configure(text="Pendente", text_color="#D9534F")
            self.configure(border_color="#D9534F")

    def salvar_e_notificar(self):
        if getattr(self, "inicializando", False):
            return
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip().upper()
        cc = self.entry_cc.get().strip()
        ca = self.entry_ca.get().strip()
        
        self.config_manager.salvar_mapeamento_conta(
            self.conta_id, tipo_adm, nome_adm, cc, ca, produto=self.produto
        )
        
        if nome_adm:
            self.config_manager.salvar_geral(tipo_adm, nome_adm)
            
        self.atualizar_status_visual()
        if self.on_change_callback:
            self.on_change_callback()

    def limpar_mapeamento(self):
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip()
        if self.config_manager.limpar_conta(self.conta_id, tipo_adm, nome_adm, produto=self.produto):
            self.combo_tipo.set("ADM")
            self.entry_nome.delete(0, 'end')
            if not self.is_aplicacao:
                self.entry_cc.delete(0, 'end')
            self.entry_ca.delete(0, 'end')
            self.atualizar_status_visual()
            if self.on_change_callback:
                self.on_change_callback()
            messagebox.showinfo("Limpeza", f"O mapeamento da conta {self.conta_id} foi apagado.")

    def obter_dados_mapeados(self):
        tipo_adm = self.combo_tipo.get()
        nome_adm = self.entry_nome.get().strip().upper()
        cc = self.entry_cc.get().strip()
        ca = self.entry_ca.get().strip()
        
        return {
            "tipo_adm": tipo_adm,
            "nome_adm": nome_adm,
            "corrente": cc,
            "aplicacao": ca,
            "valido": bool(nome_adm and ca and (self.is_aplicacao or cc))
        }

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
        self.dados_processados_lote = []
        self.cards_lote = []
        self.bot_instance = None
        self.config_manager = ConfigManager()

        # Configurações nativas da Janela
        self.title(f"AutoSIGA v{VERSION} - Importação de Lançamentos")
        self.aplicar_geometria()
        self.configure(fg_color="#F1F5F9")
        
        # Intercepta o botão "X" da janela para fechamento gracioso
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Binds do teclado para acessibilidade (atalhos rápidos)
        self.bind("<Control-o>", self.selecionar_arquivo)
        self.bind("<Control-O>", self.selecionar_arquivo)
        self.bind("<Control-e>", lambda e: self.gerar_txt_ofertas() if self.botao_gerar_txt.cget("state") != "disabled" else None)
        self.bind("<Control-E>", lambda e: self.gerar_txt_ofertas() if self.botao_gerar_txt.cget("state") != "disabled" else None)
        self.bind("<Control-i>", lambda e: self.iniciar_conexao_siga() if self.botao_conectar.cget("state") != "disabled" else None)
        self.bind("<Control-I>", lambda e: self.iniciar_conexao_siga() if self.botao_conectar.cget("state") != "disabled" else None)
        self.bind("<Escape>", self.resetar_lote)
        
        # Paleta de Cores e Tipografia (Bootstrap Theme like)
        self.fonte_padrao = ("Open Sans", 14)
        self.fonte_titulo = ("Open Sans", 24, "bold")
        self.cor_azul_botao = "#428BCA"
        self.cor_azul_hover = "#3071A9"
        self.cor_laranja_logo = "#F89406"
        self.cor_azul_header = "#438EB9"

        # Inicializa a UI e restaura estado local
        self.construir_interface()
        
        # Verifica se há credenciais configuradas e abre a modal se ausente
        self.after(500, self.verificar_credenciais_iniciais)

    def aplicar_geometria(self):
        """
        Calcula e aplica o enquadramento ideal ou restaura a última geometria da janela.
        """
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        default_w = 600
        default_h = min(850, int(screen_height * 0.85))
        if default_h < 680:
            default_h = 680
            
        x = int((screen_width - default_w) / 2)
        y = int((screen_height - default_h) / 2)
        
        geo_salva = self.config_manager.get_geometry()
        if geo_salva:
            w = geo_salva.get("width", default_w)
            h = geo_salva.get("height", default_h)
            pos_x = geo_salva.get("x", x)
            pos_y = geo_salva.get("y", y)
            
            if pos_x < 0 or pos_x > screen_width - 100:
                pos_x = x
            if pos_y < 0 or pos_y > screen_height - 100:
                pos_y = y
            self.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
        else:
            self.geometry(f"{default_w}x{default_h}+{x}+{y}")
            
        self.bind("<Configure>", self.on_configure)

    def on_configure(self, event):
        """
        Callback para salvar a geometria da janela quando ela é movida ou redimensionada.
        """
        if event.widget == self and self.state() == "normal":
            geo = {
                "width": self.winfo_width(),
                "height": self.winfo_height(),
                "x": self.winfo_x(),
                "y": self.winfo_y()
            }
            self.config_manager.salvar_geometry(geo)

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

        self.btn_credenciais = ctk.CTkButton(
            self.frame_header, text="Credenciais 🔑", font=("Open Sans", 11, "bold"),
            fg_color="#F89406", hover_color="#DF8505", text_color="#FFFFFF",
            width=100, height=28, corner_radius=4, command=self.abrir_modal_credenciais
        )
        self.btn_credenciais.pack(side="right", padx=20, pady=21)

        # ==========================================
        # MAIN TABVIEW (Alternar entre Extratos e Energia)
        # ==========================================
        self.tabview = ctk.CTkTabview(self, corner_radius=6, border_width=1, border_color="#DDDDDD", fg_color="#FFFFFF")
        self.tabview.pack(pady=20, padx=20, fill="both", expand=True)
        
        self.tab_extratos = self.tabview.add("Conciliação de Extratos")
        self.tab_energia = self.tabview.add("Contas de Energia")

        # Configura a aba de faturas de energia
        self.panel_energia = PanelEnergia(
            self.tab_energia, 
            self.config_manager, 
            self.atualizar_status, 
            lambda topmost: self.attributes('-topmost', topmost),
            self.iniciar_importacao_energia
        )
        self.panel_energia.pack(fill="both", expand=True)

        # Sessão 1: Leitura do Extrato (Instanciado na tab de extratos)
        self.frame_card = self.tab_extratos # Redireciona a hierarquia dos widgets de extrato para a tab
        
        self.label_instrucao = ctk.CTkLabel(self.frame_card, text="1. Importe seus Extratos (OFX ou XLS)", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        self.label_instrucao.pack(pady=(15, 5))

        self.botao_carregar = ctk.CTkButton(
            self.frame_card, text="Selecionar Extratos (OFX / XLS)", font=("Open Sans", 13, "bold"),
            fg_color=self.cor_azul_botao, hover_color=self.cor_azul_hover, text_color="#FFFFFF",
            corner_radius=4, height=35, command=self.selecionar_arquivo
        )
        self.botao_carregar.pack(pady=2)

        # Campos de Filtro Manual de Datas (Intervalo opcional)
        self.frame_filtro_datas = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_filtro_datas.pack(pady=(2, 4))

        self.lbl_filtro_de = ctk.CTkLabel(self.frame_filtro_datas, text="Período Opcional: De ", font=("Open Sans", 11), text_color="#555555")
        self.lbl_filtro_de.grid(row=0, column=0, padx=2)
        
        self.entry_data_inicio = ctk.CTkEntry(self.frame_filtro_datas, placeholder_text="DD/MM/AAAA", width=95, height=22, font=("Open Sans", 11))
        self.entry_data_inicio.grid(row=0, column=1, padx=2)
        
        self.lbl_filtro_ate = ctk.CTkLabel(self.frame_filtro_datas, text=" até ", font=("Open Sans", 11), text_color="#555555")
        self.lbl_filtro_ate.grid(row=0, column=2, padx=2)
        
        self.entry_data_fim = ctk.CTkEntry(self.frame_filtro_datas, placeholder_text="DD/MM/AAAA", width=95, height=22, font=("Open Sans", 11))
        self.entry_data_fim.grid(row=0, column=3, padx=2)

        self.label_arquivo = ctk.CTkLabel(self.frame_card, text="Nenhum arquivo selecionado.", font=("Open Sans", 11), text_color="#666666", wraplength=500)
        self.label_arquivo.pack(pady=(2, 5))
        
        # Linha Divisória Horizontal
        self.frame_divisor = ctk.CTkFrame(self.frame_card, height=1, fg_color="#EEEEEE")
        self.frame_divisor.pack(fill="x", padx=15, pady=5)

        # Sessão 2: Configurações do SIGA
        self.label_instrucao2 = ctk.CTkLabel(self.frame_card, text="2. Mapeamento de Contas no SIGA", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        self.label_instrucao2.pack(pady=(2, 5))
        
        # Scrollable Frame para os Cards
        self.scroll_lote = ctk.CTkScrollableFrame(self.frame_card, fg_color="#F8F9FA", corner_radius=6, height=260)
        self.scroll_lote.pack(fill="both", expand=True, padx=15, pady=5)
        
        self.lbl_no_data = ctk.CTkLabel(self.scroll_lote, text="Carregue extratos para configurar os mapeamentos.", font=("Open Sans", 12), text_color="#999999")
        self.lbl_no_data.pack(pady=40)

        # Linha Divisória Horizontal
        self.frame_divisor2 = ctk.CTkFrame(self.frame_card, height=1, fg_color="#EEEEEE")
        self.frame_divisor2.pack(fill="x", padx=15, pady=5)

        # Sessão 3: Botões de Ação Final
        self.frame_botoes = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_botoes.pack(pady=(5, 10))

        self.botao_conectar = ctk.CTkButton(
            self.frame_botoes, text="Conectar ao SIGA", font=("Open Sans", 13, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", text_color="#FFFFFF",
            corner_radius=4, height=35, state="disabled", command=self.iniciar_conexao_siga
        )
        self.botao_conectar.grid(row=0, column=0, padx=5)

        self.botao_gerar_txt = ctk.CTkButton(
            self.frame_botoes, text="Gerar .TXT Ofertas", font=("Open Sans", 13, "bold"),
            fg_color="#D9534F", hover_color="#C9302C", text_color="#FFFFFF",
            corner_radius=4, height=35, state="disabled", command=self.gerar_txt_ofertas
        )
        self.botao_gerar_txt.grid(row=0, column=1, padx=5)
        
        # Barra de Progresso Geral do Lote
        self.progress_bar = ctk.CTkProgressBar(self, width=400, height=8, corner_radius=4, progress_color="#5CB85C", fg_color="#E0E0E0")
        self.progress_bar.pack(pady=(5, 5))
        self.progress_bar.set(0.0)
        
        # Barra de Status do Rodapé do Card
        self.label_status_siga = ctk.CTkLabel(self, text="Aguardando extratos ou faturas...", font=("Open Sans", 12), text_color="#666666")
        self.label_status_siga.pack(pady=(0, 10))

        # ==========================================
        # FOOTER (Assinatura do Software)
        # ==========================================
        self.frame_rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_rodape.pack(side="bottom", fill="x", pady=(0, 5))
        
        texto_rodape = f"AutoSIGA v{VERSION} | Arquitetura MVC"
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



    def verificar_credenciais_iniciais(self):
        """Verifica se existem credenciais salvas no Keyring ou .env. Caso contrário, abre a modal."""
        import keyring
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else None
        
        # Fallback legado de desenvolvedor .env
        usuario_env = os.getenv("SIGA_USUARIO", "")
        senha_env = os.getenv("SIGA_SENHA", "")
        
        if not (usuario and senha) and not (usuario_env and senha_env):
            self.abrir_modal_credenciais()

    def abrir_modal_credenciais(self):
        """Abre a modal de cadastro de credenciais seguras."""
        modal = ModalCredenciais(self, self.config_manager)
        modal.grab_set() # Foca a interação na modal

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

    def iniciar_conexao_siga(self, event=None):
        """
        Valida os dados de todos os cards da tela e instiga a Thread de automação web.
        """
        if not self.cards_lote:
            messagebox.showwarning("Atenção", "Nenhum extrato carregado.")
            return

        # Garante o salvamento explícito de todos os inputs inseridos nos cards antes de coletar os dados
        for card in self.cards_lote:
            card.salvar_e_notificar()

        # Coleta os filtros manuais de datas (opcionais)
        data_ini_raw = self.entry_data_inicio.get().strip()
        data_fim_raw = self.entry_data_fim.get().strip()
        
        def formatar_para_data(str_d):
            import datetime
            if not str_d:
                return None
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    return datetime.datetime.strptime(str_d, fmt).date()
                except ValueError:
                    pass
            return None

        d_ini = formatar_para_data(data_ini_raw)
        d_fim = formatar_para_data(data_fim_raw)
        
        # Alerta se o formato de data estiver incorreto
        if (data_ini_raw and not d_ini) or (data_fim_raw and not d_fim):
            messagebox.showwarning("Aviso de Formato", "As datas inseridas no filtro manual são inválidas. Use o formato DD/MM/AAAA.")
            return

        lote_valido = []
        for card in self.cards_lote:
            info = card.obter_dados_mapeados()
            if not info["valido"]:
                messagebox.showwarning("Atenção", f"O extrato da conta {card.conta_id} possui mapeamento incompleto!")
                return
                
            dados_exec = card.dados_extrato.copy()
            
            # Aplica o filtro manual de datas sobre a lista de transações se os campos forem preenchidos
            if d_ini or d_fim:
                transacoes_filtradas = []
                for tx in dados_exec.get("transacoes", []):
                    tx_date = formatar_para_data(tx.get("data", ""))
                    if not tx_date:
                        transacoes_filtradas.append(tx)
                        continue
                    if d_ini and tx_date < d_ini:
                        continue
                    if d_fim and tx_date > d_fim:
                        continue
                    transacoes_filtradas.append(tx)
                dados_exec["transacoes"] = transacoes_filtradas

            dados_exec["conta_siga_corrente"] = info["corrente"]
            dados_exec["conta_siga_aplicacao"] = info["aplicacao"]
            dados_exec["tipo_adm"] = info["tipo_adm"]
            dados_exec["nome_adm"] = info["nome_adm"]
            dados_exec["localidade_selecionada"] = f"{info['tipo_adm']} - {info['nome_adm']}"
            
            # Só adiciona extrato se houver transações remanescentes após o filtro
            if dados_exec.get("transacoes"):
                lote_valido.append(dados_exec)
                
        if not lote_valido:
            messagebox.showinfo("Lote Vazio", "Nenhum lançamento restante no lote após aplicar os filtros de datas informados.")
            return

        # Bloqueia reentrância
        self.botao_conectar.configure(state="disabled")
        
        # Destrói navegador órfão antes de abrir um novo
        if getattr(self, 'bot_instance', None) and getattr(self.bot_instance, 'browser_aberto', False):
            self.atualizar_status("Encerrando janela antiga do SIGA...", "#F89406")
            self.bot_instance.fechar_browser()
            self.update()
            time.sleep(2)
            
        self.atualizar_status("Iniciando lote de automação no SIGA...", "#F89406")
        self.progress_bar.set(0.0)
        
        callbacks = {
            "update_status": self.atualizar_status,
            "update_progress": lambda val: self.after(0, lambda: self.progress_bar.set(val)),
            "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
            "request_authorization": lambda pend: self.after(0, lambda: self.mostrar_janela_lancamentos(pend)),
            "show_dashboard": lambda tel, t: self.after(0, lambda: self.mostrar_dashboard_produtividade(tel, t)),
            "on_finish": lambda: self.after(0, lambda: self.botao_conectar.configure(state="normal"))
        }

        self.bot_instance = SigaBot(lote_valido, callbacks)
        threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

    def iniciar_importacao_energia(self):
        """
        Coleta e valida as faturas de energia e inicia a thread do SigaBot para injeção.
        """
        self.atualizar_status("Obtendo faturas de energia do e-mail...", "#428BCA")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.panel_energia.btn_importar.configure(state="disabled")

        # Roda o processamento do controller em uma thread secundária para não travar a GUI
        def rodar_thread_energia():
            try:
                from controllers.fatura_energia_controller import FaturaEnergiaController
                lote_valido, lote_pendente = FaturaEnergiaController.processar_lote_energia(self.atualizar_status)

                if not lote_valido and not lote_pendente:
                    self.atualizar_status("Nenhuma fatura a processar.", "#F89406")
                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self.panel_energia.btn_importar.configure(state="normal"))
                    return

                # Se houver UCs pendentes de mapeamento, resolvemos de forma interativa (um a um)
                if lote_pendente:
                    self.atualizar_status("Resolvendo UCs não mapeadas...", "#F89406")
                    for fat in lote_pendente:
                        resposta_codigo = [None]
                        thread_blocked = threading.Event()

                        def cb_resposta(codigo):
                            resposta_codigo[0] = codigo
                            thread_blocked.set()

                        # Abre o popup na main thread
                        uc_num = fat.get("uc", "")
                        caminho_pdf = fat.get("caminho_arquivo", "")
                        self.after(0, lambda u=uc_num, path=caminho_pdf: ModalPerguntaMapeamentoUC(self, u, self.config_manager, cb_resposta, caminho_pdf=path))
                        
                        # Espera a resposta do usuário
                        thread_blocked.wait()

                        if resposta_codigo[0]:
                            fat["localidade_codigo"] = resposta_codigo[0]
                            # Recupera o nome da localidade recém-mapeada
                            locs_dict = {l["codigo"]: l["nome"] for l in self.config_manager.get_localidades_energia()}
                            fat["localidade_nome"] = locs_dict.get(resposta_codigo[0], "DESCONHECIDA")
                            lote_valido.append(fat)
                        else:
                            self.atualizar_status(f"Fatura UC {uc_num} ignorada pelo usuário.", "#D9534F")

                if not lote_valido:
                    self.atualizar_status("Nenhuma fatura de energia restante para importar.", "#F89406")
                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self.panel_energia.btn_importar.configure(state="normal"))
                    return
            except Exception as e_thread:
                logging.error(f"Erro na thread de energia: {e_thread}", exc_info=True)
                self.atualizar_status(f"Erro: {e_thread}", "#D9534F")
                self.after(0, lambda: self.progress_bar.stop())
                self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                self.after(0, lambda: self.panel_energia.btn_importar.configure(state="normal"))
                self.after(0, lambda: messagebox.showerror("Erro", f"Ocorreu um erro ao buscar faturas: {e_thread}", parent=self))
                return

            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
            self.atualizar_status(f"Preparando importação de {len(lote_valido)} faturas no SIGA...", "#428BCA")
            
            # Formata telemetria e inicia o SigaBot no modo energia
            callbacks = {
                "update_status": self.atualizar_status,
                "update_progress": lambda val: self.after(0, lambda: self.progress_bar.set(val)),
                "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
                "request_authorization": lambda pend: self.after(0, lambda: self.mostrar_janela_lancamentos(pend)),
                "show_dashboard": lambda tel, t: self.after(0, lambda: self.mostrar_dashboard_produtividade(tel, t)),
                "on_finish": lambda: self.after(0, lambda: [
                    self.panel_energia.btn_importar.configure(state="normal"),
                    self.progress_bar.set(0.0)
                ])
            }

            # Dispara automação do SigaBot
            self.bot_instance = SigaBot(lote_valido, callbacks, tipo_lote="energia")
            threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

        threading.Thread(target=rodar_thread_energia, daemon=True).start()

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


class ModalCredenciais(ctk.CTkToplevel):
    """
    Janela modal para cadastro e edição segura de credenciais do SIGA no Keyring do Windows.
    """
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager
        
        self.title("Configurar Credenciais Seguras")
        self.geometry("380x250")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        # Centraliza na janela pai
        self.transient(parent)
        
        # Força o topo
        self.attributes("-topmost", True)
        
        self.construir_widgets()
        self.carregar_dados()
        
    def construir_widgets(self):
        # Título interno
        lbl_titulo = ctk.CTkLabel(self, text="Credenciais de Acesso ao SIGA", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        lbl_titulo.pack(pady=(15, 10))
        
        lbl_info = ctk.CTkLabel(
            self, 
            text="Sua senha será salva de forma encriptada no Windows Credential Manager.",
            font=("Open Sans", 9), text_color="#666666", wraplength=340
        )
        lbl_info.pack(pady=(0, 15))
        
        # Usuário
        self.entry_usuario = ctk.CTkEntry(self, placeholder_text="Usuário (CPF ou E-mail)", width=280, height=30, font=("Open Sans", 11))
        self.entry_usuario.pack(pady=5)
        
        # Senha
        self.entry_senha = ctk.CTkEntry(self, placeholder_text="Senha do SIGA", show="*", width=280, height=30, font=("Open Sans", 11))
        self.entry_senha.pack(pady=5)
        
        # Botões
        self.frame_botoes = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_botoes.pack(pady=20)
        
        self.btn_salvar = ctk.CTkButton(
            self.frame_botoes, text="Gravar", width=100, height=30, font=("Open Sans", 12, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", command=self.salvar_credenciais
        )
        self.btn_salvar.grid(row=0, column=0, padx=5)
        
        self.btn_cancelar = ctk.CTkButton(
            self.frame_botoes, text="Cancelar", width=100, height=30, font=("Open Sans", 12, "bold"),
            fg_color="#D9534F", hover_color="#C9302C", command=self.destroy
        )
        self.btn_cancelar.grid(row=0, column=1, padx=5)
        
    def carregar_dados(self):
        import keyring
        usuario = self.config_manager.get_usuario_siga()
        senha = keyring.get_password("AutoSIGA", usuario) if usuario else ""
        
        self.entry_usuario.insert(0, usuario)
        self.entry_senha.insert(0, senha)
        
    def salvar_credenciais(self):
        import keyring
        usuario = self.entry_usuario.get().strip()
        senha = self.entry_senha.get().strip()
        
        if not usuario or not senha:
            messagebox.showerror("Erro", "Por favor, preencha o usuário e a senha do SIGA.", parent=self)
            return
            
        try:
            # Salva o usuário no config.json
            self.config_manager.salvar_usuario_siga(usuario)
            # Salva a senha de forma encriptada no Windows Credential Manager
            keyring.set_password("AutoSIGA", usuario, senha)
            
            messagebox.showinfo("Sucesso", "Credenciais gravadas com segurança no Windows Keyring!", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro de Gravação", f"Não foi possível salvar no keyring: {e}", parent=self)


class ModalLocalidades(ctk.CTkToplevel):
    """
    Janela modal para cadastro, listagem e manutenção de Localidades da Energisa.
    """
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager

        self.title("Manutenção de Localidades")
        self.geometry("580x420")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()

        self.construir_widgets()
        self.carregar_tabela()

    def construir_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Cadastro de Localidades", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        lbl_titulo.pack(pady=10)

        # Campos de Cadastro
        frame_inputs = ctk.CTkFrame(self, fg_color="transparent")
        frame_inputs.pack(padx=20, pady=5, fill="x")

        self.entry_codigo = ctk.CTkEntry(frame_inputs, placeholder_text="Código (Ex: BR 10-0516)", width=150, height=28, font=("Open Sans", 11))
        self.entry_codigo.grid(row=0, column=0, padx=5, pady=5)

        self.entry_nome = ctk.CTkEntry(frame_inputs, placeholder_text="Descrição/Nome da Localidade", width=360, height=28, font=("Open Sans", 11))
        self.entry_nome.grid(row=0, column=1, padx=5, pady=5)

        btn_salvar = ctk.CTkButton(
            frame_inputs, text="Adicionar / Salvar", font=("Open Sans", 11, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=28, command=self.salvar_localidade
        )
        btn_salvar.grid(row=1, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # Divisor
        div = ctk.CTkFrame(self, height=1, fg_color="#EEEEEE")
        div.pack(fill="x", padx=15, pady=5)

        lbl_lista = ctk.CTkLabel(self, text="Localidades Cadastradas", font=("Open Sans", 12, "bold"), text_color="#3D71A8")
        lbl_lista.pack(pady=(5, 2))

        # Lista rolável
        self.scroll_tabela = ctk.CTkScrollableFrame(self, fg_color="#F8F9FA", corner_radius=6, height=200)
        self.scroll_tabela.pack(padx=20, pady=5, fill="both", expand=True)

    def carregar_tabela(self):
        # Limpa widgets na scrollable list
        for widget in self.scroll_tabela.winfo_children():
            widget.destroy()

        localidades = self.config_manager.get_localidades_energia()
        if not localidades:
            lbl_empty = ctk.CTkLabel(self.scroll_tabela, text="Nenhuma localidade cadastrada.", font=("Open Sans", 11), text_color="#999999")
            lbl_empty.pack(pady=40)
            return

        for idx, loc in enumerate(localidades):
            item_frame = ctk.CTkFrame(self.scroll_tabela, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=4)
            item_frame.pack(fill="x", pady=2, padx=2)

            cod = loc.get("codigo", "")
            nome = loc.get("nome", "")

            lbl_cod = ctk.CTkLabel(item_frame, text=cod, font=("Open Sans", 11, "bold"), text_color="#3D71A8", width=120, anchor="w")
            lbl_cod.pack(side="left", padx=10, pady=5)

            btn_del = ctk.CTkButton(
                item_frame, text="Excluir", font=("Open Sans", 10),
                fg_color="#D9534F", hover_color="#C9302C", width=60, height=20,
                command=lambda c=cod: self.excluir_localidade(c)
            )
            btn_del.pack(side="right", padx=10, pady=5)

            btn_edit = ctk.CTkButton(
                item_frame, text="Editar", font=("Open Sans", 10),
                fg_color="#F0AD4E", hover_color="#EC971F", width=60, height=20,
                command=lambda c=cod, n=nome: self.editar_localidade(c, n)
            )
            btn_edit.pack(side="right", padx=5, pady=5)

            lbl_nome = ctk.CTkLabel(item_frame, text=nome, font=("Open Sans", 11), anchor="w")
            lbl_nome.pack(side="left", padx=5, pady=5, fill="x", expand=True)

    def editar_localidade(self, codigo, nome):
        self.entry_codigo.delete(0, "end")
        self.entry_codigo.insert(0, codigo)
        self.entry_nome.delete(0, "end")
        self.entry_nome.insert(0, nome)

    def salvar_localidade(self):
        codigo = self.entry_codigo.get().strip().upper()
        nome = self.entry_nome.get().strip().upper()

        if not codigo or not nome:
            messagebox.showerror("Erro", "Preencha o Código e a Descrição.", parent=self)
            return

        # Padrão simples de formato "BR XX-XXXX"
        if not codigo.startswith("BR ") or len(codigo) < 8:
            messagebox.showwarning("Aviso", "O código deve seguir o padrão 'BR 10-0516'.", parent=self)

        self.config_manager.salvar_localidade_energia(codigo, nome)
        self.entry_codigo.delete(0, "end")
        self.entry_nome.delete(0, "end")
        self.carregar_tabela()
        messagebox.showinfo("Sucesso", "Localidade gravada com sucesso!", parent=self)

    def excluir_localidade(self, codigo):
        if messagebox.askyesno("Confirmar", f"Deseja excluir a localidade {codigo}?", parent=self):
            self.config_manager.remover_localidade_energia(codigo)
            self.carregar_tabela()


class ModalMapeamentoUC(ctk.CTkToplevel):
    """
    Janela modal para manutenção do mapeamento de Unidades Consumidoras para Localidades.
    """
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager

        self.title("Manutenção de UCs")
        self.geometry("580x420")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()

        self.construir_widgets()
        self.carregar_tabela()

    def construir_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Mapeamento UC -> Localidade", font=("Open Sans", 14, "bold"), text_color="#3D71A8")
        lbl_titulo.pack(pady=10)

        # Cadastro
        frame_inputs = ctk.CTkFrame(self, fg_color="transparent")
        frame_inputs.pack(padx=20, pady=5, fill="x")

        self.entry_uc = ctk.CTkEntry(frame_inputs, placeholder_text="Nº UC (Ex: 890.005.051-36)", width=170, height=28, font=("Open Sans", 11))
        self.entry_uc.grid(row=0, column=0, padx=5, pady=5)

        # Dropdown de localidades cadastradas
        localidades = self.config_manager.get_localidades_energia()
        self.combo_loc_values = [f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome'] for l in localidades]
        
        self.combo_loc = ctk.CTkComboBox(
            frame_inputs, values=self.combo_loc_values if self.combo_loc_values else ["Cadastre Localidades Primeiro"],
            width=340, height=28, font=("Open Sans", 10)
        )
        self.combo_loc.grid(row=0, column=1, padx=5, pady=5)

        btn_salvar = ctk.CTkButton(
            frame_inputs, text="Relacionar UC", font=("Open Sans", 11, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=28, command=self.salvar_mapeamento
        )
        btn_salvar.grid(row=1, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # Divisor
        div = ctk.CTkFrame(self, height=1, fg_color="#EEEEEE")
        div.pack(fill="x", padx=15, pady=5)

        lbl_lista = ctk.CTkLabel(self, text="Mapeamentos UC Existentes", font=("Open Sans", 12, "bold"), text_color="#3D71A8")
        lbl_lista.pack(pady=(5, 2))

        # Lista rolável
        self.scroll_tabela = ctk.CTkScrollableFrame(self, fg_color="#F8F9FA", corner_radius=6, height=200)
        self.scroll_tabela.pack(padx=20, pady=5, fill="both", expand=True)

    def carregar_tabela(self):
        for widget in self.scroll_tabela.winfo_children():
            widget.destroy()

        mapeamentos = self.config_manager.get_mapeamentos_uc()
        if not mapeamentos:
            lbl_empty = ctk.CTkLabel(self.scroll_tabela, text="Nenhum mapeamento de UC cadastrado.", font=("Open Sans", 11), text_color="#999999")
            lbl_empty.pack(pady=40)
            return

        for idx, m in enumerate(mapeamentos):
            item_frame = ctk.CTkFrame(self.scroll_tabela, fg_color="#FFFFFF", border_width=1, border_color="#DDDDDD", corner_radius=4)
            item_frame.pack(fill="x", pady=2, padx=2)

            uc_num = m.get("uc", "")
            loc_cod = m.get("localidade_codigo", "")

            lbl_uc = ctk.CTkLabel(item_frame, text=uc_num, font=("Open Sans", 11, "bold"), text_color="#3D71A8", width=130, anchor="w")
            lbl_uc.pack(side="left", padx=10, pady=5)

            btn_del = ctk.CTkButton(
                item_frame, text="Excluir", font=("Open Sans", 10),
                fg_color="#D9534F", hover_color="#C9302C", width=60, height=20,
                command=lambda u=uc_num: self.excluir_mapeamento(u)
            )
            btn_del.pack(side="right", padx=10, pady=5)

            localidades_dict = {l["codigo"]: l["nome"] for l in self.config_manager.get_localidades_energia()}
            loc_nome = localidades_dict.get(loc_cod, "")
            texto_loc = f"{loc_cod} - {loc_nome}" if loc_nome else loc_cod

            btn_edit = ctk.CTkButton(
                item_frame, text="Editar", font=("Open Sans", 10),
                fg_color="#F0AD4E", hover_color="#EC971F", width=60, height=20,
                command=lambda u=uc_num, ln=loc_nome: self.editar_mapeamento(u, ln)
            )
            btn_edit.pack(side="right", padx=5, pady=5)

            lbl_loc = ctk.CTkLabel(item_frame, text=texto_loc, font=("Open Sans", 11), anchor="w")
            lbl_loc.pack(side="left", padx=5, pady=5, fill="x", expand=True)

    def editar_mapeamento(self, uc, loc_nome):
        self.entry_uc.delete(0, "end")
        self.entry_uc.insert(0, uc)
        if loc_nome:
            localidades = self.config_manager.get_localidades_energia()
            for l in localidades:
                if l["nome"] == loc_nome or l["codigo"] == loc_nome:
                    comb = f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome']
                    self.combo_loc.set(comb)
                    break

    def salvar_mapeamento(self):
        uc = self.entry_uc.get().strip()
        loc_texto = self.combo_loc.get().strip()

        if not uc or not loc_texto or "Cadastre" in loc_texto:
            messagebox.showerror("Erro", "Preencha a UC e selecione uma Localidade.", parent=self)
            return

        localidades = self.config_manager.get_localidades_energia()
        codigo_loc = None
        for l in localidades:
            comb = f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome']
            if comb == loc_texto or l["nome"] == loc_texto or l["codigo"] == loc_texto:
                codigo_loc = l["codigo"]
                break

        if not codigo_loc:
            messagebox.showerror("Erro", "Localidade inválida.", parent=self)
            return

        self.config_manager.salvar_mapeamento_uc(uc, codigo_loc)
        self.entry_uc.delete(0, "end")
        self.carregar_tabela()
        messagebox.showinfo("Sucesso", "Relação gravada com sucesso!", parent=self)

    def excluir_mapeamento(self, uc):
        if messagebox.askyesno("Confirmar", f"Deseja remover o relacionamento da UC {uc}?", parent=self):
            self.config_manager.remover_mapeamento_uc(uc)
            self.carregar_tabela()


class ModalPerguntaMapeamentoUC(ctk.CTkToplevel):
    """
    Modal interativo aberto dinamicamente pelo bot para associar uma UC desconhecida.
    """
    def __init__(self, parent, uc, config_manager, callback_resposta, caminho_pdf=None):
        super().__init__(parent)
        self.parent = parent
        self.uc = uc
        self.config_manager = config_manager
        self.callback_resposta = callback_resposta
        self.caminho_pdf = caminho_pdf

        self.title("Mapear Unidade Consumidora")
        self.geometry("380x320")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")
        
        self.transient(parent)
        self.attributes("-topmost", True)
        self.grab_set()

        # Evita travamento da thread caso o usuário feche a janela pelo "X" do Windows
        self.protocol("WM_DELETE_WINDOW", self.pular)

        self.construir_widgets()

    def construir_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Nova UC Detectada!", font=("Open Sans", 14, "bold"), text_color="#D9534F")
        lbl_titulo.pack(pady=8)

        lbl_desc = ctk.CTkLabel(
            self, text=f"Deseja relacionar a Unidade Consumidora {self.uc} a alguma localidade para lançar no SIGA?",
            font=("Open Sans", 11), text_color="#333333", wraplength=320
        )
        lbl_desc.pack(pady=8)

        # Botão para visualizar nota fiscal (PDF) se houver
        if self.caminho_pdf and os.path.exists(self.caminho_pdf):
            btn_ver_nota = ctk.CTkButton(
                self, text="📄 Visualizar Fatura (Abrir PDF)", font=("Open Sans", 11, "underline"),
                fg_color="transparent", text_color="#428BCA", hover_color="#EEEEEE",
                width=280, height=25, command=self.abrir_nota
            )
            btn_ver_nota.pack(pady=5)

        # Dropdown
        localidades = self.config_manager.get_localidades_energia()
        self.localidades_list = localidades
        combo_values = [f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome'] for l in localidades]

        self.combo_loc = ctk.CTkComboBox(
            self, values=combo_values if combo_values else ["Cadastre Localidades Primeiro"],
            width=280, height=30, font=("Open Sans", 10)
        )
        self.combo_loc.pack(pady=8)

        # Botões
        frame_btn = ctk.CTkFrame(self, fg_color="transparent")
        frame_btn.pack(pady=10)

        btn_confirmar = ctk.CTkButton(
            frame_btn, text="Mapear e Lançar", font=("Open Sans", 11, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", width=140, height=35, command=self.confirmar
        )
        btn_confirmar.grid(row=0, column=0, padx=5)

        btn_pular = ctk.CTkButton(
            frame_btn, text="Ignorar Fatura", font=("Open Sans", 11, "bold"),
            fg_color="#D9534F", hover_color="#C9302C", width=110, height=35, command=self.pular
        )
        btn_pular.grid(row=0, column=1, padx=5)

    def abrir_nota(self):
        if self.caminho_pdf and os.path.exists(self.caminho_pdf):
            try:
                os.startfile(self.caminho_pdf)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o PDF: {e}", parent=self)

    def confirmar(self):
        loc_txt = self.combo_loc.get().strip()
        if "Cadastre" in loc_txt or not loc_txt:
            messagebox.showerror("Erro", "Selecione uma localidade válida.", parent=self)
            return

        codigo_loc = None
        for l in self.localidades_list:
            comb = f"{l['codigo']} - {l['nome']}" if l['codigo'] != l['nome'] else l['nome']
            if comb == loc_txt or l["nome"] == loc_txt or l["codigo"] == loc_txt:
                codigo_loc = l["codigo"]
                break

        if not codigo_loc:
            messagebox.showerror("Erro", "Localidade inválida.", parent=self)
            return

        self.config_manager.salvar_mapeamento_uc(self.uc, codigo_loc)
        
        self.callback_resposta(codigo_loc)
        self.destroy()

    def pular(self):
        self.callback_resposta(None)
        self.destroy()


class PanelEnergia(ctk.CTkFrame):
    """
    Aba dedicada para configuração, controle de e-mail e cadastro das Localidades da Energisa.
    """
    def __init__(self, parent, config_manager, callback_log, callback_topmost, trigger_bot_callback):
        super().__init__(parent, fg_color="#FFFFFF")
        self.config_manager = config_manager
        self.callback_log = callback_log
        self.callback_topmost = callback_topmost
        self.trigger_bot_callback = trigger_bot_callback

        self.construir_widgets()
        self.carregar_dados()

    def construir_widgets(self):
        # Título
        lbl_tit = ctk.CTkLabel(self, text="Provisionamento Automático de Energia (Energisa)", font=("Open Sans", 13, "bold"), text_color="#3D71A8")
        lbl_tit.pack(pady=(10, 5))

        # Configurações do E-mail (Grid)
        frame_config = ctk.CTkFrame(self, fg_color="#F8F9FA", border_width=1, border_color="#DDDDDD", corner_radius=6)
        frame_config.pack(padx=15, pady=5, fill="x")

        ctk.CTkLabel(frame_config, text="E-mail (Gmail):", font=("Open Sans", 11)).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.entry_email = ctk.CTkEntry(frame_config, placeholder_text="ccbdourados@gmail.com", width=250, height=24, font=("Open Sans", 11))
        self.entry_email.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(frame_config, text="Mês de Corte:", font=("Open Sans", 11)).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.entry_corte = ctk.CTkEntry(frame_config, placeholder_text="MM/AAAA (Ex: 06/2026)", width=130, height=24, font=("Open Sans", 11))
        self.entry_corte.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        btn_save_cfg = ctk.CTkButton(
            frame_config, text="Salvar Configuração 💾", font=("Open Sans", 11, "bold"),
            fg_color="#428BCA", hover_color="#3071A9", width=150, height=24, command=self.salvar_dados_email
        )
        btn_save_cfg.grid(row=1, column=2, padx=5, pady=5, sticky="e")

        # Cadastro de Tabelas (Localidades e UCs)
        frame_tabelas = ctk.CTkFrame(self, fg_color="transparent")
        frame_tabelas.pack(padx=15, pady=10, fill="x")

        self.btn_locs = ctk.CTkButton(
            frame_tabelas, text="Cadastrar Localidades 🏢", font=("Open Sans", 12, "bold"),
            fg_color="#F89406", hover_color="#DF8505", height=32, command=self.abrir_localidades
        )
        self.btn_locs.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_ucs = ctk.CTkButton(
            frame_tabelas, text="Mapear UCs 🔌", font=("Open Sans", 12, "bold"),
            fg_color="#F89406", hover_color="#DF8505", height=32, command=self.abrir_ucs
        )
        self.btn_ucs.pack(side="right", fill="x", expand=True, padx=5)

        # Botão Importar Faturas
        self.btn_importar = ctk.CTkButton(
            self, text="⚡ BUSCAR E LANÇAR CONTAS DE ENERGIA ⚡", font=("Open Sans", 13, "bold"),
            fg_color="#5CB85C", hover_color="#4CAE4C", height=40, command=self.iniciar_importacao_energia
        )
        self.btn_importar.pack(padx=15, pady=15, fill="x")

    def carregar_dados(self):
        cfg = self.config_manager.get_email_config()
        self.entry_email.insert(0, cfg.get("email", ""))
        self.entry_corte.insert(0, cfg.get("mes_corte", ""))

    def salvar_dados_email(self):
        email_str = self.entry_email.get().strip()
        corte_str = self.entry_corte.get().strip()

        if not email_str:
            messagebox.showerror("Erro", "Informe o e-mail do Gmail.", parent=self)
            return

        self.config_manager.salvar_email_config(email_str, "imap.gmail.com", corte_str)

        messagebox.showinfo("Sucesso", "Configurações de energia gravadas com sucesso!", parent=self)

    def abrir_localidades(self):
        ModalLocalidades(self.winfo_toplevel(), self.config_manager)

    def abrir_ucs(self):
        ModalMapeamentoUC(self.winfo_toplevel(), self.config_manager)

    def iniciar_importacao_energia(self):
        self.trigger_bot_callback()


