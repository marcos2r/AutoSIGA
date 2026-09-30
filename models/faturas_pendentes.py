"""
Repositório de Faturas de Energia Pendentes (Model).

Guarda no config.json as faturas cuja UC ainda não foi relacionada a uma localidade.
Assim, uma fatura que o usuário deixou para depois (ou pulou por engano) não se perde:
ela volta a cada nova importação até ser mapeada e lançada, ou descartada de vez.
"""

import os

from models.config_manager import ConfigManager

CHAVE_CONFIG = "faturas_energia_pendentes"
CHAVE_DESCARTADAS = "faturas_energia_descartadas"

# Apenas os campos necessários para relançar a fatura. O texto bruto do PDF
# fica de fora para não inchar o config.json.
CAMPOS_PERSISTIDOS = (
    "uc", "valor", "vencimento", "numero_fatura",
    "emissao", "referencia", "consumo", "caminho_arquivo",
)


class FaturasPendentes:
    """
    Lista persistente de faturas de energia aguardando mapeamento de UC.

    Cada fatura é identificada pelo nome do PDF organizado (UC_REFERENCIA.pdf),
    que é único por unidade consumidora e mês de referência.
    """

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

    @staticmethod
    def chave(fatura: dict) -> str:
        """Retorna o identificador único da fatura (nome do arquivo PDF)."""
        return os.path.basename(fatura.get("caminho_arquivo", ""))

    def listar(self) -> list[dict]:
        """Retorna as faturas pendentes, na ordem em que foram registradas."""
        return list(self.config_manager.get_config_data().get(CHAVE_CONFIG, []))

    def adicionar(self, fatura: dict) -> None:
        """
        Registra (ou atualiza) uma fatura como pendente de mapeamento.

        Args:
            fatura (dict): Dados extraídos da fatura; precisa ter 'caminho_arquivo'.
        """
        chave = self.chave(fatura)
        if not chave:
            return

        registro = {campo: fatura.get(campo, "") for campo in CAMPOS_PERSISTIDOS}
        config = self.config_manager.get_config_data()
        pendentes = [p for p in config.get(CHAVE_CONFIG, []) if self.chave(p) != chave]
        pendentes.append(registro)
        config[CHAVE_CONFIG] = pendentes
        self.config_manager.save_config_data(config)

    def remover(self, fatura: dict) -> bool:
        """
        Tira a fatura da lista de pendentes (mapeada ou descartada pelo usuário).

        Returns:
            bool: True se a fatura estava na lista.
        """
        chave = self.chave(fatura)
        config = self.config_manager.get_config_data()
        pendentes = config.get(CHAVE_CONFIG, [])
        restantes = [p for p in pendentes if self.chave(p) != chave]
        if len(restantes) == len(pendentes):
            return False
        config[CHAVE_CONFIG] = restantes
        self.config_manager.save_config_data(config)
        return True

    def descartar(self, fatura: dict) -> None:
        """
        Remove a fatura das pendentes e lembra a decisão, para que ela não
        volte a ser perguntada se o mesmo e-mail for baixado novamente.
        """
        self.remover(fatura)
        config = self.config_manager.get_config_data()
        descartadas = config.get(CHAVE_DESCARTADAS, [])
        chave = self.chave(fatura)
        if chave and chave not in descartadas:
            descartadas.append(chave)
            config[CHAVE_DESCARTADAS] = descartadas
            self.config_manager.save_config_data(config)

    def foi_descartada(self, fatura: dict) -> bool:
        """Indica se o usuário já descartou esta fatura anteriormente."""
        descartadas = self.config_manager.get_config_data().get(CHAVE_DESCARTADAS, [])
        return self.chave(fatura) in descartadas
