"""
Módulo de Automação Web (Bot).

Este módulo concentra toda a interação com o navegador através da biblioteca
Playwright. Ele é desenhado para agir como um "humano invisível" preenchendo
formulários no portal web do SIGA.
"""

import os
import time
import logging
import traceback
from playwright.sync_api import sync_playwright
from controllers.conciliador import Conciliador

class SigaBot:
    """
    Controlador do Navegador Playwright.
    
    A classe instancia o Microsoft Edge local em modo persistente, injeta cookies,
    fura formulários complexos do SIGA (como Select2 e Datepickers) e delega as
    perguntas/alertas para a View (via callbacks), sem nunca importar nada de GUI.
    """
    
    def __init__(self, dados_processados, localidade_selecionada, tipo_alvo, nome_alvo, callbacks):
        """
        Inicializa a configuração do bot de automação.
        
        Args:
            dados_processados (dict): O extrato OFX mapeado e filtrado.
            localidade_selecionada (str): String amigável da filial (para os logs).
            tipo_alvo (str): Sigla da filial alvo (ex: ADM, DR, PIA).
            nome_alvo (str): Nome da filial alvo (ex: SAO PAULO).
            callbacks (dict): Dicionário de funções para acionar a UI. Possui:
                - update_status(msg, color)
                - show_message(tipo, titulo, msg)
                - request_authorization(lancamentos_pendentes)
                - show_dashboard(telemetria, tempo_inicio)
                - on_finish()
        """
        self.dados_processados = dados_processados
        self.localidade_selecionada = localidade_selecionada
        self.tipo_alvo = tipo_alvo
        self.nome_alvo = nome_alvo
        self.callbacks = callbacks
        self.browser_aberto = False
        self._qtd_injecoes_efetuadas = 0
        self.esperando_autorizacao = False
        self.autorizou_importacao = False

    def update_status(self, msg, color="#666666"):
        """Envia um log de texto simples para o painel da interface."""
        logging.info(f"[STATUS] {msg}")
        if "update_status" in self.callbacks:
            self.callbacks["update_status"](msg, color)

    def show_message(self, tipo, titulo, msg):
        """Aciona um popup na interface para alertas e erros genéricos."""
        if "show_message" in self.callbacks:
            self.callbacks["show_message"](tipo, titulo, msg)

    def fechar_browser(self):
        """Força a finalização do loop principal do Playwright."""
        self.browser_aberto = False


    def selecionar_select2(self, page, select_id, termo_busca, dropdown_is_ajax=True):
        """
        Hack utilitário para forçar a interação em listas suspensas (Select2).
        
        Devido à arquitetura da biblioteca Select2, que mascara inputs reais 
        com elementos <div> e <ul> invisíveis, o Playwright falha em seleções simples.
        Este método bypassa localizando a box pai, aguardando o input temporário,
        digitando e esperando o retorno da rede (AJAX).
        
        Args:
            page (Page): Instância da aba atual do Playwright rodando.
            select_id (str): ID base do elemento select escondido no DOM.
            termo_busca (str): Texto a ser pesquisado (ex: Código da Conta).
            dropdown_is_ajax (bool): Define se o script deve tolerar delay de rede.
        """
        try:
            # 1. Clica na caixa visual para acender o modal do dropdown
            container = page.locator(f'#s2id_{select_id}')
            container.wait_for(state="visible", timeout=3000)
            
            classes = container.get_attribute("class") or ""
            if "select2-container-disabled" in classes:
                # Campo bloqueado via JS (somente leitura), abortamos a injeção.
                return
                
            container.click(timeout=3000)
            time.sleep(0.5)
            
            # 2. Digita no input temporário que nasce dinamicamente no final do <body>
            input_search = page.locator('#select2-drop:visible .select2-input')
            input_search.fill(str(termo_busca), timeout=3000)
            
            if dropdown_is_ajax:
                time.sleep(2.0) # Espera o SIGA buscar no servidor
            else:
                time.sleep(0.5) # O filtro é puramente local (JS Regex)
                
            # 3. Clica no primeiro item resultante
            opcao_li = page.locator('#select2-drop:visible .select2-results li.select2-result-selectable').first
            opcao_li.wait_for(state="visible", timeout=3000)
            opcao_li.click()
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"Falha ao usar Select2 {select_id} para o termo {termo_busca}: {e}")

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
                msg_comp = f"{tipo_nome} - {desc_tx}"
                page.evaluate(f'''
                    if (document.getElementById("f_complementoorigem")) document.getElementById("f_complementoorigem").value = "{msg_comp}";
                    if (document.getElementById("f_complementodestino")) document.getElementById("f_complementodestino").value = "{msg_comp}";
                    if (document.getElementById("f_complemento")) document.getElementById("f_complemento").value = "{msg_comp}";
                    if (document.getElementById("f_documentoorigem")) document.getElementById("f_documentoorigem").value = "OFX";
                    if (document.getElementById("f_documentodestino")) document.getElementById("f_documentodestino").value = "OFX";
                    if (document.getElementById("f_documento")) document.getElementById("f_documento").value = "OFX";
                ''')
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
            if "show_message" in self.callbacks:
                self.callbacks["show_message"]("info", "AutoSIGA", "Todos os lançamentos foram importados com sucesso! O robô agora fará a validação.")
            
        except Exception as e:
            logging.error(f"Erro inserindo lançamentos: {e}", exc_info=True)
            self.update_status(f"Falha na inserção: {e}", "#D9534F")

    def fluxo_automacao(self):
        """
        Coração assíncrono do bot. Roteiriza a abertura do navegador, injeção, e encerramento.
        
        Etapas:
        1. Contexto do Edge persistente (puxa os cookies de login).
        2. Tenta fazer login, caso o cookie tenha expirado.
        3. Entra na aba de seleção da Localidade e preenche os dropdowns invisíveis.
        4. Lê a rotina TES01701 e extrai o extrato HTML da empresa.
        5. Passa para o Conciliador fazer a matemática.
        6. Aguarda o Humano autorizar a injeção (caso existam pendências).
        7. Realiza nova conferência de sucesso após injeções e solta relatório de produtividade.
        """
        self.browser_aberto = True
        tempo_inicio = time.time()
        telemetria = {
            "ofx_itens": len(self.dados_processados.get("transacoes", [])),
            "siga_itens": 0,
            "injecoes": 0,
            "pendentes": 0
        }
        try:
            with sync_playwright() as p:
                user_data_dir = os.path.join(os.getcwd(), 'siga_browser_data')
                
                # Utiliza o Microsoft Edge nativo do sistema para fugir de problemas
                # de incompatibilidade do Webkit quando buildado em .exe (PyInstaller)
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    no_viewport=True,
                    channel="msedge",
                    args=["--start-maximized"]
                )
                
                page = context.pages[0] if context.pages else context.new_page()
                
                # Ferramenta para Logar no terminal python onde quer que o mouse clique
                # (Extremamente útil para o dev atualizar o bot se o sistema SIGA sofrer atualizações)
                page.on("console", lambda msg: logging.info(msg.text) if "SIGA-CLIQUE" in msg.text else None)
                page.add_init_script('''
                    document.addEventListener('click', function(e) {
                        let el = e.target;
                        let tags = [];
                        while(el && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                            let id_str = el.id ? '#' + el.id : '';
                            let class_str = (el.className && typeof el.className === 'string' && el.className.trim() !== '') ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
                            tags.unshift(el.tagName.toLowerCase() + id_str + class_str);
                            el = el.parentElement;
                        }
                        let info = 'SIGA-CLIQUE -> ' + tags.join(' > ');
                        if (e.target.innerText) {
                            info += ' || TEXTO: ' + e.target.innerText.trim().substring(0, 40).replace(/\\n/g, ' ');
                        }
                        console.log(info);
                    }, true);
                ''')
                
                self.update_status("Iniciando navegador e validando sessão...", "#428BCA")
                page.goto("https://siga.congregacao.org.br/")
                page.wait_for_load_state("domcontentloaded")
                
                try:
                    senha_locator = page.locator('input[type="password"]')
                    senha_locator.wait_for(state="visible", timeout=3000)
                    precisa_fazer_login = True
                except:
                    precisa_fazer_login = False
                
                if precisa_fazer_login:
                    self.update_status("Login Mestre de Hoje: não esqueça de marcar a caixa 'Lembrar me' para a próxima!", "#D9534F")
                    try:
                        # Assinala checkbox "Lembrar Senha" forçadamente se o usuário a ignorou
                        page.evaluate("() => { let cbs = document.querySelectorAll('input[type=\"checkbox\"]'); for(let cb of cbs) { if(cb.parentElement.innerText.match(/Lembrar/i) || cb.id.indexOf('lembr') > -1) { cb.checked = true; } } }")
                    except:
                        pass
                    # Trava o loop do bot até que a janela de senha não exista mais (Sinal de Logon validado)
                    senha_locator.wait_for(state="hidden", timeout=0)
                
                self.update_status("Sessão Validada. Verificando localidade...", "#428BCA")
                
                self.update_status("Ajustando configurações de Localidade e Mês de Trabalho...", "#428BCA")
                
                mes_ano_alvo = self.dados_processados.get("data_final", "")
                if len(mes_ano_alvo) >= 10:
                    mes_ano_alvo = mes_ano_alvo[3:] # Corta pro formato 'MM/YYYY'
                else:
                    mes_ano_alvo = ""

                page.locator('#a_competencia').click()
                time.sleep(1)
                
                page.locator('a.showModal:has-text("Outros Meses")').click()
                
                btn_confirmar = page.locator('form.modal-form button[type="submit"]:has-text("Confirmar")').first
                btn_confirmar.wait_for(state="attached", timeout=15000)
                time.sleep(1.5)
                
                js_select2 = f'''() => {{
                    var selectLoc = jQuery('select[name="f_estabelecimento"]');
                    if (selectLoc.length > 0) {{
                        var optLoc = selectLoc.find('option').filter(function() {{
                            var text = jQuery(this).text().toUpperCase();
                            return text.indexOf("{self.tipo_alvo}") > -1 && text.indexOf("{self.nome_alvo}") > -1;
                        }});
                        if (optLoc.length > 0) {{
                            selectLoc.val(optLoc.val()).trigger('change');
                        }}
                    }}
                    
                    if ("{mes_ano_alvo}" !== "") {{
                        var selectMes = jQuery('select[name="f_competencia"]');
                        if (selectMes.length > 0) {{
                            var optMes = selectMes.find('option:contains("{mes_ano_alvo}")');
                            if (optMes.length > 0) {{
                                selectMes.val(optMes.val()).trigger('change');
                            }}
                        }}
                    }}
                    
                    jQuery('#f-mudarpadrao').prop('checked', true);
                }}'''
                
                page.evaluate(js_select2)
                time.sleep(1.5)
                
                btn_confirmar.evaluate("el => el.click()")
                
                page.wait_for_load_state("domcontentloaded")
                time.sleep(3)
                
                if mes_ano_alvo:
                    self.update_status(f"✅ Logado em: {self.localidade_selecionada} ({mes_ano_alvo})", "#3C763D")
                else:
                    self.update_status(f"✅ Logado em: {self.localidade_selecionada}", "#3C763D")
                
                self.update_status("Acessando rotina TES01701...", "#428BCA")
                
                input_programa = page.locator('#f_executar_programa')
                btn_executar = page.locator('#btn_executar_programa')
                
                input_programa.wait_for(state="visible", timeout=10000)
                input_programa.fill("TES01701")
                time.sleep(0.5)
                
                # Exclui popups nativos que atrapalham a área de clique
                page.evaluate("document.querySelectorAll('.notificacao').forEach(e => e.remove());")
                
                btn_executar.click(force=True)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                
                self.update_status("Abrindo menu do Extrato...", "#428BCA")
                
                btn_extrato = page.locator('#btn-filtro')
                btn_extrato.wait_for(state="visible", timeout=10000)
                btn_extrato.click()
                time.sleep(1.5)
                
                self.update_status("Preenchendo Conta e Datas...", "#428BCA")
                
                conta_alvo = self.dados_processados.get("conta_siga_corrente", "")
                achou_conta = False
                
                # Varre a lista de contas na tela e dispara jQuery ao achar match
                if conta_alvo:
                    opcoes = page.locator('#f_conta option')
                    for i in range(opcoes.count()):
                        texto_opt = opcoes.nth(i).text_content()
                        if conta_alvo in texto_opt:
                            valor_id = opcoes.nth(i).get_attribute('value')
                            page.evaluate(f'$("#f_conta").val("{valor_id}").trigger("change")')
                            achou_conta = True
                            break
                            
                if not achou_conta:
                    self.update_status(f"⚠️ Conta '{conta_alvo}' não encontrada na lista!", "#D9534F")
                    time.sleep(3)
                    
                data_in = self.dados_processados.get("data_inicial", "")
                data_fim = self.dados_processados.get("data_final", "")
                
                if data_in:
                    page.locator('#f_data1').fill(data_in)
                if data_fim:
                    page.locator('#f_data2').fill(data_fim)
                    
                time.sleep(0.5)
                
                self.update_status("Consultando movimentações no banco...", "#F89406")
                page.locator('#f_main button[type="submit"].btn-success').click()
                
                page.wait_for_load_state("domcontentloaded")
                time.sleep(3)
                
                self.update_status("Lendo dados da tabela do SIGA...", "#428BCA")
                page.locator('#grid1').wait_for(state="visible", timeout=10000)
                
                # Extrai grid principal (Web Scraper)
                extrato_siga = page.evaluate('''() => {
                    let rows = document.querySelectorAll('#grid1 tbody tr');
                    let result = [];
                    for (let tr of rows) {
                        let tds = tr.querySelectorAll('td');
                        // Garante que é uma linha de valor (não ignorar cabeçalhos em <th>)
                        if (tds.length >= 8) {
                            result.push({
                                data: tds[0].innerText.trim(),
                                lote: tds[1].innerText.trim(),
                                documento: tds[2].innerText.trim(),
                                historico: tds[3].innerText.trim(),
                                origem: tds[4].innerText.trim(),
                                entrada: tds[5].innerText.trim(),
                                saida: tds[6].innerText.trim(),
                                saldo: tds[7].innerText.trim()
                            });
                        }
                    }
                    return result;
                }''')
                
                self.dados_processados["extrato_siga"] = extrato_siga
                qtd_siga = len(extrato_siga)
                
                self.update_status(f"Cruzando {qtd_siga} itens do SIGA com o OFX...", "#428BCA")
                
                novos_lancamentos = Conciliador.conciliar(self.dados_processados.get("transacoes", []), extrato_siga)
                
                if novos_lancamentos:
                    self.update_status(f"⚠️ Há {len(novos_lancamentos)} lançamentos para importar! Aguardando sua ação...", "#F89406")
                    
                    self.esperando_autorizacao = True
                    self.autorizou_importacao = False
                    
                    # Interrompe o processo e aciona a UI para apresentar o modal para o humano
                    if "request_authorization" in self.callbacks:
                        self.callbacks["request_authorization"](novos_lancamentos)
                        
                    # Busy Wait elegante aguardando a resposta humana na UI
                    while self.esperando_autorizacao:
                        if not self.browser_aberto:
                            break
                        time.sleep(1)
                        
                    if self.autorizou_importacao:
                        self.update_status("🚀 Lançamentos autorizados! Iniciando inserção...", "#428BCA")
                        self.inserir_lancamentos_siga(page, novos_lancamentos)
                        
                        self.update_status("Realizando conferência final no servidor...", "#428BCA")
                        time.sleep(2)
                        
                        try:
                            if page.locator('#btn-filtro').is_visible():
                                page.locator('#btn-filtro').click()
                                time.sleep(1)
                                
                            page.locator('#modal-filtro form#f_main button.btn-success').first.click()
                            page.wait_for_load_state("domcontentloaded")
                            time.sleep(4)
                            
                            extrato_recente = page.evaluate('''() => {
                                let rows = document.querySelectorAll('#grid1 tbody tr');
                                let r = [];
                                for (let tr of rows) {
                                    let tds = tr.querySelectorAll('td');
                                    if (tds.length >= 8) {
                                        r.push({
                                            data: tds[0].innerText.trim(), lote: tds[1].innerText.trim(),
                                            documento: tds[2].innerText.trim(), historico: tds[3].innerText.trim(),
                                            origem: tds[4].innerText.trim(), entrada: tds[5].innerText.trim(),
                                            saida: tds[6].innerText.trim(), saldo: tds[7].innerText.trim()
                                        });
                                    }
                                }
                                return r;
                            }''')
                            
                            self.dados_processados["extrato_siga"] = extrato_recente
                            pendentes = Conciliador.conciliar(self.dados_processados.get("transacoes", []), extrato_recente)
                            
                            telemetria["siga_itens"] = len(extrato_recente)
                            telemetria["pendentes"] = len(pendentes)
                            
                            if not pendentes:
                                self.update_status("✅ Conferência 100%: Nenhum item para trás!", "#3C763D")
                            else:
                                self.update_status(f"⚠️ Alerta: {len(pendentes)} itens não bateram no SIGA.", "#D9534F")
                                
                            if "show_dashboard" in self.callbacks:
                                self.callbacks["show_dashboard"](telemetria, tempo_inicio)
                                
                        except Exception as e:
                            logging.error(f"Erro na conferência final: {e}")
                            self.update_status("✅ Lançamentos finalizados (sem prova real)", "#3C763D")
                            
                    else:
                        self.update_status("❌ Importação cancelada pelo usuário.", "#D9534F")
                        
                else:
                    self.update_status("✅ Tudo conciliado! Nenhum lançamento novo faltando.", "#3C763D")
                    if "show_dashboard" in self.callbacks:
                        self.callbacks["show_dashboard"](telemetria, tempo_inicio)
                        
                # Mantém o Contexto aberto na tela para que o usuário avalie com seus próprios olhos
                self.browser_aberto = True
                while self.browser_aberto:
                    try:
                        # Se o navegador for fechado brutalmente via "X" da janela
                        if not context.pages:
                            break
                    except Exception:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            msg_erro = f"Erro inesperado na automação do SIGA: {e}"
            print(f"⚠️ {msg_erro}")
            logging.error(msg_erro, exc_info=True)
            traceback.print_exc()
            
            erro_resumido = str(e).split('\n')[0][:50]
            self.update_status(f"Erro no navegador: {erro_resumido}...", "#D9534F")
        finally:
            if "on_finish" in self.callbacks:
                self.callbacks["on_finish"]()
