"""
Fluxos de extratos bancários do SigaBot (TES01701/TES01703/TES01704).
"""

import time
import logging


class ExtratosMixin:
    """Lançamentos de extrato e de rendimentos no SIGA."""

    def inserir_lancamentos_siga(self, page, lancamentos):
        """
        Preenche autonomamente os formulários contábeis para injeção final.
        
        Este é o módulo mais agressivo do robô. Ele acessa a URL de lançamentos
        e estabelece o fluxo contábil de Origem e Destino baseado se a transação
        é um Débito (Aplicação) ou Crédito (Resgate).
        
        Emula a alta rotatividade clicando no botão "Salvar e Novo".
        
        Args:
            page (Page): Página ativa no navegador.
            lancamentos (list): A lista consolidada final expurgada de pendências.
        """
        try:
            # Ordenação exigida pela regra de negócio: Resgates primeiro, Aplicações depois.
            lanc_ordenados = sorted(lancamentos, key=lambda tx: tx.get("valor", 0.0), reverse=True)
            conta_corrente = self.dados_processados.get("conta_siga_corrente", "")
            conta_aplicacao = self.dados_processados.get("conta_siga_aplicacao", "")
            
            for i, tx in enumerate(lanc_ordenados):
                if not self.browser_aberto:
                    break
                    
                self._verificar_sessao_ativa(page)
                    
                data_tx = tx.get("data", "")
                valor_tx = tx.get("valor", 0.0)
                desc_tx = tx.get("descricao", "OFX")
                
                eh_resgate = valor_tx > 0
                tipo_nome = "RESGATE" if eh_resgate else "APLICAÇÃO"
                
                self.update_status(f"Lançando {i+1}/{len(lanc_ordenados)}: {tipo_nome} -> R$ {abs(valor_tx):.2f}", "#F89406")
                
                # Apenas necessita carregar a rotina no primeiro loop.
                # Nos demais, o SIGA zera o formulário sozinho por causa do 'Salvar e Novo'.
                if i == 0:
                    page.locator('#f_executar_programa').fill("TES01704")
                    page.locator('#btn_executar_programa').click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                else:
                    self.update_status("Preparando novo registro na tela atual...", "#F89406")
                    time.sleep(1)
                
                # Injeta a data driblando o calendário visual (Datepicker Bootstrap)
                page.evaluate(f'''() => {{
                    let inp = document.getElementById("f_data");
                    if (inp) {{
                        inp.value = "{data_tx}";
                        if (window.jQuery) {{
                            window.jQuery(inp).datepicker('update', "{data_tx}");
                            window.jQuery(inp).trigger('change');
                            window.jQuery('.datepicker').hide();
                        }} else {{
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }}''')
                
                time.sleep(1)
                # O SIGA pode emitir um pop-up avisando que a data do lançamento
                # diverge do mês de competência atual. Vamos prever e clicar 'Sim'.
                try:
                    btn_sim = page.locator('.bootbox button:has-text("Sim")').first
                    btn_sim.wait_for(state="visible", timeout=2000)
                    btn_sim.click()
                    time.sleep(0.5)
                except Exception:
                    pass
                
                # Preenche o Valor Numérico
                valor_str = f"{abs(valor_tx):.2f}".replace('.', ',')
                input_valor = page.locator('#f_valor')
                input_valor.click()
                input_valor.fill("")
                input_valor.type(valor_str)
                time.sleep(0.5)
                
                # Forma de pagamento hardcoded "TRANSF. BANCÁRIA"
                self.selecionar_select2(page, "f_formapagamento", "TRANSF. BANCÁRIA", dropdown_is_ajax=False)
                
                # Lógica de Partidas Dobradas Contábeis
                if eh_resgate:
                    str_orig = conta_aplicacao
                    str_dest = conta_corrente
                else:
                    str_orig = conta_corrente
                    str_dest = conta_aplicacao
                    
                self.selecionar_select2(page, "f_contaorigem", str_orig, dropdown_is_ajax=True)
                self.selecionar_select2(page, "f_conta", str_dest, dropdown_is_ajax=True)
                
                # 002: Lançamento padrão Aplicação, 031: Lançamento padrão Resgate
                codigo_historico = "002" if tx["valor"] < 0 else "031"
                self.selecionar_select2(page, "f_historicoorigem", codigo_historico, dropdown_is_ajax=True)
                self.selecionar_select2(page, "f_historico", codigo_historico, dropdown_is_ajax=True)
                
                # Dispara preenchimento em lote por JavaScript nos textareas de complemento
                desc_sanitizada = self.sanitizar_descricao(desc_tx)
                msg_comp = f"{tipo_nome} - {desc_sanitizada}"
                self._preencher_campos(page, {
                    "f_complementoorigem": msg_comp,
                    "f_complementodestino": msg_comp,
                    "f_complemento": msg_comp,
                    "f_documentoorigem": "OFX",
                    "f_documentodestino": "OFX",
                    "f_documento": "OFX",
                })
                time.sleep(1)
                
                # Verifica se está no fim da fila para não clicar em 'Salvar e Novo' à toa
                is_ultimo = (i == len(lanc_ordenados) - 1)
                
                if is_ultimo:
                    btn_gravar = page.locator('button.btn-salvar[data-comando="F"]')
                else:
                    btn_gravar = page.locator('button.btn-salvar[data-comando="N"]')
                    
                if btn_gravar.count() > 0:
                    btn_gravar.first.click()
                else:
                    page.locator('button.btn-success:has(i.icon-ok)').first.click()
                
                page.wait_for_load_state("domcontentloaded")
                
                # Bypassa a modal de confirmação de gravação bem sucedida
                try:
                    btn_sucesso = page.locator('.modal.in button:text-matches("Ok", "i")').first
                    btn_sucesso.wait_for(state="attached", timeout=25000)
                    time.sleep(1)
                    btn_sucesso.evaluate("el => el.click()")
                except Exception:
                    pass
                    
                time.sleep(1.5)
                
            self._qtd_injecoes_efetuadas = len(lanc_ordenados)
            self.update_status(f"✅ Finalizado! {len(lanc_ordenados)} registros injetados no SIGA.", "#3C763D")
            
        except Exception as e:
            logging.error(f"Erro inserindo lançamentos: {e}", exc_info=True)
            self._capturar_tela_e_log(page, "erro_inserir_lancamentos")
            self.update_status(f"Falha na inserção: {e}", "#D9534F")

    def inserir_rendimentos_siga(self, page, lancamentos):
        """
        Preenche autonomamente os formulários de receita para injeção final de rendimentos.
        
        Args:
            page (Page): Página ativa no navegador.
            lancamentos (list): A lista consolidada final expurgada de pendências.
        """
        try:
            # Ordenação por data (crescente)
            lanc_ordenados = sorted(lancamentos, key=lambda tx: tuple(map(int, reversed(tx.get("data", "").split("/")))) if "/" in tx.get("data", "") else tx.get("data", ""))
            conta_aplicacao = self.dados_processados.get("conta_siga_aplicacao", "")
            
            for i, tx in enumerate(lanc_ordenados):
                if not self.browser_aberto:
                    break
                    
                self._verificar_sessao_ativa(page)
                    
                data_tx = tx.get("data", "")
                valor_tx = tx.get("valor", 0.0)
                desc_tx = tx.get("descricao", "Rendimento")
                
                self.update_status(f"Lançando Rendimento {i+1}/{len(lanc_ordenados)}: R$ {valor_tx:.2f} ({data_tx})", "#F89406")
                
                # Apenas necessita carregar a rotina no primeiro loop.
                # Nos demais, o SIGA zera o formulário sozinho por causa do 'Salvar e Novo'.
                if i == 0:
                    page.locator('#f_executar_programa').fill("TES01703")
                    page.locator('#btn_executar_programa').click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                else:
                    self.update_status("Preparando novo registro na tela atual...", "#F89406")
                    time.sleep(1.5)
                
                # 1. Origem (Pessoa): Campo opcional ignorado para maior agilidade e portabilidade contábil
                # (Não é preenchido para evitar divergências de cadastro entre cooperativas regionais do Sicredi)
                
                # 2. Receita (Crédito): Selecionar "4100 - RENDA SOBRE APLICAÇÃO FINANCEIRA"
                self.selecionar_select2(page, "f_receita", "4100", dropdown_is_ajax=True)
                time.sleep(1.2) # Estabiliza reatividade AJAX da Receita
                
                # 3. Histórico (Crédito): Selecionar "029 - RENDAS BANCÁRIAS"
                self.selecionar_select2(page, "f_historico_credito", "029", dropdown_is_ajax=True)
                time.sleep(1.0)
                
                # 4. Injeta a data driblando o calendário visual (Datepicker Bootstrap)
                page.evaluate(f'''() => {{
                    let inp = document.getElementById("f_data");
                    if (inp) {{
                        inp.value = "{data_tx}";
                        if (window.jQuery) {{
                            window.jQuery(inp).datepicker('update', "{data_tx}");
                            window.jQuery(inp).trigger('change');
                            window.jQuery('.datepicker').hide();
                        }} else {{
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                }}''')
                
                time.sleep(1)
                # Popup de competência bootbox
                try:
                    btn_sim = page.locator('.bootbox button:has-text("Sim")').first
                    btn_sim.wait_for(state="visible", timeout=2000)
                    btn_sim.click()
                    time.sleep(0.5)
                except Exception:
                    pass
                
                # 5. Forma de Recebimento: "CRÉDITO EM CONTA" (opção '10')
                self.selecionar_select2(page, "f_formapagamento", "CRÉDITO EM CONTA", dropdown_is_ajax=False)
                
                # 6. Nº Documento: Pegar do extrato ou "0"
                doc_val = tx.get("documento", "0")
                if not doc_val or str(doc_val).strip() == "":
                    doc_val = "0"
                input_doc = page.locator('#f_documento')
                input_doc.click()
                input_doc.fill("")
                input_doc.type(str(doc_val))
                time.sleep(0.5)
                
                # 7. Valor Numérico
                valor_str = f"{abs(valor_tx):.2f}".replace('.', ',')
                input_valor = page.locator('#f_valor')
                input_valor.click()
                input_valor.fill("")
                input_valor.type(valor_str)
                time.sleep(0.5)
                
                # 8. Conta (Débito): Selecionar a Conta de Aplicação mapeada
                self.selecionar_select2(page, "f_conta", conta_aplicacao, dropdown_is_ajax=True)
                
                # 9. Histórico (Débito): Selecionar "029 - RENDAS BANCÁRIAS"
                self.selecionar_select2(page, "f_historico_debito", "029", dropdown_is_ajax=True)
                
                # 10. Complemento
                desc_sanitizada = self.sanitizar_descricao(desc_tx)
                msg_comp = f"RENDIMENTO - {desc_sanitizada}"
                self._preencher_campos(page, {"f_complemento": msg_comp})
                time.sleep(1)
                
                # 11. Salvar ou Salvar e Novo
                is_ultimo = (i == len(lanc_ordenados) - 1)
                if is_ultimo:
                    btn_gravar = page.locator('button.btn-salvar[data-comando="F"]')
                else:
                    btn_gravar = page.locator('button.btn-salvar[data-comando="N"]')
                    
                if btn_gravar.count() > 0:
                    btn_gravar.first.click()
                else:
                    page.locator('button.btn-success:has(i.icon-ok)').first.click()
                
                page.wait_for_load_state("domcontentloaded")
                
                # Bypassa a modal de confirmação de gravação bem sucedida
                try:
                    btn_sucesso = page.locator('.modal.in button:text-matches("Ok", "i")').first
                    btn_sucesso.wait_for(state="attached", timeout=25000)
                    time.sleep(1.2)
                    btn_sucesso.evaluate("el => el.click()")
                except Exception:
                    pass
                    
                time.sleep(1.5)
                
            self._qtd_injecoes_efetuadas = len(lanc_ordenados)
            self.update_status(f"✅ Finalizado! {len(lanc_ordenados)} rendimentos injetados no SIGA.", "#3C763D")
            if "show_message" in self.callbacks:
                self.callbacks["show_message"]("info", "AutoSIGA", "Todos os rendimentos foram importados com sucesso! O robô agora fará a validação.")
            
        except Exception as e:
            logging.error(f"Erro inserindo rendimentos: {e}", exc_info=True)
            self._capturar_tela_e_log(page, "erro_inserir_rendimentos")
            self.update_status(f"Falha na injeção: {e}", "#D9534F")
