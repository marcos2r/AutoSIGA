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
        """Garante que a localidade ativa é 'ADM - DOURADOS - MS' e a competência bate com a fatura"""
        active_local = page.locator('li.green span.user-info').text_content() or ""
        active_comp = page.locator('span#f_competencianome').text_content() or ""

        loc_incorreta = "ADM - DOURADOS" not in active_local
        comp_incorreta = competencia_fatura and (active_comp.strip() != competencia_fatura.strip())

        if loc_incorreta or comp_incorreta:
            self.update_status(f"Ajustando localidade/competência para ADM - DOURADOS - MS ({competencia_fatura})...", "#428BCA")
            mes_encontrado = page.evaluate(f'''() => {{
                if ("{competencia_fatura}" !== "") {{
                    var selectMes = document.getElementById("f_competencia_webmaster");
                    if (selectMes) {{
                        for (let opt of selectMes.options) {{
                            if (opt.text.indexOf("{competencia_fatura}") > -1) {{
                                return true;
                            }}
                        }}
                    }}
                }}
                return false;
            }}''')

            if mes_encontrado:
                js_submit = f'''() => {{
                    var selectMes = document.getElementById("f_competencia_webmaster");
                    for (let opt of selectMes.options) {{
                        if (opt.text.indexOf("{competencia_fatura}") > -1) {{
                            if (window.jQuery) {{
                                window.jQuery("#form-competencia-competencia").val(opt.value);
                                window.jQuery("#form-competencia").submit();
                            }} else {{
                                document.getElementById("form-competencia-competencia").value = opt.value;
                                document.getElementById("form-competencia").submit();
                            }}
                            break;
                        }}
                    }}
                }}'''
                with page.expect_navigation(timeout=15000):
                    page.evaluate(js_submit)
                import time
                time.sleep(1.5)
                self.esperar_loading(page)
            else:
                self.update_status(f"⚠️ Mês de Trabalho {competencia_fatura} não encontrado no SIGA.", "#D9534F")
                import time
                time.sleep(1)
