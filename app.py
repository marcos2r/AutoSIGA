import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import json
from ofxparse import OfxParser

# Configuração do estilo para combinar com o SIGA
ctk.set_appearance_mode("light") 

class AutoSigaApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Mantenha referência aos dados
        self.dados_processados = None
        self.browser_aberto = False
        self.localidade_selecionada = ""

        # Configurações da Janela
        self.title("AutoSIGA - Importação")
        self.geometry("600x680")
        self.configure(fg_color="#F1F5F9") # Fundo cinza clarinho (estilo SIGA)
        
        # Identidade Visual SIGA
        self.fonte_padrao = ("Open Sans", 14)
        self.fonte_titulo = ("Open Sans", 24, "bold")
        self.cor_azul_botao = "#428BCA"
        self.cor_azul_hover = "#3071A9"
        self.cor_laranja_logo = "#F89406"
        self.cor_azul_header = "#438EB9"

        self.construir_interface()
        self.carregar_configuracoes()

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
        self.label_arquivo.pack(pady=(5, 10))
        
        # Divisor
        self.frame_divisor = ctk.CTkFrame(self.frame_card, height=1, fg_color="#EEEEEE")
        self.frame_divisor.pack(fill="x", padx=20, pady=5)

        # 5. Etapa de Conexão com o SIGA
        self.label_instrucao2 = ctk.CTkLabel(self.frame_card, text="2. Configuração e Conexão", font=("Open Sans", 16, "bold"), text_color="#3D71A8")
        self.label_instrucao2.pack(pady=(5, 5))
        
        # --- Configuração da Localidade ---
        self.frame_localidade = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_localidade.pack(pady=5)

        self.label_localidade = ctk.CTkLabel(self.frame_localidade, text="Localidade:", font=self.fonte_padrao, text_color="#333333")
        self.label_localidade.grid(row=0, column=0, padx=5)

        self.combo_tipo_adm = ctk.CTkComboBox(self.frame_localidade, values=["ADM", "DR", "PIA"], width=70)
        self.combo_tipo_adm.grid(row=0, column=1, padx=5)
        
        self.label_hifen = ctk.CTkLabel(self.frame_localidade, text="-", font=self.fonte_padrao, text_color="#333333")
        self.label_hifen.grid(row=0, column=2)

        self.entry_nome_adm = ctk.CTkEntry(self.frame_localidade, placeholder_text="Ex: SÃO PAULO", width=180)
        self.entry_nome_adm.grid(row=0, column=3, padx=5)
        
        # --- Configuração das Contas SIGA ---
        self.frame_contas = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_contas.pack(pady=5)
        
        self.label_info_conta = ctk.CTkLabel(self.frame_contas, text="Conta do arquivo OFX não carregada.", font=("Open Sans", 12, "italic"), text_color="#AAAAAA")
        self.label_info_conta.grid(row=0, column=0, columnspan=2, pady=(0,5))
        
        ctk.CTkLabel(self.frame_contas, text="Conta Corrente (SIGA):", font=self.fonte_padrao, text_color="#333333").grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.entry_conta_corrente = ctk.CTkEntry(self.frame_contas, width=150, placeholder_text="Ex: 12345-6")
        self.entry_conta_corrente.grid(row=1, column=1, padx=5, pady=2)

        ctk.CTkLabel(self.frame_contas, text="Conta Aplicação (SIGA):", font=self.fonte_padrao, text_color="#333333").grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self.entry_conta_aplicacao = ctk.CTkEntry(self.frame_contas, width=150, placeholder_text="Ex: 54321-0")
        self.entry_conta_aplicacao.grid(row=2, column=1, padx=5, pady=2)
        
        self.btn_limpar_conta = ctk.CTkButton(self.frame_contas, text="Limpar Lembrete", font=("Open Sans", 11), fg_color="#D9534F", hover_color="#C9302C", width=100, height=24, command=self.limpar_contas_siga)
        self.btn_limpar_conta.grid(row=3, column=0, columnspan=2, pady=5)
        
        # Inicialmente desabilitados
        self.entry_conta_corrente.configure(state="disabled")
        self.entry_conta_aplicacao.configure(state="disabled")
        self.btn_limpar_conta.configure(state="disabled")
        # ----------------------------------------
        
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
        self.botao_conectar.pack(pady=10)
        
        self.label_status_siga = ctk.CTkLabel(self.frame_card, text="Aguardando arquivo OFX...", font=self.fonte_padrao, text_color="#666666")
        self.label_status_siga.pack(pady=(0, 10))

    def atualizar_status(self, label_widget, texto, cor="#666666"):
        # Atualiza a UI a partir de threads de forma segura
        self.after(0, lambda: label_widget.configure(text=texto, text_color=cor))
        
    def get_config_data(self):
        caminho = "config.json"
        if os.path.exists(caminho):
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config_data(self, data):
        caminho = "config.json"
        try:
            with open(caminho, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")

    def carregar_configuracoes(self):
        config = self.get_config_data()
        tipo = config.get("tipo_adm", "ADM")
        nome = config.get("nome_adm", "")
        self.combo_tipo_adm.set(tipo)
        if nome:
            self.entry_nome_adm.delete(0, 'end')
            self.entry_nome_adm.insert(0, nome)

    def salvar_configuracoes_gerais(self, tipo_adm, nome_adm):
        config = self.get_config_data()
        config["tipo_adm"] = tipo_adm
        config["nome_adm"] = nome_adm
        self.save_config_data(config)

    def carregar_mapeamento_conta(self, conta_id):
        self.entry_conta_corrente.configure(state="normal")
        self.entry_conta_aplicacao.configure(state="normal")
        self.btn_limpar_conta.configure(state="normal")
        
        self.label_info_conta.configure(text=f"Mapeamento para Conta OFX Nº {conta_id}", text_color="#3D71A8")
        
        config = self.get_config_data()
        mapeamentos = config.get("contas_mapeadas", {})
        dados = mapeamentos.get(conta_id, {"corrente": "", "aplicacao": ""})
        
        self.entry_conta_corrente.delete(0, 'end')
        self.entry_conta_corrente.insert(0, dados.get("corrente", ""))
        
        self.entry_conta_aplicacao.delete(0, 'end')
        self.entry_conta_aplicacao.insert(0, dados.get("aplicacao", ""))

    def salvar_mapeamento_conta(self, conta_id, corrente, aplicacao):
        config = self.get_config_data()
        if "contas_mapeadas" not in config:
            config["contas_mapeadas"] = {}
            
        config["contas_mapeadas"][conta_id] = {
            "corrente": corrente,
            "aplicacao": aplicacao
        }
        self.save_config_data(config)

    def limpar_contas_siga(self):
        if not self.dados_processados: return
        conta_id = self.dados_processados.get("conta_id")
        if not conta_id: return
        
        self.entry_conta_corrente.delete(0, 'end')
        self.entry_conta_aplicacao.delete(0, 'end')
        
        config = self.get_config_data()
        if "contas_mapeadas" in config and conta_id in config["contas_mapeadas"]:
            del config["contas_mapeadas"][conta_id]
            self.save_config_data(config)
            
        messagebox.showinfo("Limpeza", "O lembrete dessas contas apagadas.")

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
            
            # Habilita a etapa 2 e carrega mapeamentos de conta vinculados a esse OFX
            self.carregar_mapeamento_conta(dados_ofx["conta_id"])
            self.botao_conectar.configure(state="normal")
            self.atualizar_status(self.label_status_siga, "Pronto! Preencha as informações e abra o SIGA.", "#F89406")
            
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Encontramos um problema ao ler o arquivo OFX.\nDetalhe: {e}")

    def iniciar_conexao_siga(self):
        nome_adm = self.entry_nome_adm.get().strip().upper()
        if not nome_adm:
            messagebox.showwarning("Atenção", "Por favor, digite o nome da administração (ex: SÃO PAULO).")
            return
            
        corrente = self.entry_conta_corrente.get().strip()
        aplicacao = self.entry_conta_aplicacao.get().strip()
        
        if not corrente or not aplicacao:
            messagebox.showwarning("Atenção", "Preencha a 'Conta Corrente' e a 'Conta Aplicação' do SIGA para efetuarmos os lançamentos ali.")
            return
            
        tipo_adm = self.combo_tipo_adm.get()
        self.localidade_selecionada = f"{tipo_adm} - {nome_adm}"
        
        # Salva para a proxima vez (Administração e Contas)
        self.salvar_configuracoes_gerais(tipo_adm, nome_adm)
        
        conta_id_ofx = self.dados_processados.get("conta_id", "")
        self.salvar_mapeamento_conta(conta_id_ofx, corrente, aplicacao)
        
        # Armazena os números das contas SIGA prontas para uso nos próximos passos
        self.dados_processados["conta_siga_corrente"] = corrente
        self.dados_processados["conta_siga_aplicacao"] = aplicacao
        
        self.botao_conectar.configure(state="disabled")
        self.atualizar_status(self.label_status_siga, f"Abrindo SIGA para {self.localidade_selecionada}...", "#F89406")
        
        # Inicia a automação em uma thread separada para não travar a interface
        threading.Thread(target=self._fluxo_automacao_siga, daemon=True).start()

    def _fluxo_automacao_siga(self):
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                # 1. Usar modo "Persistente" para salvar os cookies e sessão do usuário na pasta local
                data_dir = os.path.join(os.getcwd(), 'siga_browser_data')
                
                context = p.chromium.launch_persistent_context(
                    user_data_dir=data_dir,
                    headless=False,
                    no_viewport=True # Permite a janela abrir em tamanhos padronizados do OS
                )
                
                # No modo persistente, uma guia já vem previamente aberta
                page = context.pages[0] if context.pages else context.new_page()
                
                self.atualizar_status(self.label_status_siga, f"Iniciando navegador e validando sessão...", "#428BCA")
                page.goto("https://siga.congregacao.org.br/")
                
                # Aguarda o html estrutural carregar
                page.wait_for_load_state("domcontentloaded")
                
                # 2. Lógica para detectar se o usuário já possui cookies válidos de outra sessão
                # O input type="password" é um padrão universal da página de login não autenticada
                try:
                    # Dá 3 segundos no máximo para a box de senha aparecer; se não aparecer, é pq já pulou de tela (logado)
                    senha_locator = page.locator('input[type="password"]')
                    senha_locator.wait_for(state="visible", timeout=3000)
                    precisa_fazer_login = True
                except:
                    precisa_fazer_login = False
                
                if precisa_fazer_login:
                    self.atualizar_status(self.label_status_siga, f"Sessão não detectada.\nFaça o login na janela aberta...", "#F89406")
                    # Congela o loop até que a box de senha não seja mais visível na página (ex: clicou em Entrar)
                    senha_locator.wait_for(state="hidden", timeout=0)
                
                # A partir desse ponto sabemos que o sistema autenticou e trocou de tela
                self.atualizar_status(self.label_status_siga, f"Sessão Validada. Verificando localidade...", "#428BCA")
                
                # Aguarda o elemento de perfil carregar no menu superior (indica que a home carregou por completo)
                page.locator('.informacao-local').first.wait_for(state="visible", timeout=15000)
                
                # Encontra todas as localidades no dropdown (mesmo oculto)
                locais_locator = page.locator('ul#dropdown_localidades > li')
                locais_locator.first.wait_for(state="attached", timeout=10000)
                
                quantidade = locais_locator.count()
                precisa_trocar = True
                linha_alvo = None
                
                tipo_alvo = self.combo_tipo_adm.get().upper()
                nome_alvo = self.entry_nome_adm.get().strip().upper()
                
                for i in range(quantidade):
                    li = locais_locator.nth(i)
                    texto_li = li.text_content().upper()
                    
                    if tipo_alvo in texto_li and nome_alvo in texto_li:
                        linha_alvo = li
                        classe_li = li.get_attribute("class") or ""
                        if "active" in classe_li.lower():
                            precisa_trocar = False
                        break
                        
                if not linha_alvo:
                    # Se não achou na lista
                    self.atualizar_status(self.label_status_siga, f"⚠️ Localidade '{self.localidade_selecionada}' não encontrada no seu menu!", "#D9534F")
                else:
                    if precisa_trocar:
                        self.atualizar_status(self.label_status_siga, f"Trocando perfil do SIGA para {self.localidade_selecionada}...", "#F89406")
                        # Realiza o clique no link daquela localidade forçando pois o menu pode estar fechado/invisivel
                        linha_alvo.locator('a').click(force=True)
                        page.wait_for_load_state("domcontentloaded")
                        time.sleep(2) # Aguarda atualizar a página da nova localidade
                    
                # 4. Verificação do Mês de Trabalho (Competência)
                self.atualizar_status(self.label_status_siga, f"Verificando Mês de Trabalho...", "#428BCA")
                data_final_ofx = self.dados_processados.get("data_final", "")
                
                if data_final_ofx and len(data_final_ofx) == 10: # No formato DD/MM/YYYY
                    mes_ano_alvo = data_final_ofx[3:] # Ex: captura "02/2026" de "28/02/2026"
                    
                    mes_trabalho_locator = page.locator('#f_competencianome')
                    if mes_trabalho_locator.count() > 0:
                        mes_trabalho_atual = mes_trabalho_locator.text_content().strip()
                        
                        if mes_trabalho_atual != mes_ano_alvo:
                            self.atualizar_status(self.label_status_siga, f"Trocando Mês de {mes_trabalho_atual} para {mes_ano_alvo}...", "#F89406")
                            link_mes = page.locator(f'a.f_competencia_master:has-text("{mes_ano_alvo}")')
                            
                            if link_mes.count() > 0:
                                link_mes.first.click(force=True)
                                page.wait_for_load_state("domcontentloaded")
                                time.sleep(2) # Aguarda página recarregar com novo mês
                            else:
                                self.atualizar_status(self.label_status_siga, f"⚠️ Mês {mes_ano_alvo} precisa ser trocado manualmente!", "#D9534F")
                                time.sleep(3) # Pausa pro usuario ler e poder agir
                                
                self.atualizar_status(self.label_status_siga, f"✅ Pronto e Logado em: {self.localidade_selecionada}", "#3C763D")
                    
                # Mantém o navegador aberto num loop
                while True:
                    time.sleep(1)
                    
        except Exception as e:
            # Esses Print/Errors silenciam se o usuário apenas fechar a janela 
            self.atualizar_status(self.label_status_siga, f"Sessão no navegador finalizada.", "#F89406")
            self.after(0, lambda: self.botao_conectar.configure(state="normal"))

if __name__ == "__main__":
    app = AutoSigaApp()
    app.mainloop()