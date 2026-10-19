"""
Auditoria de faturas de energia no SIGA (TES01501) e ajuste de localidade/competência.
"""

import logging
import time


class AuditoriaEnergiaMixin:
    """Consulta se a fatura já foi lançada e garante localidade e competência corretas."""

    def verificar_fatura_ja_lancada(self, page, numero_fatura, emissao=None, vencimento=None):
        """
        Consulta na rotina TES01501 se a fatura já foi lançada anteriormente.
        Retorna True se já existir lançamento, False caso contrário.
        """
        try:
            self.update_status(f"Verificando no SIGA se fatura Nº {numero_fatura} já foi lançada...", "#428BCA")

            # Navega para a rotina de Consulta de Contas a Pagar (TES01501)
            page.locator('#f_executar_programa').fill("TES01501")
            page.locator('#btn_executar_programa').click()
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            self.esperar_loading(page)

            # Ajusta o período de busca com base na data da fatura
            data_ini = "01/01/2026"
            data_fim = "31/12/2026"
            ref_data = emissao or vencimento
            if ref_data:
                try:
                    from datetime import datetime, timedelta
                    dt_ref = datetime.strptime(ref_data, "%d/%m/%Y")
                    data_ini = (dt_ref - timedelta(days=60)).strftime("%d/%m/%Y")
                    data_fim = (dt_ref + timedelta(days=60)).strftime("%d/%m/%Y")
                except Exception:
                    pass

            # Preenche as datas no formulário de filtro via JS para evitar erros de elemento invisível
            try:
                page.evaluate(f'''() => {{
                    let inp1 = document.getElementById("f_data1");
                    if (inp1) {{
                        inp1.value = "{data_ini}";
                        if (window.jQuery) window.jQuery(inp1).trigger('change');
                    }}
                    let inp2 = document.getElementById("f_data2");
                    if (inp2) {{
                        inp2.value = "{data_fim}";
                        if (window.jQuery) window.jQuery(inp2).trigger('change');
                    }}
                }}''')
            except Exception as e_datas:
                logging.warning(f"Erro ao preencher datas de filtro: {e_datas}")
            time.sleep(0.5)

            # Se o modal de filtros f_main estiver aberto, clica em Consultar diretamente
            btn_consultar = page.locator('form#f_main button[type="submit"]:has-text("Consultar")')
            if btn_consultar.count() > 0 and btn_consultar.first.is_visible():
                btn_consultar.first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                self.esperar_loading(page)

            # Filtra pelo número do documento no campo de busca do datatable
            search_input = page.locator('div#grid1_filter input[type="search"], input[aria-controls="grid1"], div#grid1_filter input')
            if search_input.count() > 0:
                search_input.first.fill(str(numero_fatura))
                search_input.first.press("Enter")
                time.sleep(1.5)
                self.esperar_loading(page)

                # Verifica se há alguma linha na tabela contendo o número do documento exato na coluna de Nº Doc. (5ª coluna)
                rows = page.locator('table#grid1 tbody tr')
                for k in range(rows.count()):
                    row = rows.nth(k)
                    row_text = row.text_content() or ""
                    if "nenhum registro" in row_text.lower() or "não encontrado" in row_text.lower():
                        continue

                    doc_cell = row.locator('td').nth(4) # 5ª coluna (index 4)
                    if doc_cell.count() > 0:
                        doc_val = doc_cell.text_content() or ""
                        if str(numero_fatura).strip() in doc_val.strip():
                            return True
            return False
        except Exception as e_check:
            logging.error(f"Erro ao verificar se fatura {numero_fatura} já foi lançada: {e_check}", exc_info=True)
            return False

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
