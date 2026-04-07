import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
from ofxparse import OfxParser

# Configuração do estilo para combinar com o SIGA
ctk.set_appearance_mode("light") 

class AutoSigaApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Mantenha referência aos dados
        self.dados_processados = None

        # Configurações da Janela
        self.title("AutoSIGA - Importação")
        self.geometry("550x450")
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

        self.label_instrucao = ctk.CTkLabel(self.frame_card, text="Importação de Extrato", font=("Open Sans", 18), text_color="#3D71A8")
        self.label_instrucao.pack(pady=(30, 20))

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
        self.botao_carregar.pack(pady=10)

        # 4. Label para mostrar o nome do arquivo selecionado
        self.label_arquivo = ctk.CTkLabel(self.frame_card, text="Nenhum arquivo selecionado.", font=self.fonte_padrao, text_color="#666666")
        self.label_arquivo.pack(pady=(10, 30))

    def selecionar_arquivo(self):
        # Abre o explorador de arquivos filtrando por .ofx
        caminho_arquivo = filedialog.askopenfilename(
            title="Selecione o arquivo do extrato",
            filetypes=[("Arquivos OFX", "*.ofx"), ("Todos os Arquivos", "*.*")]
        )

        if caminho_arquivo:
            nome_arquivo = os.path.basename(caminho_arquivo)
            # Verde sucesso (estilo alert-success do Bootstrap)
            self.label_arquivo.configure(text=f"Arquivo selecionado:\n{nome_arquivo}", text_color="#3C763D") 
            print(f"Arquivo selecionado para processamento: {caminho_arquivo}")
            
            # Após selecionar, realizar o processamento
            self.processar_ofx(caminho_arquivo)

    def processar_ofx(self, caminho):
        try:
            with open(caminho, 'rb') as f:
                ofx = OfxParser.parse(f)
            
            conta = ofx.account
            extrato = conta.statement
            
            # Objeto (dicionário) com os dados consolidados para a próxima etapa
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
            quantidade_tx = len(dados_ofx["transacoes"])
            saldo = dados_ofx["saldo_atual"]
            
            print(f"Processamento concluído. {quantidade_tx} transações estruturadas.")
            messagebox.showinfo(
                "Processamento Concluído", 
                f"Extrato lido com sucesso!\n\nTransações encontradas: {quantidade_tx}\nSaldo: R$ {saldo:.2f}"
            )
            
        except Exception as e:
            print(f"Erro ao processar arquivo: {e}")
            messagebox.showerror("Erro de Leitura", f"Encontramos um problema ao ler o arquivo OFX.\nDetalhe: {e}")

if __name__ == "__main__":
    app = AutoSigaApp()
    app.mainloop()