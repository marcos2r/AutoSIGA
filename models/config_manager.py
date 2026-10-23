"""
Módulo de Gerenciamento de Configurações (Model).

Este módulo é responsável por isolar toda a lógica de persistência e
recuperação de dados locais da aplicação (I/O). Ele lida com o arquivo
'config.json', armazenando preferências do usuário como localidade
e mapeamentos de contas bancárias.
"""

import json
import logging
import os
from datetime import datetime

from caminhos import diretorio_base
from models.config_catalogo import ConfigCatalogoMixin
from models.config_energia import ConfigEnergiaMixin


class ConfigManager(ConfigEnergiaMixin, ConfigCatalogoMixin):
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
            config_path = os.path.join(diretorio_base(), "config.json")

        self.config_path = config_path

    def get_config_data(self):
        """
        Lê e retorna as configurações armazenadas no arquivo JSON local.

        Se não existir, retorna vazio. Se estiver ilegível, é preservado como backup
        antes de retornar vazio, para a próxima gravação não apagar os mapeamentos.

        Returns:
            dict: Dicionário contendo as configurações estruturadas.
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding='utf-8') as f:
                    config = json.load(f)
                if "contas_mapeadas" in config:
                    config = self._migrar_formato_antigo(config)
                return config
            except Exception as e:
                self._preservar_config_corrompido(e)
                return {}
        return {}

    def _preservar_config_corrompido(self, erro):
        """Renomeia um config.json ilegível para um backup com data e hora."""
        backup = f"{self.config_path}.corrompido-{datetime.now():%Y%m%d-%H%M%S}"
        try:
            os.replace(self.config_path, backup)
            logging.error(f"config.json ilegível ({erro}). Cópia preservada em: {backup}")
        except OSError as e:
            logging.error(f"config.json ilegível ({erro}) e não foi possível preservá-lo: {e}")

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
        mapeamentos_unicos: dict[tuple, dict] = {}
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
        # Grava num arquivo temporário e o troca pelo definitivo em uma única operação:
        # se o app fechar no meio da gravação, o config.json anterior continua íntegro.
        temp_path = f"{self.config_path}.tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.config_path)
        except Exception as e:
            logging.error(f"Erro ao salvar configurações: {e}", exc_info=True)

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

    def get_revisar_antes_de_lancar(self):
        """
        Retorna se o robô deve mostrar a prévia e esperar autorização antes de gravar no SIGA.
        """
        return bool(self.get_config_data().get("revisar_antes_de_lancar", False))

    def salvar_revisar_antes_de_lancar(self, ativo):
        """
        Persiste a preferência da prévia dos lançamentos.
        """
        config = self.get_config_data()
        config["revisar_antes_de_lancar"] = bool(ativo)
        self.save_config_data(config)

    def get_baixar_energia_pelo_extrato(self):
        """
        Retorna se o robô aprova e baixa as faturas de energia debitadas nos extratos (ligado por padrão).
        """
        return bool(self.get_config_data().get("baixar_energia_pelo_extrato", True))

    def salvar_baixar_energia_pelo_extrato(self, ativo):
        """
        Persiste a preferência da baixa das faturas de energia pelo extrato.
        """
        config = self.get_config_data()
        config["baixar_energia_pelo_extrato"] = bool(ativo)
        self.save_config_data(config)

    def get_revisar_baixas(self):
        """
        Retorna se o robô mostra a prévia das baixas de energia antes de gravar (ligado por padrão).
        """
        return bool(self.get_config_data().get("revisar_baixas", True))

    def salvar_revisar_baixas(self, ativo):
        """
        Persiste a preferência da prévia das baixas de energia.
        """
        config = self.get_config_data()
        config["revisar_baixas"] = bool(ativo)
        self.save_config_data(config)
