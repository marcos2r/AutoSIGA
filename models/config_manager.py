import os
import json

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path

    def get_config_data(self):
        """Lê e retorna as configurações armazenadas no arquivo JSON local."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config_data(self, data):
        """Salva um objeto contendo configurações da aplicação no disco."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")

    def get_geral(self):
        """Retorna o tipo e o nome da administração salvos."""
        config = self.get_config_data()
        return config.get("tipo_adm", "ADM"), config.get("nome_adm", "")

    def salvar_geral(self, tipo_adm, nome_adm):
        """Salva a preferência de administração atual."""
        config = self.get_config_data()
        config["tipo_adm"] = tipo_adm
        config["nome_adm"] = nome_adm
        self.save_config_data(config)

    def get_mapeamento_conta(self, conta_id, tipo_adm, nome_adm):
        """Busca as contas SIGA vinculadas a uma conta_id de um OFX.
        
        Realiza a busca reversa: se a conta OFX pertencer a uma administração 
        diferente da passada nos parâmetros, ele atualiza a administração ativa.
        Retorna o tipo_adm resultante, o nome_adm resultante e os dados do mapeamento.
        """
        config = self.get_config_data()
        mapeamentos = config.get("contas_mapeadas", {})
        
        tipo_alvo = tipo_adm.strip().upper()
        nome_alvo = nome_adm.strip().upper()
        chave = f"{tipo_alvo}-{nome_alvo}-{conta_id}"
        
        # MÁGICA: PROCURA REVERSA E AUTO-PREENCHIMENTO
        if chave not in mapeamentos:
            for db_chave in mapeamentos.keys():
                if db_chave.endswith(f"-{conta_id}"):
                    partes = db_chave.split('-')
                    if len(partes) >= 3:
                        novo_tipo = partes[0]
                        novo_nome = "-".join(partes[1:-1])
                        
                        # Atualiza a configuração local com a nova preferência recém assumida
                        self.salvar_geral(novo_tipo, novo_nome)
                        chave = db_chave
                        return novo_tipo, novo_nome, mapeamentos.get(chave)

        dados = mapeamentos.get(chave)
        if not dados:
            dados = mapeamentos.get(conta_id, {"corrente": "", "aplicacao": ""})
            
        return tipo_alvo, nome_alvo, dados

    def salvar_mapeamento_conta(self, conta_id, tipo_adm, nome_adm, corrente, aplicacao):
        """Salva as contas do SIGA para o respectivo ID do OFX."""
        config = self.get_config_data()
        if "contas_mapeadas" not in config:
            config["contas_mapeadas"] = {}
            
        chave = f"{tipo_adm.strip().upper()}-{nome_adm.strip().upper()}-{conta_id}"
            
        config["contas_mapeadas"][chave] = {
            "corrente": corrente,
            "aplicacao": aplicacao
        }
        self.save_config_data(config)

    def limpar_conta(self, conta_id, tipo_adm, nome_adm):
        """Remove o mapeamento de contas salvo para o ID do OFX especificado."""
        config = self.get_config_data()
        chave = f"{tipo_adm.strip().upper()}-{nome_adm.strip().upper()}-{conta_id}"
        
        if "contas_mapeadas" in config and chave in config["contas_mapeadas"]:
            del config["contas_mapeadas"][chave]
            self.save_config_data(config)
            return True
        return False
