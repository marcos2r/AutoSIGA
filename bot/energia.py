"""
Lançamento de faturas de energia no SIGA (TES01502).
"""

import logging
import os
import time

from caminhos import diretorio_base
from controllers.anexo_fatura import CONTA_DESPESA_ENERGIA, preparar_anexo


class EnergiaMixin:
    """Injeção das faturas de energia extraídas dos PDFs."""

    def inserir_faturas_energia_siga(self, page, faturas):
        """
        Preenche autonomamente a rotina de contas a pagar/provisão de energia no SIGA (TES01502).

        Args:
            page (Page): Página ativa no navegador.
            faturas (list): Lista de faturas processadas e validadas (com UC, valor, vencimento, caminho_arquivo).
        """
        try:

            qtd_injetada = 0
            competencias_fechadas = set()
            # Por que cada fatura não foi lançada (número -> motivo), para o painel
            self.motivos_energia = {}
            self.faturas_energia_sucesso = []
            faturas_sucesso = []

            for i, fat in enumerate(faturas):
                gravou = False
                try:
                    if not self.browser_aberto:
                        break

                    self._verificar_sessao_ativa(page)

                    vencimento = fat.get("vencimento", "")
                    emissao = fat.get("emissao", "")
                    numero_fatura = fat.get("numero_fatura", "")
                    valor = fat.get("valor", 0.0)
                    uc = fat.get("uc", "")
                    referencia = fat.get("referencia", "")
                    consumo = fat.get("consumo", "")
                    localidade_codigo = fat.get("localidade_codigo", "")
                    caminho_pdf = fat.get("caminho_arquivo", "")

                    from models.config_manager import ConfigManager
                    config_mgr = ConfigManager()
                    localidades_dict = {l["codigo"]: l["nome"] for l in config_mgr.get_localidades_energia()}
                    localidade_nome = localidades_dict.get(localidade_codigo, "")

                    self.update_status(f"Importando fatura {i+1}/{len(faturas)}: UC {uc} -> R$ {valor:.2f}", "#F89406")

                    # Extrai a competência correspondente ao mês de emissão (ex: "29/06/2026" -> "06/2026")
                    competencia_fatura = ""
                    if emissao and len(emissao.split('/')) == 3:
                        partes = emissao.split('/')
                        competencia_fatura = f"{partes[1]}/{partes[2]}"

                    if competencia_fatura and competencia_fatura in competencias_fechadas:
                        self.motivos_energia[numero_fatura] = f"competência {competencia_fatura} fechada no SIGA"
                        self.update_status(f"⚠️ Competência {competencia_fatura} já mapeada como fechada. Pulando fatura {numero_fatura}...", "#D9534F")
                        time.sleep(1)
                        continue

                    # Garante que a localidade ativa do SIGA é "ADM - DOURADOS - MS" e a competência é a da fatura
                    try:
                        self._garantir_localidade_competencia(page, uc, competencia_fatura)
                    except Exception as e_loc:
                        logging.warning(f"Não foi possível garantir localidade/competência no cabeçalho: {e_loc}")

                    # --- PRÉ-CHECK DE DUPLICIDADE ---
                    # Sempre no SIGA e logo antes de gravar: outra pessoa pode ter lançado em outra
                    # máquina. Sem número ou sem conseguir conferir, a fatura não é lançada.
                    if not numero_fatura:
                        self.motivos_energia[numero_fatura] = "o PDF não traz o número da fatura"
                        self.update_status(f"⚠️ Fatura da UC {uc} sem número: não lançada.", "#F89406")
                        continue
                    try:
                        ja_lancada = self.verificar_fatura_ja_lancada(page, numero_fatura, emissao=emissao,
                                                                      vencimento=vencimento, fatura=fat)
                    except Exception as e_check:
                        logging.error(f"Não foi possível conferir a fatura {numero_fatura} no SIGA: {e_check}", exc_info=True)
                        self.motivos_energia[numero_fatura] = "não deu para conferir no SIGA se já estava lançada"
                        self.update_status(f"⚠️ Não consegui conferir a fatura {numero_fatura} no SIGA: não lançada.", "#D9534F")
                        continue
                    if ja_lancada:
                        config_mgr.marcar_fatura_processada(numero_fatura)
                        self.motivos_energia[numero_fatura] = "já estava no SIGA (lançada em outra execução ou à mão)"
                        self.update_status(f"⚠️ Fatura Nº {numero_fatura} já foi lançada anteriormente. Pulando...", "#F89406")
                        time.sleep(1.5)
                        continue

                    # Navega para a rotina de lançamento de contas a pagar / provisão (TES01502)
                    page.locator('#f_executar_programa').fill("TES01502")
                    page.locator('#btn_executar_programa').click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2.5)
                    self.esperar_loading(page)

                    # 1. Preenche a data do Lançamento e a data do Documento (Emissão) driblando o datepicker e overlays
                    if emissao:
                        try:
                            page.evaluate(f'''() => {{
                                let dataEm = "{emissao}";

                                // Data Lançamento e Data Documento idênticas (mesmo mês de competência agora ajustado)
                                let inpLan = document.getElementById("f_lancamento");
                                if (inpLan) {{
                                    inpLan.value = dataEm;
                                    if (window.jQuery) {{
                                        window.jQuery(inpLan).datepicker('update', dataEm);
                                        window.jQuery(inpLan).trigger('change');
                                    }}
                                }}

                                // Data Documento
                                let inpEm = document.getElementById("f_emissao");
                                if (inpEm) {{
                                    inpEm.value = dataEm;
                                    if (window.jQuery) {{
                                        window.jQuery(inpEm).datepicker('update', dataEm);
                                        window.jQuery(inpEm).trigger('change');
                                    }}
                                }}

                                if (window.jQuery) {{
                                    window.jQuery('.datepicker').hide();
                                }}
                            }}''')
                        except Exception as e_datas:
                            logging.warning(f"Erro ao preencher datas de lançamento/emissão: {e_datas}")

                        time.sleep(1.5) # Aguarda o AJAX de validação de data do SIGA responder

                        mes_fechado = page.evaluate('''() => {
                            let hasError = false;
                            let modals = document.querySelectorAll('.bootbox.modal');
                            modals.forEach(m => {
                                if (m.innerText.includes('Fechamento de competência já realizado') ||
                                    m.innerText.includes('fora da Competência') ||
                                    m.innerText.includes('Fechamento mensal')) {
                                    hasError = true;
                                }
                                let closeBtn = m.querySelector('.bootbox-close-button') || m.querySelector('.close') || m.querySelector('.btn-primary');
                                if (closeBtn) closeBtn.click();
                                else m.remove();
                            });

                            let backdrop = document.querySelector('.modal-backdrop');
                            if (backdrop) backdrop.remove();

                            return hasError;
                        }''')

                        if mes_fechado:
                            competencias_fechadas.add(competencia_fatura)
                            self.motivos_energia[numero_fatura] = f"competência {competencia_fatura} fechada no SIGA"
                            self.update_status(f"⚠️ Competência {competencia_fatura} fechada ou data inválida. Pulando fatura {numero_fatura}...", "#D9534F")
                            time.sleep(2)
                            continue

                    # 2. Tipo Documento (Select2): Seleciona "NOTA FISCAL"
                    self.selecionar_select2(page, "f_tipodocumento", "NOTA FISCAL", dropdown_is_ajax=False)
                    time.sleep(0.5)

                    # 3. Nº Documento
                    if numero_fatura:
                        input_doc = page.locator('#f_documento')
                        if input_doc.count() > 0:
                            input_doc.fill("")
                            input_doc.type(str(numero_fatura))
                            time.sleep(0.5)

                    # 4. Valor
                    input_valor = page.locator('#f_valor')
                    if input_valor.count() > 0:
                        try:
                            page.evaluate(f'''() => {{
                                let el = document.getElementById("f_valor");
                                if (el && window.jQuery) {{
                                    window.jQuery(el).autoNumeric("set", {valor});
                                    window.jQuery(el).trigger("change");
                                    window.jQuery(el).trigger("blur");
                                }}
                            }}''')
                        except Exception as e_val:
                            logging.warning(f"Erro ao injetar f_valor via autoNumeric: {e_val}")
                        time.sleep(0.5)
                        try:
                            erro_fatal = page.evaluate('''() => {
                                let hasError = false;
                                let modals = document.querySelectorAll('.bootbox.modal');
                                modals.forEach(m => {
                                    if (m.innerText.includes('Fechamento de competência já realizado') ||
                                        m.innerText.includes('fora da Competência') ||
                                        m.innerText.includes('Fechamento mensal')) {
                                        hasError = true;
                                    }
                                    let closeBtn = m.querySelector('.bootbox-close-button') || m.querySelector('.close') || m.querySelector('.btn-primary');
                                    if (closeBtn) closeBtn.click();
                                    else m.remove();
                                });
                                let backdrop = document.querySelector('.modal-backdrop');
                                if (backdrop) backdrop.remove();
                                return hasError;
                            }''')
                            if erro_fatal:
                                competencias_fechadas.add(competencia_fatura)
                                self.motivos_energia[numero_fatura] = f"competência {competencia_fatura} fechada no SIGA"
                                self.update_status(f"⚠️ Competência fechada ou data inválida. Pulando fatura {numero_fatura}...", "#D9534F")
                                time.sleep(2)
                                continue
                        except Exception as e:
                            logging.warning(f"Não foi possível checar a competência da fatura {numero_fatura}: {e}")
                        time.sleep(0.5)

                    # 5. Rateio - Despesas (Select2): Seleciona a conta de energia elétrica ("3006")
                    self.selecionar_select2(page, "f_despesa_rateio", CONTA_DESPESA_ENERGIA, dropdown_is_ajax=False)
                    time.sleep(0.5)

                    # 6. Rateio - Centro de Custo (Select2): Mapeia baseado na localidade da UC
                    termo_cc = "ADM"
                    # Tenta extrair primeiro do próprio código da localidade (caso o usuário tenha inserido no formato BR 10-XXXX)
                    import re
                    if localidade_codigo:
                        match_cod = re.search(r'\d{2}-\d{4}', localidade_codigo)
                        if match_cod:
                            termo_cc = match_cod.group(0)

                    # Se não encontrou no código, tenta extrair do nome (para os casos pré-existentes como "BR 10-0244 - ...")
                    if termo_cc == "ADM" and localidade_nome:
                        match_cod = re.search(r'\d{2}-\d{4}', localidade_nome)
                        if match_cod:
                            termo_cc = match_cod.group(0)
                        elif "ADM" in localidade_nome.upper():
                            termo_cc = "ADM"
                        else:
                            partes = localidade_nome.split('-')
                            termo_cc = partes[-1].strip() if len(partes) > 1 else localidade_nome

                    self.selecionar_select2(page, "f_centrocusto_rateio", termo_cc, dropdown_is_ajax=False)
                    time.sleep(0.5)

                    # 7. Fornecedor (Select2): Busca e seleciona "ENERGISA"
                    self.selecionar_select2(page, "f_fornecedor", "ENERGISA", dropdown_is_ajax=True)
                    time.sleep(0.5)

                    # 8. Parcela 1 - Data Vencimento
                    if vencimento:
                        try:
                            page.evaluate(f'''() => {{
                                let inp = document.getElementById("f_datavencimento_1");
                                if (inp) {{
                                    inp.value = "{vencimento}";
                                    if (window.jQuery) {{
                                        window.jQuery(inp).datepicker('update', "{vencimento}");
                                        window.jQuery(inp).trigger('change');
                                        window.jQuery('.datepicker').hide();
                                    }}
                                }}
                            }}''')
                        except Exception as e_ven:
                            logging.warning(f"Erro ao preencher f_datavencimento_1: {e_ven}")
                        time.sleep(0.3)

                    # 9. Parcela 1 - Valor
                    input_valor_p = page.locator('#f_valor_1')
                    if input_valor_p.count() > 0:
                        try:
                            page.evaluate(f'''() => {{
                                let el = document.getElementById("f_valor_1");
                                if (el && window.jQuery) {{
                                    window.jQuery(el).autoNumeric("set", {valor});
                                    window.jQuery(el).trigger("change");
                                    window.jQuery(el).trigger("blur");
                                }}
                            }}''')
                        except Exception as e_val_p:
                            logging.warning(f"Erro ao injetar f_valor_1 via autoNumeric: {e_val_p}")
                        time.sleep(0.5)

                    # 10. Parcela 1 - Observação
                    obs_texto = f"PROVISÃO ENERGIA ELÉTRICA - UC {uc} - REF {referencia}"
                    if consumo:
                        obs_texto += f" - CONSUMO: {consumo} kWh"

                    input_obs = page.locator('input[name="f_observacao1"]')
                    if input_obs.count() > 0:
                        input_obs.fill("")
                        input_obs.type(obs_texto)
                        time.sleep(0.5)

                    # 11. Provisionamento - Conta de Provisão / Crédito (Select2)
                    self.selecionar_select2(page, "f_credito", "2000 - FORNECEDORES MATERIAIS DIVERSOS", dropdown_is_ajax=False)
                    time.sleep(0.5)

                    # 12. Provisionamento - Histórico (Select2)
                    self.selecionar_select2(page, "f_historico", "021 - NF", dropdown_is_ajax=False)
                    time.sleep(0.5)

                    # 13. Anexo PDF, renomeado com a conta de despesa e o centro de custo
                    # (ex: "3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf")
                    if caminho_pdf and os.path.exists(caminho_pdf):
                        self.update_status("Anexando PDF da fatura...", "#F89406")
                        try:
                            pasta_anexos = os.path.join(diretorio_base(), "faturas_temporarias", "anexos_siga")
                            caminho_anexo = preparar_anexo(caminho_pdf, localidade_codigo, localidade_nome, pasta_anexos)
                            input_file = page.locator('#f_anexos')
                            if input_file.count() == 0:
                                input_file = page.locator('input[type="file"]').first
                            input_file.set_input_files(caminho_anexo)
                            time.sleep(1.5)
                        except Exception as e_upload:
                            logging.warning(f"Não foi possível fazer upload do anexo: {e_upload}")
                        # A cópia não é apagada aqui: com o navegador local, o Playwright entrega
                        # o caminho e o arquivo só é lido ao gravar. A pasta faturas_temporarias
                        # é limpa na próxima importação de energia.

                    # Salvar (F para fechar no último/único, N para novo)
                    is_ultimo = (i == len(faturas) - 1)
                    if is_ultimo:
                        btn_gravar = page.locator('button.btn-salvar[data-comando="F"]')
                    else:
                        btn_gravar = page.locator('button.btn-salvar[data-comando="N"]')

                    # Antes de gravar, fecha qualquer modal de Atenção que possa ter brotado (ex: soma de parcelas)
                    try:
                        erro_fatal_gravar = page.evaluate('''() => {
                            let hasError = false;
                            let modals = document.querySelectorAll('.bootbox.modal');
                            modals.forEach(m => {
                                if (m.innerText.includes('Fechamento de competência já realizado') ||
                                    m.innerText.includes('fora da Competência') ||
                                    m.innerText.includes('Fechamento mensal')) {
                                    hasError = true;
                                }
                                let closeBtn = m.querySelector('.bootbox-close-button') || m.querySelector('.close') || m.querySelector('.btn-primary');
                                if (closeBtn) closeBtn.click();
                                else m.remove();
                            });
                            let backdrop = document.querySelector('.modal-backdrop');
                            if (backdrop) backdrop.remove();
                            return hasError;
                        }''')
                        if erro_fatal_gravar:
                            competencias_fechadas.add(competencia_fatura)
                            self.motivos_energia[numero_fatura] = f"competência {competencia_fatura} fechada no SIGA"
                            self.update_status(f"⚠️ Competência fechada impediu a gravação. Pulando fatura {numero_fatura}...", "#D9534F")
                            time.sleep(2)
                            continue
                    except Exception as e:
                        logging.warning(f"Não foi possível checar modais antes de gravar a fatura {numero_fatura}: {e}")
                    time.sleep(0.5)

                    if btn_gravar.count() > 0:
                        btn_gravar.first.click(force=True)
                        gravou = True
                    else:
                        page.locator('button.btn-success:has(i.icon-ok)').first.click(force=True)
                        gravou = True

                    page.wait_for_load_state("domcontentloaded")

                    # Bypassa modal de sucesso
                    self._confirmar_gravacao(page, timeout_ms=10000)

                    # Marca como processada
                    config_mgr.marcar_fatura_processada(fat.get("numero_fatura", ""))
                    faturas_sucesso.append(fat)
                    qtd_injetada += 1
                except Exception as e_fat:
                    # Uma fatura com erro não derruba as outras; se o Gravar já foi clicado, a
                    # auditoria final confere no SIGA se ela ficou gravada
                    num_erro = fat.get("numero_fatura", "")
                    logging.error(f"Erro ao lançar a fatura {num_erro}: {e_fat}", exc_info=True)
                    self._capturar_tela_e_log(page, "erro_fatura_energia")
                    if gravou:
                        faturas_sucesso.append(fat)
                    else:
                        resumo_erro = str(e_fat).splitlines()[0][:80] if str(e_fat) else type(e_fat).__name__
                        self.motivos_energia[num_erro] = f"erro ao lançar no SIGA ({resumo_erro})"
                    self.update_status(f"⚠️ Erro na fatura {num_erro}; seguindo para a próxima.", "#D9534F")

            # --- AUDITORIA FINAL ---
            if faturas_sucesso:
                self.update_status("🔍 Iniciando Auditoria Final no Banco do SIGA...", "#337AB7")
                sucessos_auditados = 0
                faturas_confirmadas = []
                for fat_aud in faturas_sucesso:
                    num_doc = fat_aud.get("numero_fatura", "")
                    emissao_aud = fat_aud.get("emissao", "")
                    venc_aud = fat_aud.get("vencimento", "")
                    uc_aud = fat_aud.get("uc", "")

                    if emissao_aud and len(emissao_aud.split('/')) == 3:
                        partes = emissao_aud.split('/')
                        comp_aud = f"{partes[1]}/{partes[2]}"
                        try:
                            self._garantir_localidade_competencia(page, uc_aud, comp_aud)
                        except Exception as e:
                            logging.warning(f"Auditoria: Erro ao ajustar competência para {comp_aud}: {e}")

                    # O verificar_fatura_ja_lancada vai cuidar de ir para o TES01501 e buscar a nota
                    try:
                        existe = self.verificar_fatura_ja_lancada(page, num_doc, emissao=emissao_aud, vencimento=venc_aud)
                    except Exception as e_aud:
                        logging.error(f"Auditoria: falha ao consultar a fatura {num_doc}: {e_aud}", exc_info=True)
                        existe = False
                    if existe:
                        self.update_status(f"✅ Auditoria: Fatura {num_doc} confirmada com SUCESSO!", "#3C763D")
                        sucessos_auditados += 1
                        faturas_confirmadas.append(fat_aud)
                    else:
                        self.update_status(f"❌ Auditoria: ALERTA! Fatura {num_doc} NÃO encontrada no banco!", "#D9534F")
                    time.sleep(1.5)

                self._qtd_injecoes_efetuadas = sucessos_auditados
                self.faturas_energia_sucesso = faturas_confirmadas
                if sucessos_auditados == len(faturas_sucesso):
                    self.update_status(f"✅ Auditoria Finalizada! {sucessos_auditados}/{len(faturas_sucesso)} faturas confirmadas no SIGA.", "#3C763D")
                else:
                    self.update_status(f"⚠️ Auditoria Finalizada! Apenas {sucessos_auditados}/{len(faturas_sucesso)} faturas foram validadas no SIGA.", "#F89406")
            else:
                self._qtd_injecoes_efetuadas = qtd_injetada
                self.faturas_energia_sucesso = []
                self.update_status("✅ Finalizado! 0 faturas de energia importadas no SIGA.", "#3C763D")

        except Exception as e:
            logging.error(f"Erro ao inserir faturas de energia: {e}", exc_info=True)
            self._capturar_tela_e_log(page, "erro_faturas_energia")
            self.update_status(f"Falha na injeção: {e}", "#D9534F")
