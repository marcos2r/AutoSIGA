"""
Configurações de faturas de energia (Energisa) no config.json.

Separado do ConfigManager por responsabilidade: e-mail das faturas, localidades,
mapeamento UC -> localidade e faturas já lançadas. Entra no ConfigManager como
mixin, então os chamadores continuam usando config_manager.get_localidades_energia() etc.
"""

from typing import TYPE_CHECKING, Any


class ConfigEnergiaMixin:
    """Leitura e gravação das chaves de energia, via get_config_data/save_config_data."""

    if TYPE_CHECKING:
        def get_config_data(self) -> dict[str, Any]: ...
        def save_config_data(self, data: dict[str, Any]) -> None: ...

    def get_email_config(self):
        """
        Retorna as configurações de e-mail e corte.

        Returns:
            dict: {email, servidor}
        """
        config = self.get_config_data()
        return {
            "email": config.get("email_energia", ""),
            "servidor": config.get("servidor_imap_energia", "imap.gmail.com"),
        }

    def salvar_email_config(self, email, servidor):
        """
        Salva as configurações de e-mail.
        """
        config = self.get_config_data()
        config["email_energia"] = str(email).strip()
        config["servidor_imap_energia"] = str(servidor).strip()
        config.pop("mes_corte_energia", None)  # o corte agora é automático (mês anterior)
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
