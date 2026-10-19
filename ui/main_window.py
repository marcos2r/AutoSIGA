"""
Módulo de Interface Gráfica (View).

Este módulo define a janela principal do AutoSIGA utilizando a biblioteca
CustomTkinter para criar uma interface moderna e agradável. 
Aqui ocorre a interação humana, coleta de cliques, configuração de parâmetros
na tela e delegação das tarefas pesadas para as camadas Model, Controller e Bot.
"""

import customtkinter as ctk
from tkinter import messagebox
from models.config_manager import ConfigManager
from version import VERSION
from ui.panel_energia import PanelEnergia
from ui.credenciais import CredenciaisMixin
from ui.lote_extratos import LoteExtratosMixin
from ui.acoes_siga import AcoesSigaMixin
from ui.dashboard import DashboardMixin


# Força o tema claro para combinar com a identidade visual do SIGA
ctk.set_appearance_mode("light")

class MainWindow(CredenciaisMixin, LoteExtratosMixin, AcoesSigaMixin, DashboardMixin, ctk.CTk):
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

        self.botao_importar_ofertas = ctk.CTkButton(
            self.frame_botoes, text="Importar Ofertas no SIGA", font=("Open Sans", 13, "bold"),
            fg_color="#428BCA", hover_color="#3071A9", text_color="#FFFFFF",
            corner_radius=4, height=35, state="disabled", command=self.iniciar_importacao_ofertas
        )
        self.botao_importar_ofertas.grid(row=0, column=2, padx=5)
        
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
