"""
Módulo de Gerenciamento de Configurações (Model).

Este módulo é responsável por isolar toda a lógica de persistência e 
recuperação de dados locais da aplicação (I/O). Ele lida com o arquivo 
'config.json', armazenando preferências do usuário como localidade 
e mapeamentos de contas bancárias.
"""

import os
import json
import sys

class ConfigManager:
    """
    Gerencia a leitura e escrita do arquivo de configurações JSON.
    
    A classe encapsula as operações de I/O para evitar acesso direto ao disco
    pelos controllers ou interfaces, seguindo o padrão MVC.
    """

    def __init__(self, config_path=None):
        """
        Inicializa o gerenciador de configurações calculando o caminho absoluto do config.json.
        """
        if config_path is None:
            if getattr(sys, 'frozen', False):
                # Se empacotado pelo PyInstaller
                base_dir = os.path.dirname(sys.executable)
            else:
                # Se rodando como script Python (config_manager.py está dentro de 'models/')
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config.json")
            
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
                    config = json.load(f)
                if "contas_mapeadas" in config:
                    config = self._migrar_formato_antigo(config)
                return config
            except Exception:
                return {}
        return {}

    def _migrar_formato_antigo(self, config):
        """
        Migra o formato de contas_mapeadas legado para a nova estrutura de lista estruturada.
        """
        contas_mapeadas = config.pop("contas_mapeadas", {})
        mapeamentos_novos = []
        
        def norm(c_id):
            return "".join(c for c in str(c_id) if c.isdigit()).lstrip("0")
            
        for key, value in contas_mapeadas.items():
            if not value or not (value.get("corrente", "").strip() or value.get("aplicacao", "").strip()):
                continue
                
            tipo_adm = None
            for t in ["ADM", "DR", "PIA"]:
                if key.startswith(f"{t}-"):
                    tipo_adm = t
                    break
            
            if tipo_adm:
                resto = key[len(tipo_adm) + 1:]
                if '#' in resto:
                    conta_raw, produto = resto.split('#', 1)
                    produto = produto.strip().upper()
                else:
                    conta_raw = resto
                    produto = None
                
                partes = conta_raw.split('-')
                if len(partes) >= 2:
                    idx_conta = len(partes) - 1
                    while idx_conta > 0:
                        if partes[idx_conta - 1].isalpha():
                            break
                        idx_conta -= 1
                    
                    conta_id = "-".join(partes[idx_conta:])
                    nome_adm = "-".join(partes[:idx_conta]).strip().upper()
                else:
                    conta_id = conta_raw
                    nome_adm = ""
            else:
                nome_adm = ""
                tipo_adm = "ADM"
                if '#' in key:
                    conta_id, produto = key.split('#', 1)
                    produto = produto.strip().upper()
                else:
                    conta_id = key
                    produto = None
            
            mapeamentos_novos.append({
                "conta_id": conta_id,
                "produto": produto,
                "tipo_adm": tipo_adm,
                "nome_adm": nome_adm,
                "corrente": value.get("corrente", ""),
                "aplicacao": value.get("aplicacao", "")
            })
            
        # Agrupa duplicados
        mapeamentos_unicos = {}
        for m in mapeamentos_novos:
            chave_unica = (
                m["conta_id"],
                m["produto"],
                m["tipo_adm"],
                m["nome_adm"]
            )
            existente = mapeamentos_unicos.get(chave_unica)
            if existente:
                if m["corrente"] and not existente["corrente"]:
                    existente["corrente"] = m["corrente"]
                if m["aplicacao"] and not existente["aplicacao"]:
                    existente["aplicacao"] = m["aplicacao"]
            else:
                mapeamentos_unicos[chave_unica] = m
                
        config["mapeamentos"] = list(mapeamentos_unicos.values())
        self.save_config_data(config)
        return config

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
        Busca as contas SIGA vinculadas a uma conta bancária (OFX ou XLS).
        
        Args:
            conta_id (str): Número da conta bancária.
            tipo_adm (str): Tipo da administração corrente.
            nome_adm (str): Nome da administração corrente.
            produto (str): Opcional. Nome do produto de investimento.
            
        Returns:
            tuple: (tipo_adm, nome_adm, dados_contas) onde 'dados_contas' é um dict.
        """
        config = self.get_config_data()
        mapeamentos = config.get("mapeamentos", [])
        
        tipo_alvo = tipo_adm.strip().upper()
        nome_alvo = nome_adm.strip().upper()
        prod_alvo = produto.strip().upper() if produto else None
        
        # 1. Match exato
        for m in mapeamentos:
            if (m.get("conta_id", "").strip() == conta_id and
                m.get("produto") == prod_alvo and
                m.get("tipo_adm", "").strip().upper() == tipo_alvo and
                m.get("nome_adm", "").strip().upper() == nome_alvo):
                return tipo_alvo, nome_alvo, m
                
        # 2. Busca reversa (match de conta e produto em qualquer localidade)
        def norm(c_id):
            return "".join(c for c in str(c_id) if c.isdigit()).lstrip("0")
            
        conta_id_norm = norm(conta_id)
        match_favorito = None
        
        for m in mapeamentos:
            m_conta = m.get("conta_id", "").strip()
            m_prod = m.get("produto")
            m_tipo = m.get("tipo_adm", "").strip().upper()
            m_nome = m.get("nome_adm", "").strip().upper()
            
            if norm(m_conta) == conta_id_norm:
                if prod_alvo and m_prod != prod_alvo:
                    continue
                    
                if m_tipo == tipo_alvo and m_nome == nome_alvo:
                    match_favorito = m
                    break
                elif not match_favorito:
                    match_favorito = m
                    
        if match_favorito:
            return match_favorito.get("tipo_adm"), match_favorito.get("nome_adm"), match_favorito
            
        # 3. Fallback geral de conta e produto
        for m in mapeamentos:
            m_conta = m.get("conta_id", "").strip()
            m_prod = m.get("produto")
            if norm(m_conta) == conta_id_norm and (not prod_alvo or m_prod == prod_alvo):
                return tipo_alvo, nome_alvo, m
                
        return tipo_alvo, nome_alvo, {"corrente": "", "aplicacao": ""}

    def salvar_mapeamento_conta(self, conta_id, tipo_adm, nome_adm, corrente, aplicacao, produto=None):
        """
        Vincula as IDs das contas do SIGA ao respectivo número de conta bancária.
        """
        config = self.get_config_data()
        if "mapeamentos" not in config:
            config["mapeamentos"] = []
            
        tipo_clean = tipo_adm.strip().upper()
        nome_clean = nome_adm.strip().upper()
        prod_alvo = produto.strip().upper() if produto else None
        
        match_existente = None
        for m in config["mapeamentos"]:
            if (m.get("conta_id", "").strip() == conta_id and
                m.get("produto") == prod_alvo and
                m.get("tipo_adm", "").strip().upper() == tipo_clean and
                m.get("nome_adm", "").strip().upper() == nome_clean):
                match_existente = m
                break
                
        if match_existente:
            match_existente["corrente"] = corrente if corrente.strip() else match_existente.get("corrente", "")
            match_existente["aplicacao"] = aplicacao if aplicacao.strip() else match_existente.get("aplicacao", "")
        else:
            config["mapeamentos"].append({
                "conta_id": conta_id,
                "produto": prod_alvo,
                "tipo_adm": tipo_clean,
                "nome_adm": nome_clean,
                "corrente": corrente,
                "aplicacao": aplicacao
            })
            
        self.save_config_data(config)

    def limpar_conta(self, conta_id, tipo_adm, nome_adm, produto=None):
        """
        Remove o mapeamento em disco de uma conta salva.
        """
        config = self.get_config_data()
        mapeamentos = config.get("mapeamentos", [])
        
        tipo_clean = tipo_adm.strip().upper()
        nome_clean = nome_adm.strip().upper()
        prod_alvo = produto.strip().upper() if produto else None
        
        novos_mapeamentos = []
        removido = False
        for m in mapeamentos:
            if (m.get("conta_id", "").strip() == conta_id and
                m.get("produto") == prod_alvo and
                m.get("tipo_adm", "").strip().upper() == tipo_clean and
                m.get("nome_adm", "").strip().upper() == nome_clean):
                removido = True
                continue
            novos_mapeamentos.append(m)
            
        if removido:
            config["mapeamentos"] = novos_mapeamentos
            self.save_config_data(config)
            return True
        return False

    def get_geometry(self):
        """
        Retorna as dimensões e posicionamento da janela salvos.
        """
        config = self.get_config_data()
        return config.get("geometry")

    def salvar_geometry(self, geometry):
        """
        Salva a posição e dimensões atuais da janela.
        """
        config = self.get_config_data()
        config["geometry"] = geometry
        self.save_config_data(config)

    def get_usuario_siga(self):
        """
        Retorna o usuário do SIGA salvo publicamente para consulta no Keyring.
        """
        config = self.get_config_data()
        return config.get("usuario_siga", "")

    def salvar_usuario_siga(self, usuario):
        """
        Persiste o nome do usuário do SIGA de forma pública para atrelar a consulta do Keyring.
        """
        config = self.get_config_data()
        config["usuario_siga"] = str(usuario).strip()
        self.save_config_data(config)

    # Métodos novos para suporte a faturas de energia (Energisa)
    def get_email_config(self):
        """
        Retorna as configurações de e-mail e corte.
        
        Returns:
            dict: {email, servidor, mes_corte}
        """
        config = self.get_config_data()
        return {
            "email": config.get("email_energia", ""),
            "servidor": config.get("servidor_imap_energia", "imap.gmail.com"),
            "mes_corte": config.get("mes_corte_energia", "")
        }

    def salvar_email_config(self, email, servidor, mes_corte):
        """
        Salva as configurações de e-mail e corte.
        """
        config = self.get_config_data()
        config["email_energia"] = str(email).strip()
        config["servidor_imap_energia"] = str(servidor).strip()
        config["mes_corte_energia"] = str(mes_corte).strip()
        self.save_config_data(config)

    def get_localidades_energia(self):
        """
        Retorna a lista de localidades cadastradas para energia.
        
        Returns:
            list: Lista de dicts [{"codigo": "...", "nome": "..."}]
        """
        config = self.get_config_data()
        return config.get("localidades_energia", [])

    def salvar_localidade_energia(self, codigo, nome):
        """
        Salva ou atualiza uma localidade de energia.
        """
        config = self.get_config_data()
        localidades = config.get("localidades_energia", [])
        
        codigo_clean = str(codigo).strip().upper()
        nome_clean = str(nome).strip().upper()
        
        # Procura se já existe para atualizar
        atualizado = False
        for loc in localidades:
            if loc.get("codigo") == codigo_clean:
                loc["nome"] = nome_clean
                atualizado = True
                break
                
        if not atualizado:
            localidades.append({
                "codigo": codigo_clean,
                "nome": nome_clean
            })
            
        config["localidades_energia"] = localidades
        self.save_config_data(config)

    def remover_localidade_energia(self, codigo):
        """
        Remove uma localidade de energia.
        """
        config = self.get_config_data()
        localidades = config.get("localidades_energia", [])
        codigo_clean = str(codigo).strip().upper()
        
        novas = [loc for loc in localidades if loc.get("codigo") != codigo_clean]
        if len(novas) != len(localidades):
            config["localidades_energia"] = novas
            self.save_config_data(config)
            return True
        return False

    def get_mapeamentos_uc(self):
        """
        Retorna a lista de mapeamentos de UCs para Localidades.
        
        Returns:
            list: Lista de dicts [{"uc": "...", "localidade_codigo": "..."}]
        """
        config = self.get_config_data()
        return config.get("mapeamentos_uc", [])

    def salvar_mapeamento_uc(self, uc, localidade_codigo):
        """
        Salva ou atualiza a relação de uma UC com uma Localidade.
        """
        config = self.get_config_data()
        mapeamentos = config.get("mapeamentos_uc", [])
        
        uc_clean = str(uc).strip()
        loc_codigo_clean = str(localidade_codigo).strip().upper()
        
        atualizado = False
        for map_item in mapeamentos:
            if map_item.get("uc") == uc_clean:
                map_item["localidade_codigo"] = loc_codigo_clean
                atualizado = True
                break
                
        if not atualizado:
            mapeamentos.append({
                "uc": uc_clean,
                "localidade_codigo": loc_codigo_clean
            })
            
        config["mapeamentos_uc"] = mapeamentos
        self.save_config_data(config)

    def remover_mapeamento_uc(self, uc):
        """
        Remove um mapeamento de UC.
        """
        config = self.get_config_data()
        mapeamentos = config.get("mapeamentos_uc", [])
        uc_clean = str(uc).strip()
        
        novos = [m for m in mapeamentos if m.get("uc") != uc_clean]
        if len(novos) != len(mapeamentos):
            config["mapeamentos_uc"] = novos
            self.save_config_data(config)
            return True
        return False

    def get_fatura_processada(self, numero_fatura):
        """
        Verifica se uma fatura específica já foi processada anteriormente.
        """
        config = self.get_config_data()
        processadas = config.get("faturas_energia_processadas", [])
        return str(numero_fatura).strip() in processadas

    def marcar_fatura_processada(self, numero_fatura):
        """
        Registra o número da fatura processada para evitar duplicidade.
        """
        config = self.get_config_data()
        if "faturas_energia_processadas" not in config:
            config["faturas_energia_processadas"] = []
        num_clean = str(numero_fatura).strip()
        if num_clean not in config["faturas_energia_processadas"]:
            config["faturas_energia_processadas"].append(num_clean)
            self.save_config_data(config)

