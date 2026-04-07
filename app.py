import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
from ofxparse import OfxParser

# Configuração do estilo para combinar com o SIGA
ctk.set_appearance_mode("light") 

class AutoSigaApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Mantenha referência aos dados
        self.dados_processados = None
        self.browser_aberto = False

        # Configurações da Janela
        self.title("AutoSIGA - Importação")
        self.geometry("550x550")
        self.configure(fg_color="#F1F5F9") # Fundo cinza clarinho (estilo SIGA)
        
        # Identidade Visual SIGA
        self.fonte_padrao = ("Open Sans", 14)
        self.fonte_titulo = ("Open Sans", 24, "bold")
        self.cor_azul_botao = "#428BCA"
        self.cor_azul_hover = "#3071A9"
        self.cor_laranja_logo = "#F89406"
        self.cor_azul_header = "#438EB9"

        self.construir_interface()

    def construir_interface(self):
        # 1. Header estilo SIGA
        self.frame_header = ctk.CTkFrame(self, fg_color=self.cor_azul_header, corner_radius=0, height=70)
        self.frame_header.pack(fill="x", side="top")
        
        # Logo no Header (> AutoSIGA)
        self.label_chevron = ctk.CTkLabel(self.frame_header, text="> ", font=self.fonte_titulo, text_color=self.cor_laranja_logo)
        self.label_chevron.pack(side="left", padx=(20, 0), pady=15)
        
        self.label_titulo = ctk.CTkLabel(self.frame_header, text="AutoSIGA", font=self.fonte_titulo, text_color="#FFFFFF")
        self.label_titulo.pack(side="left", pady=15)

        # 2. Card Principal
        self.frame_card = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#DDDDDD")
        self.frame_card.pack(pady=40, padx=40, fill="both", expand=True)

        self.label_instrucao = ctk.CTkLabel(self.frame_card, text="1. Importe o seu arquivo OFX", font=("Open Sans", 16, "bold"), text_color="#3D71A8")
        self.label_instrucao.pack(pady=(25, 10))

        # 3. Botão de Carregar Arquivo
        self.botao_carregar = ctk.CTkButton(
            self.frame_card, 
            text="Selecionar Arquivo OFX", 
            font=("Open Sans", 14, "bold"),
            fg_color=self.cor_azul_botao, 
            hover_color=self.cor_azul_hover,
            text_color="#FFFFFF",
            corner_radius=4,
            height=40,
            command=self.selecionar_arquivo
        )
        self.botao_carregar.pack(pady=5)

        # 4. Label para mostrar o nome do arquivo selecionado
        self.label_arquivo = ctk.CTkLabel(self.frame_card, text="Nenhum arquivo selecionado.", font=self.fonte_padrao, text_color="#666666")
        self.label_arquivo.pack(pady=(5, 20))
        
        # Divisor
        self.frame_divisor = ctk.CTkFrame(self.frame_card, height=1, fg_color="#EEEEEE")
        self.frame_divisor.pack(fill="x", padx=20, pady=10)

        # 5. Etapa de Conexão com o SIGA
        self.label_instrucao2 = ctk.CTkLabel(self.frame_card, text="2. Conexão ao Sistema", font=("Open Sans", 16, "bold"), text_color="#3D71A8")
        self.label_instrucao2.pack(pady=(10, 10))
        
        self.botao_conectar = ctk.CTkButton(
            self.frame_card, 
            text="Abrir SIGA e Fazer Login", 
            font=("Open Sans", 14, "bold"),
            fg_color="#5CB85C", # Verde
            hover_color="#4CAE4C",
            text_color="#FFFFFF",
            corner_radius=4,
            height=40,
            state="disabled", # Desabilitado até carregar o OFX
            command=self.iniciar_conexao_siga
        )
        self.botao_conectar.pack(pady=5)
        
        self.label_status_siga = ctk.CTkLabel(self.frame_card, text="Aguardando arquivo OFX...", font=self.fonte_padrao, text_color="#666666")
        self.label_status_siga.pack(pady=(5, 20))

    def atualizar_status(self, label_widget, texto, cor="#666666"):
        # Atualiza a UI a partir de threads de forma segura
        self.after(0, lambda: label_widget.configure(text=texto, text_color=cor))

    def selecionar_arquivo(self):
        caminho_arquivo = filedialog.askopenfilename(
            title="Selecione o arquivo do extrato",
            filetypes=[("Arquivos OFX", "*.ofx"), ("Todos os Arquivos", "*.*")]
        )

        if caminho_arquivo:
            nome_arquivo = os.path.basename(caminho_arquivo)
            self.atualizar_status(self.label_arquivo, f"Arquivo selecionado:\n{nome_arquivo}", "#3C763D")
            self.processar_ofx(caminho_arquivo)

    def processar_ofx(self, caminho):
        try:
            with open(caminho, 'rb') as f:
                ofx = OfxParser.parse(f)
            
            conta = ofx.account
            extrato = conta.statement
            
            dados_ofx = {
                "banco": getattr(conta, 'routing_number', ''),
                "conta_id": getattr(conta, 'account_id', ''),
                "moeda": getattr(extrato, 'currency', ''),
                "saldo_atual": float(extrato.balance) if hasattr(extrato, 'balance') else 0.0,
                "data_inicial": extrato.start_date.strftime("%d/%m/%Y") if hasattr(extrato, 'start_date') and extrato.start_date else None,
                "data_final": extrato.end_date.strftime("%d/%m/%Y") if hasattr(extrato, 'end_date') and extrato.end_date else None,
                "transacoes": []
            }
            
            for tx in extrato.transactions:
                dados_ofx["transacoes"].append({
                    "id": getattr(tx, 'id', ''),
                    "data": tx.date.strftime("%d/%m/%Y") if tx.date else '',
                    "valor": float(tx.amount) if tx.amount else 0.0,
                    "tipo": getattr(tx, 'type', ''),
                    "descricao": getattr(tx, 'memo', getattr(tx, 'payee', ''))
                })
                
            self.dados_processados = dados_ofx
            
            # Habilita a etapa 2
            self.botao_conectar.configure(state="normal")
            self.atualizar_status(self.label_status_siga, "Pronto! Clique acima para abrir o SIGA.", "#F89406")
            
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Encontramos um problema ao ler o arquivo OFX.\nDetalhe: {e}")

    def iniciar_conexao_siga(self):
        self.botao_conectar.configure(state="disabled")
        self.atualizar_status(self.label_status_siga, "Abrindo navegador... Aguarde.", "#F89406")
        # Inicia a automação em uma thread separada para não travar a interface
        threading.Thread(target=self._fluxo_automacao_siga, daemon=True).start()

    def _fluxo_automacao_siga(self):
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False) # Visível para o usuário interagir
                context = browser.new_context()
                page = context.new_page()
                
                self.atualizar_status(self.label_status_siga, "Navegador aberto! Faça o login no SIGA.", "#428BCA")
                page.goto("https://siga.congregacao.org.br/")
                
                # Aguarda até que a URL deixe de ser a URL raiz (indicando que logou e foi pra Home)
                # Como não sabemos a exata url, aguardamos que a pagina mude significativamente 
                # ou que não haja mais um botão/submit de login na tela.
                # SIGA tipicamente vai para /alguma_coisa. O timeout=0 significa esperar indefinidamente.
                page.wait_for_function('() => window.location.pathname !== "/"', timeout=0)
                
                self.atualizar_status(self.label_status_siga, "✅ Login detectado com sucesso!\nAguardando próximos passos...", "#3C763D")
                
                # Mantém o navegador aberto num loop para os próximos comandos que implementarmos depois
                while True:
                    time.sleep(1)
                    
        except Exception as e:
            self.atualizar_status(self.label_status_siga, f"Erro na automação: {e}", "#D9534F")
            self.after(0, lambda: self.botao_conectar.configure(state="normal"))


if __name__ == "__main__":
    app = AutoSigaApp()
    app.mainloop()