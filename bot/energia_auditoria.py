"""
Auditoria de faturas de energia no SIGA (TES01501) e ajuste de localidade/competência.
"""

from datetime import datetime, timedelta

from controllers.provisao_energia import JA_LANCADA, JA_LANCADA_MANUAL, provisao_existente

# Janela de vencimento lida na Contas a Pagar em volta do vencimento da fatura
_JANELA_DIAS = 60


def _data(texto):
    try:
        return datetime.strptime((texto or "").strip(), "%d/%m/%Y")
    except ValueError:
        return None


class AuditoriaEnergiaMixin:
    """Consulta se a fatura já foi lançada e garante localidade e competência corretas."""

    def verificar_fatura_ja_lancada(self, page, numero_fatura, emissao=None, vencimento=None, fatura=None):
        """
        Consulta na Contas a Pagar (TES01501) se a fatura já tem provisão.

        Lê todas as provisões da Energisa com vencimento até 60 dias antes ou depois do da
        fatura. Com `fatura`, também reconhece a provisão lançada à mão (código de débito da
        UC no Nº Doc. e mesmo valor). Não engole erro: quem chama decide não lançar quando
        não dá para conferir, porque o SIGA é a única referência entre as máquinas.

        Returns:
            bool: True se a provisão já existe.

        Raises:
            Exception: Se a consulta falhar ou a grade vier cortada.
        """
        self.update_status(f"Verificando no SIGA se a fatura Nº {numero_fatura} já foi lançada...", "#428BCA")
        referencia = _data(vencimento) or _data(emissao) or datetime.now()
        periodo = ((referencia - timedelta(days=_JANELA_DIAS)).strftime("%d/%m/%Y"),
                   (referencia + timedelta(days=_JANELA_DIAS)).strftime("%d/%m/%Y"))
        provisoes = self._ler_provisoes_energisa(page, periodo)
        acao, _ = provisao_existente(fatura or {"numero_fatura": numero_fatura}, provisoes)
        return acao in (JA_LANCADA, JA_LANCADA_MANUAL)

    def _garantir_localidade_competencia(self, page, uc, competencia_fatura):
        """Garante que a localidade ativa no SIGA é a ADM e a competência bate com a fatura.

        Contas de energia ficam sempre na ADM, mesmo que o lote tenha terminado de conciliar
        um extrato do DR ou do PIA. Usa o modal "Outros Meses" (`_ajustar_localidade_competencia`)
        para trocar tanto a localidade quanto o mês de trabalho, e falha se o cabeçalho do SIGA
        não confirmar a troca.
        """
        nome_adm = next(
            (str(d.get("nome_adm", "")).strip() for d in getattr(self, "lote_processados", [])
             if isinstance(d, dict) and str(d.get("tipo_adm", "")).strip().upper() == "ADM"),
            "",
        )
        if self._contexto_ativo_confere(page, "ADM", nome_adm, competencia_fatura):
            return

        alvo = f"ADM - {nome_adm}" if nome_adm else "ADM"
        self.update_status(
            f"Ajustando localidade/competência para {alvo} ({competencia_fatura or 'mês atual'})...",
            "#428BCA",
        )
        if not self._ajustar_localidade_competencia(page, "ADM", nome_adm, competencia_fatura):
            raise RuntimeError(
                f"O SIGA não ficou em {alvo} ({competencia_fatura or 'mês atual'})."
            )
