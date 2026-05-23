"""
Módulo de Gerenciamento de Configurações (Model).

Este módulo é responsável por isolar toda a lógica de persistência e 
recuperação de dados locais da aplicação (I/O). Ele lida com o arquivo 
'config.json', armazenando preferências do usuário como localidade 
e mapeamentos de contas bancárias.
"""

import os
import json

class ConfigManager:
    """
    Gerencia a leitura e escrita do arquivo de configurações JSON.
    
    A classe encapsula as operações de I/O para evitar acesso direto ao disco
    pelos controllers ou interfaces, seguindo o padrão MVC.
    """

    def __init__(self, config_path="config.json"):
        """
        Inicializa o gerenciador de configurações.
        
        Args:
            config_path (str): Opcional. Caminho do arquivo JSON no disco. 
                               Padrão é 'config.json'.
        """
        self.config_path = config_path

    def get_config_data(self):
        """
        Lê e retorna as configurações armazenadas no arquivo JSON local.
        
        Se o arquivo não existir ou for inválido, retorna um dicionário vazio.
        
        Returns:
            dict: Dicionário contendo as configurações estruturadas.
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config_data(self, data):
        """
        Salva um dicionário contendo as configurações da aplicação no disco.
        
        Args:
            data (dict): Os dados que devem ser persistidos no JSON.
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")

    def get_geral(self):
        """
        Retorna as preferências gerais salvas pelo usuário.
        
        Returns:
            tuple: Uma tupla (str, str) contendo (tipo_adm, nome_adm).
                   Exemplo: ("ADM", "SÃO PAULO")
        """
        config = self.get_config_data()
        return config.get("tipo_adm", "ADM"), config.get("nome_adm", "")

    def salvar_geral(self, tipo_adm, nome_adm):
        """
        Salva a preferência de administração atual no disco.
        
        Args:
            tipo_adm (str): O tipo de administração (ex: ADM, DR, PIA).
            nome_adm (str): O nome da administração (ex: SÃO PAULO).
        """
        config = self.get_config_data()
        config["tipo_adm"] = tipo_adm
        config["nome_adm"] = nome_adm
        self.save_config_data(config)

    def get_mapeamento_conta(self, conta_id, tipo_adm, nome_adm, produto=None):
        """
        Busca as contas SIGA vinculadas a uma conta bancária (OFX).
        
        Realiza a busca reversa: se a conta OFX informada não existir para a
        administração atual, mas for encontrada vinculada a outra administração,
        o sistema infere inteligentemente e muda a administração ativa.
        
        Args:
            conta_id (str): Número da conta bancária extraído do arquivo OFX.
            tipo_adm (str): Tipo da administração corrente na interface.
            nome_adm (str): Nome da administração corrente na interface.
            produto (str): Opcional. Nome do produto de investimento (ex: POUPANCA TRADICIONAL).
            
        Returns:
            tuple: (tipo_adm, nome_adm, dados_contas) atualizados. Onde 
                   'dados_contas' é um dict {"corrente": str, "aplicacao": str}.
        """
        config = self.get_config_data()
        mapeamentos = config.get("contas_mapeadas", {})
        
        tipo_alvo = tipo_adm.strip().upper()
        nome_alvo = nome_adm.strip().upper()
        
        prod_alvo = produto.strip().upper() if produto else None
        conta_com_prod = f"{conta_id}#{prod_alvo}" if prod_alvo else conta_id
        
        chave = f"{tipo_alvo}-{nome_alvo}-{conta_com_prod}"
        
        # MÁGICA: PROCURA REVERSA E AUTO-PREENCHIMENTO COM NORMALIZAÇÃO INTELIGENTE
        def norm(c_id):
            return "".join(c for c in str(c_id) if c.isdigit()).lstrip("0")
            
        conta_id_norm = norm(conta_id)
        chave_encontrada = None
        
        # Varre as chaves mapeadas para encontrar matches normativos de conta
        for db_chave in mapeamentos.keys():
            partes = db_chave.split('-')
            if len(partes) >= 3:
                db_tipo = partes[0]
                db_nome = "-".join(partes[1:-1])
                db_conta_raw = partes[-1]
                
                if '#' in db_conta_raw:
                    db_conta, db_prod = db_conta_raw.split('#', 1)
                else:
                    db_conta = db_conta_raw
                    db_prod = None
                
                # Se der match no número base da conta
                if norm(db_conta).endswith(conta_id_norm):
                    # Se estamos buscando um produto específico, o produto no banco deve corresponder
                    if prod_alvo and db_prod != prod_alvo:
                        continue
                        
                    # Prioridade Absoluta: se der match na filial que já está selecionada na tela (UI)
                    if db_tipo == tipo_alvo and db_nome == nome_alvo:
                        chave_encontrada = db_chave
                        break
                    elif not chave_encontrada:
                        # Fallback: guarda o primeiro match que achar em outra filial
                        chave_encontrada = db_chave
                        
        if chave_encontrada:
            partes = chave_encontrada.split('-')
            novo_tipo = partes[0]
            novo_nome = "-".join(partes[1:-1])
            
            # Se o match foi em outra filial, altera a preferência ativa de filial
            if novo_tipo != tipo_alvo or novo_nome != nome_alvo:
                self.salvar_geral(novo_tipo, novo_nome)
                
            return novo_tipo, novo_nome, mapeamentos.get(chave_encontrada)
 
        dados = mapeamentos.get(chave)
        # Fallback de compatibilidade caso o arquivo não tenha sido salvo ainda
        if not dados:
            # Se for com produto, tenta buscar sem produto também como fallback genérico de compatibilidade
            if prod_alvo:
                chave_sem_prod = f"{tipo_alvo}-{nome_alvo}-{conta_id}"
                dados = mapeamentos.get(chave_sem_prod)
            if not dados:
                dados = mapeamentos.get(conta_id, {"corrente": "", "aplicacao": ""})
            
        return tipo_alvo, nome_alvo, dados

    def salvar_mapeamento_conta(self, conta_id, tipo_adm, nome_adm, corrente, aplicacao, produto=None):
        """
        Vincula as IDs das contas do SIGA ao respectivo número de conta do OFX.
        
        Args:
            conta_id (str): A conta origem extraída nativamente do OFX bancário.
            tipo_adm (str): O tipo de administração.
            nome_adm (str): O nome da administração (ex: SÃO PAULO).
            corrente (str): O ID da conta corrente interna no SIGA.
            aplicacao (str): O ID da conta aplicação interna no SIGA.
            produto (str): Opcional. Nome do produto de investimento.
        """
        config = self.get_config_data()
        if "contas_mapeadas" not in config:
            config["contas_mapeadas"] = {}
            
        prod_alvo = produto.strip().upper() if produto else None
        conta_com_prod = f"{conta_id}#{prod_alvo}" if prod_alvo else conta_id
        
        # Cria uma chave única combinando os três parâmetros
        chave = f"{tipo_adm.strip().upper()}-{nome_adm.strip().upper()}-{conta_com_prod}"
            
        # Preserva dados anteriores caso venham campos em branco (ex: corrente vazia no XLS de aplicação)
        dados_existentes = config["contas_mapeadas"].get(chave, {})
        corr_final = corrente if corrente.strip() else dados_existentes.get("corrente", "")
        apli_final = aplicacao if aplicacao.strip() else dados_existentes.get("aplicacao", "")
        
        config["contas_mapeadas"][chave] = {
            "corrente": corr_final,
            "aplicacao": apli_final
        }
        self.save_config_data(config)

    def limpar_conta(self, conta_id, tipo_adm, nome_adm, produto=None):
        """
        Remove o mapeamento em disco de uma conta salva.
        
        Utilizado pelo botão 'Esquecer' da interface gráfica para forçar o
        sistema a esquecer a correlação entre o OFX e o SIGA.
        
        Args:
            conta_id (str): A conta do OFX.
            tipo_adm (str): O tipo de administração.
            nome_adm (str): O nome da administração.
            produto (str): Opcional. Nome do produto de investimento.
            
        Returns:
            bool: True se removeu com sucesso, False caso o mapeamento não exista.
        """
        config = self.get_config_data()
        prod_alvo = produto.strip().upper() if produto else None
        conta_com_prod = f"{conta_id}#{prod_alvo}" if prod_alvo else conta_id
        chave = f"{tipo_adm.strip().upper()}-{nome_adm.strip().upper()}-{conta_com_prod}"
        
        if "contas_mapeadas" in config and chave in config["contas_mapeadas"]:
            del config["contas_mapeadas"][chave]
            self.save_config_data(config)
            return True
        return False
