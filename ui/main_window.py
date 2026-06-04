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
        self.title("AutoSIGA v1.2.1 - Importação de Lançamentos")
        self.aplicar_geometria()
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

        # ==========================================
        # MAIN CARD (Corpo Central Branco)
        # ==========================================
        self.frame_card = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#DDDDDD")
        self.frame_card.pack(pady=20, padx=20, fill="both", expand=True)

        # Sessão 1: Leitura do Extrato
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
        self.progress_bar = ctk.CTkProgressBar(self.frame_card, width=400, height=8, corner_radius=4, progress_color="#5CB85C", fg_color="#E0E0E0")
        self.progress_bar.pack(pady=(5, 5))
        self.progress_bar.set(0.0)
        
        # Barra de Status do Rodapé do Card
        self.label_status_siga = ctk.CTkLabel(self.frame_card, text="Aguardando extratos (OFX ou XLS)...", font=("Open Sans", 12), text_color="#666666")
        self.label_status_siga.pack(pady=(0, 10))

        # ==========================================
        # FOOTER (Assinatura do Software)
        # ==========================================
        self.frame_rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_rodape.pack(side="bottom", fill="x", pady=(0, 5))
        
        texto_rodape = "AutoSIGA v1.2.1 | Arquitetura MVC"
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



    def selecionar_arquivo(self):
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

    def gerar_txt_ofertas(self):
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

    def iniciar_conexao_siga(self):
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
        
        tempo_total = time.time() - tempo_inicio
        minutos = int(tempo_total // 60)
        segundos = int(tempo_total % 60)
        
        ofx_itens = telemetria.get("ofx_itens", 0)
        injecoes = telemetria.get("injecoes", 0)
        total_contas = telemetria.get("total_contas", 1)
        volume_fin = telemetria.get("volume_financeiro", 0.0)
        pendentes = telemetria.get("pendentes", 0)
        
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
        
        # ROI Financeiro (Tarifa de R$ 30,00/hora de trabalho administrativo)
        roi_financeiro = (economia_segundos / 3600.0) * 30.0
        
        # Taxa de Assertividade
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

