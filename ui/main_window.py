"""
Módulo de Interface Gráfica (View).

Este módulo define a janela principal do AutoSIGA utilizando a biblioteca
CustomTkinter para criar uma interface moderna e agradável.
Aqui ocorre a interação humana, coleta de cliques, configuração de parâmetros
na tela e delegação das tarefas pesadas para as camadas Model, Controller e Bot.
"""

import logging
from tkinter import messagebox

import customtkinter as ctk

from models.config_manager import ConfigManager
from ui import tema
from ui.acoes_siga import AcoesSigaMixin
from ui.catalogo_siga import CatalogoSigaMixin
from ui.credenciais import CredenciaisMixin
from ui.dashboard import DashboardMixin
from ui.lote_extratos import LoteExtratosMixin
from ui.panel_energia import PanelEnergia
from version import VERSION

# Força o tema claro para combinar com a identidade visual do SIGA
ctk.set_appearance_mode("light")

class MainWindow(CredenciaisMixin, LoteExtratosMixin, AcoesSigaMixin, CatalogoSigaMixin, DashboardMixin, ctk.CTk):
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
        self.configure(fg_color=tema.FUNDO_JANELA)

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
        self.cor_laranja_logo = tema.LARANJA_LOGO
        # Azul da navbar do SIGA: branco sobre ele tem 5,7:1 (o #438EB9 antigo ficava abaixo de 4,5:1)
        self.cor_azul_header = tema.AZUL_NAVBAR

        # Inicializa a UI e restaura estado local
        self.construir_interface()

        # Verifica se há credenciais configuradas e abre a modal se ausente
        self.after(500, self.verificar_credenciais_iniciais)

    # Menor janela em que o card de extrato mostra todos os campos e botões sem cortar
    LARGURA_MINIMA = 880
    ALTURA_MINIMA = 520

    def aplicar_geometria(self):
        """
        Abre maximizado por padrão, ou restaura a janela normal se o usuário a deixou assim.

        A geometria fica em memória enquanto a janela é movida e só é gravada ao fechar
        (on_closing), para não reescrever o config.json a cada pixel arrastado.
        """
        largura_tela = self.winfo_screenwidth()
        altura_tela = self.winfo_screenheight()
        largura_util = max(640, largura_tela - 40)
        altura_util = max(440, altura_tela - 80)
        min_w = min(self.LARGURA_MINIMA, largura_util)
        min_h = min(self.ALTURA_MINIMA, altura_util)
        self.minsize(min_w, min_h)

        w = min(largura_util, max(min_w, min(1200, int(largura_tela * 0.8))))
        h = min(altura_util, max(min_h, min(900, int(altura_tela * 0.85))))
        x, y = max(0, (largura_tela - w) // 2), max(0, (altura_tela - h) // 2)
        maximizada = True

        geo_salva = self.config_manager.get_geometry()
        if isinstance(geo_salva, dict):
            # Geometria antiga (sem "maximizada") também abre maximizada: era pequena demais
            maximizada = geo_salva.get("maximizada", True)
            if not maximizada:
                w = min(largura_util, max(min_w, geo_salva.get("width", w)))
                h = min(altura_util, max(min_h, geo_salva.get("height", h)))
                pos_x, pos_y = geo_salva.get("x", x), geo_salva.get("y", y)
                if 0 <= pos_x <= largura_tela - 100:
                    x = pos_x
                if 0 <= pos_y <= altura_tela - 100:
                    y = pos_y

        self.geometry(f"{w}x{h}+{x}+{y}")
        self._geo_normal = {"width": w, "height": h, "x": x, "y": y}
        if maximizada:
            # O CustomTkinter reaplica o estado da janela ao ajustar a barra de título no Windows;
            # maximizar logo depois garante que o "zoomed" não seja desfeito.
            self.after(50, lambda: self.state("zoomed"))

        self.bind("<Configure>", self.on_configure)

    def on_configure(self, event):
        """Guarda em memória o tamanho e a posição da janela normal (não maximizada)."""
        if event.widget == self and self.state() == "normal":
            # geometry() do CTk já devolve os valores sem a escala de DPI, como o geometry() aceita
            tamanho, _, posicao = self.geometry().partition("+")
            w, _, h = tamanho.partition("x")
            x, _, y = posicao.partition("+")
            try:
                self._geo_normal = {"width": int(w), "height": int(h), "x": int(x), "y": int(y)}
            except ValueError:
                pass

    def _salvar_estado_janela(self):
        """Grava a geometria normal e se a janela estava maximizada, para a próxima abertura."""
        try:
            geo = dict(getattr(self, "_geo_normal", {}) or {})
            geo["maximizada"] = self.state() == "zoomed"
            self.config_manager.salvar_geometry(geo)
        except Exception as e:
            logging.warning(f"Não foi possível salvar o tamanho da janela: {e}")

    def on_closing(self):
        """
        Gatilho acionado quando o usuário tenta fechar o programa pelo 'X'.
        Encerra o robô (Playwright) em background antes de matar a UI.
        """
        self._salvar_estado_janela()
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
        self.frame_header = ctk.CTkFrame(self, fg_color=self.cor_azul_header, corner_radius=0, height=56)
        self.frame_header.pack(fill="x", side="top")

        self.label_chevron = ctk.CTkLabel(self.frame_header, text="> ", font=self.fonte_titulo, text_color=self.cor_laranja_logo)
        self.label_chevron.pack(side="left", padx=(20, 0), pady=10)

        self.label_titulo = ctk.CTkLabel(self.frame_header, text="AutoSIGA", font=self.fonte_titulo, text_color=tema.BRANCO)
        self.label_titulo.pack(side="left", pady=10)

        # Ação rara: botão discreto (contorno branco) para não competir com o fluxo principal
        self.btn_credenciais = ctk.CTkButton(
            self.frame_header, text="Credenciais do SIGA", font=(tema.FONTE, 12),
            fg_color="transparent", hover_color=tema.AZUL_NAVBAR_HOVER, text_color=tema.BRANCO,
            border_width=1, border_color=tema.BRANCO,
            width=140, height=30, corner_radius=4, command=self.abrir_modal_credenciais
        )
        self.btn_credenciais.pack(side="right", padx=20, pady=14)

        # ==========================================
        # FOOTER E BARRA DE STATUS (Ancorados embaixo antes da área central)
        # ==========================================
        # Status e rodapé dividem a mesma linha (status à esquerda, versão à direita)
        self.frame_rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_rodape.pack(side="bottom", fill="x", padx=16, pady=(0, 4))

        texto_rodape = f"AutoSIGA v{VERSION} · PAIRUS Soluções Tecnológicas"
        self.label_rodape = ctk.CTkLabel(self.frame_rodape, text=texto_rodape, font=(tema.FONTE, 11),
                                         text_color=tema.CINZA_TEXTO)
        self.label_rodape.pack(side="right")

        self.label_status_siga = ctk.CTkLabel(self.frame_rodape, text="Aguardando extratos ou faturas...",
                                              font=(tema.FONTE, 13, "bold"), text_color=tema.CINZA_TEXTO,
                                              anchor="w", justify="left")
        self.label_status_siga.pack(side="left", fill="x", expand=True)

        self.progress_bar = ctk.CTkProgressBar(self, width=400, height=8, corner_radius=4,
                                               progress_color=tema.VERDE_TEXTO, fg_color=tema.CINZA_BORDA)
        self.progress_bar.pack(side="bottom", pady=(2, 4))
        self.progress_bar.set(0.0)

        # ==========================================
        # MAIN TABVIEW (Alternar entre Extratos e Energia)
        # ==========================================
        self.tabview = ctk.CTkTabview(self, corner_radius=6, border_width=1, border_color=tema.CINZA_BORDA, fg_color=tema.BRANCO)
        self.tabview.pack(pady=(8, 4), padx=14, fill="both", expand=True)

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

        # Telas pequenas (notebook, 125% de escala): cada linha vertical conta. As três etapas
        # ficam numa linha só, e o botão de seleção divide a linha com o nome dos arquivos.
        frame_etapas = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        frame_etapas.pack(pady=(4, 2))
        fonte_etapa = (tema.FONTE, 13, "bold")
        self.label_instrucao = ctk.CTkLabel(frame_etapas, text="", font=fonte_etapa)
        self.label_instrucao2 = ctk.CTkLabel(frame_etapas, text="", font=fonte_etapa)
        self.label_instrucao3 = ctk.CTkLabel(frame_etapas, text="", font=fonte_etapa)
        for i, rotulo in enumerate((self.label_instrucao, self.label_instrucao2, self.label_instrucao3)):
            if i:
                ctk.CTkLabel(frame_etapas, text="›", font=fonte_etapa, text_color=tema.CINZA_TEXTO).pack(side="left", padx=8)
            rotulo.pack(side="left")

        frame_arquivos = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        frame_arquivos.pack(fill="x", padx=15, pady=(2, 4))
        self.botao_carregar = ctk.CTkButton(
            frame_arquivos, text="Selecionar extratos (OFX / XLS)   Ctrl+O", font=("Open Sans", 13, "bold"),
            fg_color=tema.AZUL_NAVBAR, hover_color=tema.AZUL_NAVBAR_HOVER, text_color=tema.BRANCO,
            corner_radius=4, height=34, command=self.selecionar_arquivo
        )
        self.botao_carregar.pack(side="left")

        self.label_arquivo = ctk.CTkLabel(frame_arquivos, text="Nenhum arquivo selecionado.", font=(tema.FONTE, 12),
                                          text_color=tema.CINZA_TEXTO, wraplength=480, justify="left", anchor="w")
        self.label_arquivo.pack(side="left", padx=(12, 0), fill="x", expand=True)
        self.construir_faixa_catalogo(self.frame_card, depois_de=frame_arquivos)

        # Sessão 3: Botões de Ação Final (ancorados no rodapé da aba antes da lista rolável)
        self.frame_botoes = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_botoes.pack(side="bottom", pady=(2, 4))

        self.frame_divisor2 = ctk.CTkFrame(self.frame_card, height=1, fg_color=tema.CINZA_DIVISOR)
        self.frame_divisor2.pack(side="bottom", fill="x", padx=15, pady=4)

        # Scrollable Frame para os Cards (expande no espaço restante entre o topo e os botões)
        self.scroll_lote = ctk.CTkScrollableFrame(self.frame_card, fg_color=tema.FUNDO_PAINEL, corner_radius=6, height=100)
        self.scroll_lote.pack(fill="both", expand=True, padx=15, pady=4)

        self.lbl_no_data = ctk.CTkLabel(self.scroll_lote, text="Carregue extratos para configurar os mapeamentos.",
                                        font=("Open Sans", 12), text_color=tema.CINZA_TEXTO)
        self.lbl_no_data.pack(pady=30)

        # Um só primário (cheio); os outros dois são secundários (contorno), sem cor que sugira perigo
        self.botao_conectar = ctk.CTkButton(
            self.frame_botoes, text="Conciliar no SIGA   Ctrl+I", font=("Open Sans", 13, "bold"),
            fg_color=tema.AZUL_NAVBAR, hover_color=tema.AZUL_NAVBAR_HOVER, text_color=tema.BRANCO,
            text_color_disabled=tema.CINZA_TEXTO,
            corner_radius=4, height=36, state="disabled", command=self.iniciar_conexao_siga
        )
        self.botao_conectar.grid(row=0, column=0, padx=5)

        secundario = dict(font=("Open Sans", 13), fg_color=tema.BRANCO, hover_color=tema.CINZA_HOVER,
                          text_color=tema.AZUL_NAVBAR, text_color_disabled=tema.CINZA_TEXTO,
                          border_width=1, border_color=tema.CINZA_BORDA, corner_radius=4, height=36)
        self.botao_gerar_txt = ctk.CTkButton(
            self.frame_botoes, text="Gerar .TXT de ofertas   Ctrl+E", state="disabled",
            command=self.gerar_txt_ofertas, **secundario
        )
        self.botao_gerar_txt.grid(row=0, column=1, padx=5)

        self.botao_importar_ofertas = ctk.CTkButton(
            self.frame_botoes, text="Importar ofertas no SIGA", state="disabled",
            command=self.iniciar_importacao_ofertas, **secundario
        )
        self.botao_importar_ofertas.grid(row=0, column=2, padx=5)

        # Baixa das provisões pagas no extrato (energia, boletos e PIX): ligada por padrão
        self.var_baixar_energia = ctk.BooleanVar(value=self.config_manager.get_baixar_energia_pelo_extrato())
        # Revisão desligada por padrão: o robô grava sozinho o que passou nas conferências do SIGA
        self.var_revisar = ctk.BooleanVar(value=self.config_manager.get_revisar_antes_de_gravar())
        # As duas opções dividem uma linha só: economiza altura em notebook
        frame_opcoes = ctk.CTkFrame(self.frame_botoes, fg_color="transparent")
        frame_opcoes.grid(row=2, column=0, columnspan=3, pady=(6, 0), sticky="w")
        ctk.CTkCheckBox(
            frame_opcoes, text="Baixar as provisões pagas no extrato (energia, boletos e PIX)",
            font=("Open Sans", 12),
            variable=self.var_baixar_energia, command=self._alternar_baixa_energia
        ).pack(side="left", padx=(5, 16))
        ctk.CTkCheckBox(
            frame_opcoes, text="Revisar antes de gravar no SIGA", font=("Open Sans", 12),
            variable=self.var_revisar,
            command=lambda: self.config_manager.salvar_revisar_antes_de_gravar(self.var_revisar.get())
        ).pack(side="left")
        self._alternar_baixa_energia(salvar=False)
        self.atualizar_etapas()

    def atualizar_status(self, texto, cor=tema.CINZA_TEXTO):
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

    def _alternar_baixa_energia(self, salvar=True):
        """Salva a opção da baixa das faturas de energia debitadas no extrato."""
        if salvar:
            self.config_manager.salvar_baixar_energia_pelo_extrato(self.var_baixar_energia.get())
