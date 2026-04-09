import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import json
import logging
from ofxparse import OfxParser

# Configuração de Logs Globais
logging.basicConfig(
    filename='autosiga.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

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
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Identidade Visual SIGA
        self.fonte_padrao = ("Open Sans", 14)
        self.fonte_titulo = ("Open Sans", 24, "bold")
        self.cor_azul_botao = "#428BCA"
        self.cor_azul_hover = "#3071A9"
        self.cor_laranja_logo = "#F89406"
        self.cor_azul_header = "#438EB9"

        self.construir_interface()
        self.carregar_configuracoes()

    def on_closing(self):
        self.browser_aberto = False
        self.after(500, self.destroy)

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
        
        # --- Botões de Ação Principais ---
        self.frame_botoes_acao = ctk.CTkFrame(self.frame_card, fg_color="transparent")
        self.frame_botoes_acao.pack(pady=10)
        
        self.botao_conectar = ctk.CTkButton(
            self.frame_botoes_acao, 
            text="Inserir Investimentos no SIGA", 
            font=("Open Sans", 13, "bold"),
            fg_color="#5CB85C", # Verde
            hover_color="#4CAE4C",
            text_color="#FFFFFF",
            corner_radius=4,
            height=40,
            state="disabled", # Desabilitado até carregar o OFX
            command=self.iniciar_conexao_siga
        )
        self.botao_conectar.grid(row=0, column=0, padx=5)

        self.botao_gerar_txt = ctk.CTkButton(
            self.frame_botoes_acao, 
            text="Gerar TXT Ofertas", 
            font=("Open Sans", 13, "bold"),
            fg_color="#0275D8", # Azul
            hover_color="#025AA5",
            text_color="#FFFFFF",
            corner_radius=4,
            height=40,
            state="disabled",
            command=self.gerar_txt_ofertas
        )
        self.botao_gerar_txt.grid(row=0, column=1, padx=5)
        
        self.label_status_siga = ctk.CTkLabel(self.frame_card, text="Aguardando arquivo OFX...", font=self.fonte_padrao, text_color="#666666")
        self.label_status_siga.pack(pady=(0, 10))

    def atualizar_status(self, label_widget, texto, cor="#666666"):
        # Atualiza a UI a partir de threads de forma segura
        logging.info(f"[STATUS] {texto}")
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
            self.botao_gerar_txt.configure(state="normal")
            self.atualizar_status(self.label_status_siga, "Extrato lido! Escolha uma das opções acima.", "#F89406")
            
        except Exception as e:
            self.dados_processados = None
            logging.error(f"Erro ao ler OFX: {e}")
            messagebox.showerror("Erro de Leitura", f"Não foi possível processar o arquivo OFX.\n\nDetalhes:\n{e}")

    def conciliar_extratos(self):
        if not self.dados_processados or "extrato_siga" not in self.dados_processados:
            return []
            
        ofx_txs = self.dados_processados.get("transacoes", [])
        siga_txs_raw = self.dados_processados.get("extrato_siga", [])
        
        siga_txs = []
        for entry in siga_txs_raw:
            val_str = entry.get('entrada', '-').strip()
            is_saida = False
            if val_str == '-':
                val_str = entry.get('saida', '-').strip()
                is_saida = True
                
            if not val_str or val_str == '-':
                continue
                
            try:
                # Transforma 3.000,00 ou 150,00 em float
                val_float = float(val_str.replace('.', '').replace(',', '.'))
                if is_saida:
                    val_float = -abs(val_float)
                else:
                    val_float = abs(val_float)
                    
                siga_txs.append({
                    'data': entry.get('data', '').strip(),
                    'valor': val_float,
                    'matched': False
                })
            except Exception as e:
                logging.error(f"Erro ao converter valor do SIGA: {val_str} - {e}")
                
        # Procura quais itens do OFX não existem no SIGA
        a_lancar = []
        
        # Filtro: nesta primeira versão, consideramos apenas transações de investimento/resgate
        kw_investimentos = ['APLIC', 'RESG', 'RDC', 'CDB', 'POUP', 'INVEST']
        
        for tx in ofx_txs:
            tx_data = tx.get("data", "")
            tx_valor = tx.get("valor", 0.0)
            tx_desc = tx.get("descricao", "").upper()
            
            # Checa se a transação é de aplicação/resgate
            eh_investimento = any(kw in tx_desc for kw in kw_investimentos)
            if not eh_investimento:
                continue # Ignora transferências, PIX e depósitos comuns
            
            matched = False
            for stx in siga_txs:
                if not stx['matched'] and stx['data'] == tx_data:
                    # Tolerância de 1 centavo para problemas de float
                    if abs(stx['valor'] - tx_valor) <= 0.01:
                        stx['matched'] = True
                        matched = True
                        break
            
            if not matched: # Não achou correspondência no SIGA
                a_lancar.append(tx)
                
        return a_lancar

    def mostrar_janela_lancamentos(self, lancamentos):
        janela = ctk.CTkToplevel(self)
        janela.title("Prévia de Importação")
        janela.geometry("650x500")
        janela.transient(self) # Fica por cima da main
        janela.attributes('-topmost', True) # Fica por cima do Windows/Navegador
        janela.grab_set() # Foca os cliques nela
        
        lbl_titulo = ctk.CTkLabel(janela, text=f"Lançamentos a Importar ({len(lancamentos)})", font=self.fonte_titulo, text_color=self.cor_azul_header)
        lbl_titulo.pack(pady=(20, 10))
        
        lbl_sub = ctk.CTkLabel(janela, text="Estes são os registros do OFX que não foram encontrados no SIGA e estão prontos para descer pro sistema.", font=self.fonte_padrao, text_color="#777")
        lbl_sub.pack(pady=(0, 15))
        
        frame_scroll = ctk.CTkScrollableFrame(janela, width=600, height=300, fg_color="#F8F9FA", corner_radius=6)
        frame_scroll.pack(padx=20, pady=10, fill="both", expand=True)
        
        for tx in lancamentos:
            frame_item = ctk.CTkFrame(frame_scroll, fg_color="#FFFFFF", corner_radius=4, border_width=1, border_color="#DDDDDD")
            frame_item.pack(fill="x", pady=5, padx=5)
            
            data = tx.get("data", "")
            valor = tx.get("valor", 0.0)
            desc = tx.get("descricao", "")
            
            cor_valor = "#3C763D" if valor >= 0 else "#D9534F"
            valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            lbl_data = ctk.CTkLabel(frame_item, text=data, font=("Open Sans", 13, "bold"), width=80)
            lbl_data.pack(side="left", padx=10, pady=5)
            
            lbl_desc = ctk.CTkLabel(frame_item, text=desc[:50] + ("..." if len(desc)>50 else ""), font=("Open Sans", 12), anchor="w")
            lbl_desc.pack(side="left", padx=10, pady=5, fill="x", expand=True)
            
            lbl_valor = ctk.CTkLabel(frame_item, text=valor_fmt, font=("Open Sans", 13, "bold"), text_color=cor_valor)
            lbl_valor.pack(side="right", padx=15, pady=5)
            
        frame_botoes = ctk.CTkFrame(janela, fg_color="transparent")
        frame_botoes.pack(pady=15)
        
        btn_autorizar = ctk.CTkButton(frame_botoes, text="Autorizar Lançamentos", command=lambda: self.autorizar_lancamentos(janela), font=("Open Sans", 14, "bold"), fg_color="#5CB85C", hover_color="#4CAE4C", height=40)
        btn_autorizar.pack(side="left", padx=10)
        
        btn_cancelar = ctk.CTkButton(frame_botoes, text="Cancelar", command=lambda: self.cancelar_lancamentos(janela), font=("Open Sans", 14, "bold"), fg_color="#D9534F", hover_color="#C9302C", height=40)
        btn_cancelar.pack(side="right", padx=10)
        
        # Trata o caso de quem fecha a janela pelo X (fechamento bruto)
        janela.protocol("WM_DELETE_WINDOW", lambda: self.cancelar_lancamentos(janela))

    def autorizar_lancamentos(self, janela):
        self.autorizou_importacao = True
        self.esperando_autorizacao = False
        janela.destroy()
        
    def cancelar_lancamentos(self, janela):
        self.autorizou_importacao = False
        self.esperando_autorizacao = False
        janela.destroy()

    def selecionar_select2(self, page, select_id, termo_busca, dropdown_is_ajax=True):
        """
        Interage com os componentes Select2 do SIGA.
        Como o HTML muda muito, foca em clicar na wrapper e digitar no input.
        """
        try:
            # Container wrapper q abriga o select2
            container = page.locator(f'#s2id_{select_id}')
            container.wait_for(state="visible", timeout=3000) # Diminuído para 3s para evitar espera longa
            
            classes = container.get_attribute("class") or ""
            if "select2-container-disabled" in classes:
                # O campo é automático/somente leitura (ex: Histórico de Destino copiado da Origem)
                return
                
            container.click(timeout=3000)
            time.sleep(0.5)
            
            # Input de texto que aparece lá embaixo quando clicamos num select2
            input_search = page.locator('#select2-drop:visible .select2-input')
            input_search.fill(str(termo_busca), timeout=3000)
            
            if dropdown_is_ajax:
                time.sleep(2.0) # Espera o SIGA buscar no servidor
            else:
                time.sleep(0.5) # Filtro puramente local HTML
                
            # Clica no primeiro item resultante
            opcao_li = page.locator('#select2-drop:visible .select2-results li.select2-result-selectable').first
            opcao_li.wait_for(state="visible", timeout=3000)
            opcao_li.click()
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"Falha ao usar Select2 {select_id} para o termo {termo_busca}: {e}")

    def inserir_lancamentos_siga(self, page, lancamentos):
        """
        Executa os cliques para incluir Aplicações e Resgates na tela TES01704.
        """
        try:
            # Ordenação exigida pelo usuário: Resgates (Valores Positivos) PRIMEIRO, Aplicações (Negativos) DEPOIS.
            lanc_ordenados = sorted(lancamentos, key=lambda tx: tx.get("valor", 0.0), reverse=True)
            
            conta_corrente = self.dados_processados.get("conta_siga_corrente", "")
            conta_aplicacao = self.dados_processados.get("conta_siga_aplicacao", "")
            
            import time
            for i, tx in enumerate(lanc_ordenados):
                if not self.browser_aberto:
                    break
                    
                data_tx = tx.get("data", "")
                valor_tx = tx.get("valor", 0.0)
                desc_tx = tx.get("descricao", "OFX")
                
                eh_resgate = valor_tx > 0
                tipo_nome = "RESGATE" if eh_resgate else "APLICAÇÃO"
                
                self.atualizar_status(self.label_status_siga, f"Lançando {i+1}/{len(lanc_ordenados)}: {tipo_nome} -> R$ {abs(valor_tx):.2f}", "#F89406")
                
                # Somente precisa navegar para a tela TES01704 no PRIMEIRO item.
                # Nos itens subsequentes, usaremos o "Salvar e Novo" que já limpa a tela automaticamente.
                if i == 0:
                    page.locator('#f_executar_programa').fill("TES01704")
                    page.locator('#btn_executar_programa').click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                else:
                    self.atualizar_status(self.label_status_siga, f"Preparando novo registro na tela atual...", "#F89406")
                    time.sleep(1) # Intervalo pro form vazio carregar no DOM após um 'Salvar e Novo'
                
                # 1. Data e Tratamento de Alerta de Competência do SIGA
                # Dribla o Datepicker que força a 'data de hoje' ao receber foco
                page.evaluate(f'''() => {{
                    let inp = document.getElementById("f_data");
                    if (inp) {{
                        inp.value = "{data_tx}";
                        if (window.jQuery) {{
                            window.jQuery(inp).datepicker('update', "{data_tx}");
                            window.jQuery(inp).trigger('change');
                            window.jQuery('.datepicker').hide(); // Esconde o calendário visualmente
                        }} else {{
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }}''')
                
                time.sleep(1) # Aguarda debounce ou processamento AJAX do SIGA
                # Se a data informada (do OFX) divergir da competência aberta no momento, 
                # o SIGA joga uma tela de bloqueio perguntando se deseja continuar.
                try:
                    btn_sim = page.locator('.bootbox button:has-text("Sim")').first
                    btn_sim.wait_for(state="visible", timeout=2000)
                    btn_sim.click()
                    time.sleep(0.5)
                except Exception:
                    # Se não aparecer a tela, maravilhoso, segue a vida em paz.
                    pass
                
                # 1.1 Valor
                valor_str = f"{abs(valor_tx):.2f}".replace('.', ',')
                input_valor = page.locator('#f_valor')
                input_valor.click()
                input_valor.fill("")
                input_valor.type(valor_str)
                time.sleep(0.5)
                
                # 2. Forma de Pagamento (Transf Bancaria = "5")
                self.selecionar_select2(page, "f_formapagamento", "TRANSF. BANCÁRIA", dropdown_is_ajax=False)
                
                # Estabelece Origem x Destino
                if eh_resgate:
                    str_orig = conta_aplicacao
                    str_dest = conta_corrente
                else:
                    str_orig = conta_corrente
                    str_dest = conta_aplicacao
                    
                # 3. Contas Origem / Destino (Select Ajax)
                # No SIGA TES01704, a Origem ganha sufixo 'origem' e o Destino usa o ID padrão sem sufixo
                self.selecionar_select2(page, "f_contaorigem", str_orig, dropdown_is_ajax=True)
                self.selecionar_select2(page, "f_conta", str_dest, dropdown_is_ajax=True)
                
                # 4. Históricos (002 p/ Aplicação, 031 p/ Resgate)
                codigo_historico = "002" if tx["valor"] < 0 else "031"
                self.selecionar_select2(page, "f_historicoorigem", codigo_historico, dropdown_is_ajax=True)
                self.selecionar_select2(page, "f_historico", codigo_historico, dropdown_is_ajax=True)
                
                # 5. Complemento e Documento
                msg_comp = f"{tipo_nome} - {desc_tx}"
                page.evaluate(f'''
                    if (document.getElementById("f_complementoorigem")) document.getElementById("f_complementoorigem").value = "{msg_comp}";
                    if (document.getElementById("f_complementodestino")) document.getElementById("f_complementodestino").value = "{msg_comp}";
                    if (document.getElementById("f_complemento")) document.getElementById("f_complemento").value = "{msg_comp}";
                    if (document.getElementById("f_documentoorigem")) document.getElementById("f_documentoorigem").value = "OFX";
                    if (document.getElementById("f_documentodestino")) document.getElementById("f_documentodestino").value = "OFX";
                    if (document.getElementById("f_documento")) document.getElementById("f_documento").value = "OFX";
                ''')
                time.sleep(1)
                
                # 6. Salvar/Gravar usando Inteligência de Rota do SIGA
                is_ultimo = (i == len(lanc_ordenados) - 1)
                
                if is_ultimo:
                    # Último registro: Clicar apenas em "Salvar" (voltando p/ painel)
                    btn_gravar = page.locator('button.btn-salvar[data-comando="F"]')
                else:
                    # Ainda tem mais: Clicar em "Salvar e Novo" (mantém na tela limpo)
                    btn_gravar = page.locator('button.btn-salvar[data-comando="N"]')
                    
                if btn_gravar.count() > 0:
                    btn_gravar.first.click()
                else:
                    # Fallback bruto caso mude layout
                    page.locator('button.btn-success:has(i.icon-ok)').first.click()
                
                # Aguarda o reload da tela ou pop-up de sucesso ajax do SIGA
                page.wait_for_load_state("domcontentloaded")
                
                # O SIGA joga um modal de "Informação: armazenada com sucesso!"
                try:
                    btn_sucesso = page.locator('.bootbox button:has-text("Ok"), .bootbox button[data-bb-handler="botao"]').first
                    btn_sucesso.wait_for(state="visible", timeout=6000)
                    btn_sucesso.click()
                except Exception:
                    # Se salvou de forma transparente sem popup, apenas segue
                    pass
                    
                time.sleep(1) # Aguarda o modal sumir completamente
                
            self.atualizar_status(self.label_status_siga, f"✅ Finalizado! {len(lanc_ordenados)} registros injetados no SIGA.", "#3C763D")
            from tkinter import messagebox
            self.after(0, lambda: messagebox.showinfo("AutoSIGA", "Todos os lançamentos foram importados com sucesso!"))
            
        except Exception as e:
            logging.error(f"Erro inserindo lançamentos: {e}", exc_info=True)
            self.atualizar_status(self.label_status_siga, f"Falha na inserção: {e}", "#D9534F")

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
        self.browser_aberto = True
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                # 1. Usar modo "Persistente" para salvar os cookies e sessão do usuário na pasta local
                user_data_dir = os.path.join(os.getcwd(), 'siga_browser_data')
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    no_viewport=True,  # Deixa abrir maximizado ou no tamanho natural
                    args=["--start-maximized"]
                )
                
                # No modo persistente, uma guia já vem previamente aberta
                page = context.pages[0] if context.pages else context.new_page()
                
                # --- INJEÇÃO "MODO ESPIÃO" PARA MAPEAMENTO ---
                page.on("console", lambda msg: logging.info(msg.text) if "SIGA-CLIQUE" in msg.text else None)
                page.add_init_script("""
                    document.addEventListener('click', function(e) {
                        let el = e.target;
                        let tags = [];
                        while(el && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                            let id_str = el.id ? '#' + el.id : '';
                            let class_str = (el.className && typeof el.className === 'string' && el.className.trim() !== '') ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
                            tags.unshift(el.tagName.toLowerCase() + id_str + class_str);
                            el = el.parentElement;
                        }
                        let info = 'SIGA-CLIQUE -> ' + tags.join(' > ');
                        if (e.target.innerText) {
                            info += ' || TEXTO: ' + e.target.innerText.trim().substring(0, 40).replace(/\\n/g, ' ');
                        }
                        console.log(info);
                    }, true);
                """)
                # ---------------------------------------------
                
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
                        # Usa o JS nativo para forçar o clique, pois links de dropdown ficam invisíveis (display: none)
                        linha_alvo.locator('a').evaluate("el => el.click()")
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
                            
                            # Clica no botão dropdown do menu superior para revelar as opções
                            page.locator('#a_competencia').click()
                            time.sleep(0.5) # aguarda animação da listinha descendo
                            
                            link_mes = page.locator(f'a.f_competencia_master:has-text("{mes_ano_alvo}")')
                            
                            if link_mes.count() > 0:
                                # Usa clique nativo do Playwright agora que o menu está aberto
                                link_mes.first.click()
                                page.wait_for_load_state("domcontentloaded")
                                time.sleep(2) # Aguarda página recarregar com novo mês
                            else:
                                self.atualizar_status(self.label_status_siga, f"⚠️ Mês {mes_ano_alvo} precisa ser trocado manualmente!", "#D9534F")
                                time.sleep(3) # Pausa pro usuario ler e poder agir
                        else:
                            self.atualizar_status(self.label_status_siga, f"Mês de competência ({mes_ano_alvo}) já está correto.", "#3C763D")
                            time.sleep(1.5)
                                
                self.atualizar_status(self.label_status_siga, f"✅ Pronto e Logado em: {self.localidade_selecionada}", "#3C763D")
                
                # 5. Navegação para a Tela Operacional (TES01701 - Caixas e Bancos)
                self.atualizar_status(self.label_status_siga, f"Acessando rotina TES01701...", "#428BCA")
                
                input_programa = page.locator('#f_executar_programa')
                btn_executar = page.locator('#btn_executar_programa')
                
                # Aguarda o input e preenche
                input_programa.wait_for(state="visible", timeout=10000)
                input_programa.fill("TES01701")
                time.sleep(0.5)
                
                # Remove notificações do sistema (modais flutuantes) para que não interceptem cliques
                page.evaluate("document.querySelectorAll('.notificacao').forEach(e => e.remove());")
                
                # Clica na setinha verde e aguarda o carregamento
                btn_executar.click(force=True)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2) # Pequena pausa pra garantir que a tela Tesouraria "piscou e abriu"
                
                # 6. Abertura da janela/modal do Extrato
                self.atualizar_status(self.label_status_siga, f"Abrindo menu do Extrato...", "#428BCA")
                
                btn_extrato = page.locator('#btn-filtro')
                btn_extrato.wait_for(state="visible", timeout=10000)
                btn_extrato.click()
                time.sleep(1.5) # Aguarda o componente de extrato ser renderizado na tela
                
                # 7. Preenche os dados no Formulário HTML (modal)
                self.atualizar_status(self.label_status_siga, f"Preenchendo Conta e Datas...", "#428BCA")
                
                conta_alvo = self.dados_processados.get("conta_siga_corrente", "")
                achou_conta = False
                
                # Mapeia as <option> do select original e simula a troca
                if conta_alvo:
                    opcoes = page.locator('#f_conta option')
                    for i in range(opcoes.count()):
                        texto_opt = opcoes.nth(i).text_content()
                        if conta_alvo in texto_opt:
                            valor_id = opcoes.nth(i).get_attribute('value')
                            # Força via js para que o 'select2' (componente visual do SIGA) reconheça
                            page.evaluate(f'$("#f_conta").val("{valor_id}").trigger("change")')
                            achou_conta = True
                            break
                            
                if not achou_conta:
                    self.atualizar_status(self.label_status_siga, f"⚠️ Conta '{conta_alvo}' não encontrada na lista!", "#D9534F")
                    time.sleep(3) # Pausa pro usuario ler

                # Preenche datainicial e final puxados direto do Extrato Bancário
                data_in = self.dados_processados.get("data_inicial", "")
                data_fim = self.dados_processados.get("data_final", "")
                
                if data_in:
                    page.locator('#f_data1').fill(data_in)
                if data_fim:
                    page.locator('#f_data2').fill(data_fim)
                    
                time.sleep(0.5)
                
                # Clica no submit do form (Botão Consultar)
                self.atualizar_status(self.label_status_siga, f"Consultando movimentações no banco...", "#F89406")
                page.locator('#f_main button[type="submit"].btn-success').click()
                
                page.wait_for_load_state("domcontentloaded")
                time.sleep(3) # Aguarda o grid carregar com os registros
                
                # 8. Extrai as linhas da Tabela (Para bater com o OFX depois)
                self.atualizar_status(self.label_status_siga, f"Lendo dados da tabela do SIGA...", "#428BCA")
                page.locator('#grid1').wait_for(state="visible", timeout=10000)
                
                extrato_siga = page.evaluate('''() => {
                    let rows = document.querySelectorAll('#grid1 tbody tr');
                    let result = [];
                    for (let tr of rows) {
                        let tds = tr.querySelectorAll('td');
                        // Ignora "Saldo Anterior" que tem <th> em vez de <td>
                        if (tds.length >= 8) {
                            result.push({
                                data: tds[0].innerText.trim(),
                                lote: tds[1].innerText.trim(),
                                documento: tds[2].innerText.trim(),
                                historico: tds[3].innerText.trim(),
                                origem: tds[4].innerText.trim(),
                                entrada: tds[5].innerText.trim(),
                                saida: tds[6].innerText.trim(),
                                saldo: tds[7].innerText.trim()
                            });
                        }
                    }
                    return result;
                }''')
                
                self.dados_processados["extrato_siga"] = extrato_siga
                qtd_siga = len(extrato_siga)
                
                # 9. Realiza a Conciliação (Cruzamento) dos dados
                self.atualizar_status(self.label_status_siga, f"Cruzando {qtd_siga} itens do SIGA com o OFX...", "#428BCA")
                novos_lancamentos = self.conciliar_extratos()
                
                if novos_lancamentos:
                    self.atualizar_status(self.label_status_siga, f"⚠️ Há {len(novos_lancamentos)} lançamentos para importar! Aguardando sua ação...", "#F89406")
                    
                    self.esperando_autorizacao = True
                    self.autorizou_importacao = False
                    
                    # Chama a UI pra mostrar na thread principal de forma segura
                    self.after(0, lambda: self.mostrar_janela_lancamentos(novos_lancamentos))
                    
                    # Trava temporariamente o fluxo do Playwright aguardando o usuário clicar 'Autorizar' ou 'Cancelar'
                    while self.esperando_autorizacao:
                        if not self.browser_aberto:
                            # Cai se o app for fechado
                            break
                        time.sleep(1)
                        
                    if self.autorizou_importacao:
                        self.atualizar_status(self.label_status_siga, "🚀 Lançamentos autorizados! Iniciando inserção...", "#428BCA")
                        # 10. Implementar loop de cliques de lançamento aqui na proxima etapa
                        self.inserir_lancamentos_siga(page, novos_lancamentos)
                        
                        # 11. Conferência Final (Prova Real)
                        self.atualizar_status(self.label_status_siga, "Realizando conferência final no servidor...", "#428BCA")
                        time.sleep(2)
                        
                        try:
                            # A tela TES01701 provavelmente já carregou após o último 'Salvar'
                            if page.locator('#btn-filtro').is_visible():
                                page.locator('#btn-filtro').click()
                                time.sleep(1)
                                
                            # Clica pra gerar o Relatório da Tabela com os dados recém injetados
                            page.locator('#modal-filtro form#f_main button.btn-success').first.click()
                            page.wait_for_load_state("domcontentloaded")
                            time.sleep(4)
                            
                            extrato_recente = page.evaluate('''() => {
                                let rows = document.querySelectorAll('#grid1 tbody tr');
                                let r = [];
                                for (let tr of rows) {
                                    let tds = tr.querySelectorAll('td');
                                    if (tds.length >= 8) {
                                        r.push({
                                            data: tds[0].innerText.trim(), lote: tds[1].innerText.trim(),
                                            documento: tds[2].innerText.trim(), historico: tds[3].innerText.trim(),
                                            origem: tds[4].innerText.trim(), entrada: tds[5].innerText.trim(),
                                            saida: tds[6].innerText.trim(), saldo: tds[7].innerText.trim()
                                        });
                                    }
                                }
                                return r;
                            }''')
                            
                            self.dados_processados["extrato_siga"] = extrato_recente
                            pendentes = self.conciliar_extratos()
                            
                            if not pendentes:
                                self.atualizar_status(self.label_status_siga, f"✅ Conferência 100%: Nenhum item para trás!", "#3C763D")
                                self.after(0, lambda: messagebox.showinfo("AutoSIGA", "Todos os lançamentos foram importados e validados com 100% de sucesso pela conferência do robô!"))
                            else:
                                self.atualizar_status(self.label_status_siga, f"⚠️ Alerta: {len(pendentes)} itens não bateram no SIGA.", "#D9534F")
                                self.after(0, lambda: messagebox.showwarning("AutoSIGA", f"O robô terminou de lançar, porém na verificação final constam {len(pendentes)} transações com divergência de centavos ou não registradas.\n\nVerifique o extrato manualmente!"))
                                
                        except Exception as e:
                            logging.error(f"Erro na conferência final: {e}")
                            self.atualizar_status(self.label_status_siga, f"✅ Lançamentos finalizados (sem prova real)", "#3C763D")
                            
                    else:
                        self.atualizar_status(self.label_status_siga, "❌ Importação cancelada pelo usuário.", "#D9534F")
                    
                else:
                    self.atualizar_status(self.label_status_siga, f"✅ Tudo conciliado! Nenhum lançamento novo faltando.", "#3C763D")
                    # Pop-up de OK direto para o usuário na interface principal
                    self.after(0, lambda: messagebox.showinfo("AutoSIGA", "Todos os investimentos e resgates do OFX já estão conciliados no SIGA!\n\nNão há nada pendente para importar."))
                    
                # Mantém o navegador aberto num loop
                self.browser_aberto = True
                while self.browser_aberto:
                    time.sleep(1)
                    
        except Exception as e:
            # Exibe o erro no console e no arquivo de log
            msg_erro = f"Erro inesperado na automação do SIGA: {e}"
            print(f"⚠️ {msg_erro}")
            logging.error(msg_erro, exc_info=True)
            import traceback
            traceback.print_exc()
            
            # Avisa na UI que houve falha (mostra o erro truncado pra centralizar)
            erro_resumido = str(e).split('\n')[0][:50]
            self.atualizar_status(self.label_status_siga, f"Erro no navegador: {erro_resumido}...", "#D9534F")
            self.after(0, lambda: self.botao_conectar.configure(state="normal"))

    def gerar_txt_ofertas(self):
        """
        Extrai transações positivas do OFX, aplica regras de higienização
        e exporta arquivo .TXT limpo e pronto de captação (IT.TES.05)
        """
        if not hasattr(self, "dados_processados") or not self.dados_processados:
            messagebox.showerror("Erro", "Nenhum arquivo processado.")
            return

        transacoes = self.dados_processados.get("transacoes", [])
        if not transacoes:
            messagebox.showwarning("Aviso", "O arquivo OFX carregado não possui transações para avaliar.")
            return

        # Palavras bloqueadas que categorizam lançamentos que NÃO são Ofertas
        # Rendimentos de aplicação, saques aplicados e dinheiro em caixa já lançado direto (depositos)
        palavras_bloqueadas = ["APLICA", "RESGATE", "RENDIMENT", "DEPOSITO"]

        linhas_limpas = []
        qtd_descartadas = 0

        for tx in transacoes:
            valor = tx.get("valor", 0.0)
            descricao = tx.get("descricao", "").upper()
            data = tx.get("data", "")

            # COND. 1: Somente valores POSITIVOS entram no lançamento puro (sem "-").
            if valor <= 0:
                qtd_descartadas += 1
                continue
            
            # COND. 2: Nenhuma palavra bloqueada pode fazer parte da descrição.
            if any(palavra in descricao for palavra in palavras_bloqueadas):
                qtd_descartadas += 1
                continue

            # FORMATAR VALOR (sem separador de milhar, virgula p/ centavos. ex: 1530,50)
            valor_fmt = f"{valor:.2f}".replace(".", ",")
            
            # Formato SIGA Csv: DATA;HISTÓRICO;VALOR
            linha = f"{data};{tx.get('descricao', '').strip()};{valor_fmt}"
            linhas_limpas.append(linha)

        if not str(linhas_limpas):
            pass # safe escape

        if not linhas_limpas:
            messagebox.showwarning("Aviso", "Após os filtros (tirando gastos e aplicações), não sobrou nenhuma linha de Oferta/PIX/Cartão para gerar arquivo!")
            return

        # Pede para salvar
        nome_sugerido = f"OFERTAS_LIMPO_{self.dados_processados.get('conta_id', '1')}.txt"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=nome_sugerido,
            title="Salvar arquivo de Ofertas SIGA",
            filetypes=[("Arquivos de Texto", "*.txt"), ("Todos os Arquivos", "*.*")]
        )

        if filepath:
            try:
                # SIGA em geral aceita bem ISO-8859-1 (Latin1) ou UTF-8 nativo em importador web ASP.
                # Como extratos OFX costumam trazer acentos mistos, usaremos utf-8
                with open(filepath, 'w', encoding='utf-8') as f:
                    for l in linhas_limpas:
                        f.write(l + "\n")
                
                messagebox.showinfo(
                    title="Sucesso IT.TES.05", 
                    message=f"Exportação finalizada em estado puro de captação!\n\n"
                            f"✅ Ofertas Válidas Mantidas: {len(linhas_limpas)}\n"
                            f"❌ Despesas/Aplicações Descartadas: {qtd_descartadas}\n\n"
                            f"O arquivo está perfeitamente formatado para importação."
                )
            except Exception as e:
                logging.error(f"Erro ao salvar arquivo TXT: {e}", exc_info=True)
                messagebox.showerror("Erro de IO", f"Falha ao salvar o arquivo: {e}")

if __name__ == "__main__":
    app = AutoSigaApp()
    app.mainloop()