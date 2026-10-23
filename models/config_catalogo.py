"""
Catálogo de contas do SIGA no config.json.

Mixin do ConfigManager, como o de energia: guarda as contas bancárias lidas pela
descoberta (chave `catalogo_contas`) e ajuda a cruzar o catálogo com os mapeamentos
já confirmados. Um config.json antigo, sem a chave, continua carregando (catálogo vazio).
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from controllers.catalogo_contas import Catalogo, ContaSiga, so_digitos

VALIDADE_CATALOGO_DIAS = 30


class ConfigCatalogoMixin:
    """Leitura e gravação do catálogo, via get_config_data/save_config_data."""

    if TYPE_CHECKING:
        def get_config_data(self) -> dict[str, Any]: ...
        def save_config_data(self, data: dict[str, Any]) -> None: ...

    def get_catalogo(self) -> Catalogo:
        """Catálogo salvo, ou vazio se nunca foi lido ou se a chave estiver corrompida."""
        bruto = self.get_config_data().get("catalogo_contas")
        if not isinstance(bruto, dict):
            return Catalogo()
        contas = [ContaSiga.de_dict(c) for c in bruto.get("contas", []) if isinstance(c, dict)]
        return Catalogo(
            contas=[c for c in contas if c.codigo and c.grupo],
            lido_em=str(bruto.get("lido_em", "")),
            fonte=str(bruto.get("fonte", "")),
            localidades_sem_acesso=[str(s) for s in bruto.get("localidades_sem_acesso", [])],
        )

    def salvar_catalogo(self, catalogo: Catalogo) -> None:
        """Substitui o catálogo salvo; grava a data da leitura se ela vier vazia."""
        config = self.get_config_data()
        config["catalogo_contas"] = {
            "lido_em": catalogo.lido_em or datetime.now().isoformat(timespec="seconds"),
            "fonte": catalogo.fonte,
            "localidades_sem_acesso": list(catalogo.localidades_sem_acesso),
            "contas": [c.para_dict() for c in catalogo.contas],
        }
        self.save_config_data(config)

    @staticmethod
    def catalogo_vencido(catalogo: Catalogo, agora: datetime | None = None,
                         dias: int = VALIDADE_CATALOGO_DIAS) -> bool:
        """True se o catálogo nunca foi lido, tem data inválida ou passou da validade."""
        try:
            lido = datetime.fromisoformat(catalogo.lido_em)
        except ValueError:
            return True
        return (agora or datetime.now()) - lido > timedelta(days=dias)

    def localidade_preferida(self, conta_id: str) -> str:
        """Localidade ("TIPO - NOME") de um mapeamento já salvo da mesma conta bancária, ou ""."""
        alvo = so_digitos(conta_id)
        for m in self.get_config_data().get("mapeamentos", []):
            if alvo and so_digitos(m.get("conta_id", "")) == alvo and m.get("tipo_adm") and m.get("nome_adm"):
                return f"{m['tipo_adm']} - {m['nome_adm']}".upper()
        return ""

    def localidades_mapeadas(self) -> list[str]:
        """Localidades ("TIPO - NOME") usadas nos mapeamentos salvos, sem repetir."""
        vistas: list[str] = []
        for m in self.get_config_data().get("mapeamentos", []):
            if m.get("tipo_adm") and m.get("nome_adm"):
                loc = f"{m['tipo_adm']} - {m['nome_adm']}".upper()
                if loc not in vistas:
                    vistas.append(loc)
        return vistas
