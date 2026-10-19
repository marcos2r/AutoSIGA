"""
Módulo de Automação Web (Bot).

Este módulo concentra toda a interação com o navegador através da biblioteca
Playwright. Ele é desenhado para agir como um "humano invisível" preenchendo
formulários no portal web do SIGA.
"""

import time
import logging
import traceback
from playwright.sync_api import sync_playwright
from controllers.conciliador import Conciliador
from controllers.exportador import Exportador
from bot.siga_helpers import HelpersMixin
from bot.sessao import SessaoMixin
from bot.extratos import ExtratosMixin
from bot.energia_auditoria import AuditoriaEnergiaMixin
from bot.energia import EnergiaMixin
from bot.ofertas import OfertasMixin


class SigaBot(HelpersMixin, SessaoMixin, ExtratosMixin, AuditoriaEnergiaMixin, EnergiaMixin, OfertasMixin):
    """
    Controlador do Navegador Playwright.
    
    A classe instancia o Microsoft Edge local em modo persistente, injeta cookies,
    fura formulários complexos do SIGA (como Select2 e Datepickers) e delega as
    perguntas/alertas para a View (via callbacks), sem nunca importar nada de GUI.
    """
    
    def __init__(self, lote_processados, callbacks, tipo_lote="extrato"):
        """
        Inicializa a configuração do bot de automação em lote.
        
        Args:
            lote_processados (list): Lista de extratos mapeados e filtrados.
            callbacks (dict): Dicionário de funções para acionar a UI. Possui:
                - update_status(msg, color)
                - show_message(tipo, titulo, msg)
                - request_authorization(lancamentos_pendentes)
                - show_dashboard(telemetria, tempo_inicio)
                - on_finish()
            tipo_lote (str): Tipo de lote ("extrato", "energia" ou "ofertas").
        """
        # Ordena o lote por localidade_selecionada para agrupar os lançamentos da mesma filial,
        # minimizando as trocas de localidade no portal SIGA.
        self.lote_processados = sorted(
            lote_processados, 
            key=lambda x: f"{x.get('tipo_adm', '').strip().upper()} - {x.get('nome_adm', '').strip().upper()}"
        )
        self.callbacks = callbacks
        self.tipo_lote = tipo_lote
        self.browser_aberto = False
        self._qtd_injecoes_efetuadas = 0
        self.esperando_autorizacao = False
        self.autorizou_importacao = False
        self.faturas_energia_sucesso = []
        
        # Atributos reativos que serão setados a cada iteração do lote:
        self.dados_processados = None
        self.localidade_selecionada = ""
        self.tipo_alvo = ""
        self.nome_alvo = ""

    def update_status(self, msg, color="#666666"):
        """Envia um log de texto simples para o painel da interface."""
        logging.info(f"[STATUS] {msg}")
        if "update_progress" in self.callbacks:
            # Mantém a reatividade do terminal Windows limpa
            pass
        if "update_status" in self.callbacks:
            self.callbacks["update_status"](msg, color)

    def show_message(self, tipo, titulo, msg):
        """Aciona um popup na interface para alertas e erros genéricos."""
        if "show_message" in self.callbacks:
            self.callbacks["show_message"](tipo, titulo, msg)

    def fechar_browser(self):
        """Força a finalização do loop principal do Playwright."""
        self.browser_aberto = False

    def _aguardar_fechamento(self, context):
        """Mantém o navegador aberto para conferência até o usuário fechá-lo."""
        self.browser_aberto = True
        while self.browser_aberto:
            try:
                if not context.pages:
                    break
            except Exception:
                break
            time.sleep(1)

    def _fluxo_ofertas(self, page):
        """Importa o TXT de ofertas de cada conta corrente do lote na TES05602."""
        contas = [d for d in self.lote_processados if d.get("tipo_extrato") != "APLICACAO"]
        resultados = {"importado": 0, "duplicado": 0, "vazio": 0, "falha": 0}
        localidade_anterior = competencia_anterior = None

        for idx, dados in enumerate(contas):
            if not self.browser_aberto:
                break
            self._verificar_sessao_ativa(page)
            ofertas, _ = Exportador.filtrar_ofertas(dados.get("transacoes", []))
            _, _, competencia = Exportador.resumo_ofertas(ofertas)
            localidade = f"{dados['tipo_adm']}-{dados['nome_adm']}"
            if competencia and (localidade != localidade_anterior or competencia != competencia_anterior):
                if not self._ajustar_localidade_competencia(page, dados["tipo_adm"], dados["nome_adm"], competencia):
                    resultados["falha"] += 1
                    localidade_anterior = competencia_anterior = None
                    continue
                localidade_anterior, competencia_anterior = localidade, competencia

            # Uma conta com erro (ex: timeout ao abrir a tela) não interrompe as demais
            try:
                resultados[self.importar_ofertas_siga(page, dados)] += 1
            except Exception as e:
                logging.error(f"Erro ao importar ofertas da conta {dados.get('conta_id', '')}: {e}", exc_info=True)
                self._capturar_tela_e_log(page, "ofertas_erro")
                self.update_status(f"❌ Erro nas ofertas da conta {dados.get('conta_id', '')}: {str(e)[:60]}", "#D9534F")
                resultados["falha"] += 1
            if "update_progress" in self.callbacks:
                self.callbacks["update_progress"]((idx + 1) / len(contas))

        resumo = (f"Importadas: {resultados['importado']} | Já existentes: {resultados['duplicado']} | "
                  f"Sem ofertas: {resultados['vazio']} | Falhas: {resultados['falha']}")
        cor = "#D9534F" if resultados["falha"] else "#3C763D"
        self.update_status(f"Importação de ofertas concluída. {resumo}", cor)
        self.show_message("warning" if resultados["falha"] else "info", "Importação de Ofertas", resumo)

    def fluxo_automacao(self):
        """
        Coração assíncrono do bot. Roteiriza a abertura do navegador, injeção em lote e encerramento.
        """
        self.browser_aberto = True
        tempo_inicio = time.time()
        
        # Telemetria acumulada de todo o lote
        telemetria_lote = {
            "ofx_itens": sum(len(d.get("transacoes", [])) for d in self.lote_processados),
            "siga_itens": 0,
            "injecoes": 0,
            "pendentes": 0,
            "total_contas": len(self.lote_processados),
            "volume_financeiro": 0.0
        }
        
        try:
            with sync_playwright() as p:
                context, page = self._iniciar_navegador(p)

                self._validar_sessao(page)


                if self.tipo_lote == "energia":
                    self.update_status(f"Iniciando importação de {len(self.lote_processados)} faturas de energia...", "#428BCA")
                    self.inserir_faturas_energia_siga(page, self.lote_processados)
                    
                    telemetria_lote = {
                        "tipo_lote": "energia",
                        "ofx_itens": len(self.lote_processados),
                        "siga_itens": len(self.lote_processados),
                        "injecoes": self._qtd_injecoes_efetuadas,
                        "pendentes": len(self.lote_processados) - self._qtd_injecoes_efetuadas,
                        "total_contas": len(self.lote_processados),
                        "volume_financeiro": sum(f.get("valor", 0.0) for f in self.faturas_energia_sucesso)
                    }
                    if "update_progress" in self.callbacks:
                        self.callbacks["update_progress"](1.0)
                    
                    self.update_status("✅ Processamento de faturas de energia concluído!", "#3C763D")
                    if "show_dashboard" in self.callbacks:
                        self.callbacks["show_dashboard"](telemetria_lote, tempo_inicio)
                    
                    self.browser_aberto = True
                    while self.browser_aberto:
                        try:
                            if not context.pages:
                                break
                        except Exception:
                            break
                        time.sleep(1)
                    return
                
                if self.tipo_lote == "ofertas":
                    self._fluxo_ofertas(page)
                    self._aguardar_fechamento(context)
                    return

                localidade_anterior = None
                competencia_anterior = None
                
                for idx, dados_atual in enumerate(self.lote_processados):
                    if not self.browser_aberto:
                        break
                        
                    self._verificar_sessao_ativa(page)
                        
                    self.dados_processados = dados_atual
                    self.localidade_selecionada = dados_atual["localidade_selecionada"]
                    self.tipo_alvo = dados_atual["tipo_adm"]
                    self.nome_alvo = dados_atual["nome_adm"]
                    
                    # Soma o valor absoluto de cada transação do extrato no volume financeiro
                    for tx in self.dados_processados.get("transacoes", []):
                        telemetria_lote["volume_financeiro"] += abs(tx.get("valor", 0.0))
                        
                    self.update_status(f"[{idx+1}/{len(self.lote_processados)}] Processando {self.localidade_selecionada}...", "#428BCA")
                    
                    mes_ano_alvo = self.dados_processados.get("data_final", "")
                    if len(mes_ano_alvo) >= 10:
                        mes_ano_alvo = mes_ano_alvo[3:]
                    else:
                        mes_ano_alvo = ""

                    localidade_atual = f"{self.tipo_alvo}-{self.nome_alvo}"
                    
                    # Só troca de localidade e competência se for diferente do extrato anterior
                    if localidade_atual != localidade_anterior or mes_ano_alvo != competencia_anterior:
                        if not self._ajustar_localidade_competencia(page, self.tipo_alvo, self.nome_alvo, mes_ano_alvo):
                            # Não lança nada num mês/localidade diferente do extrato
                            telemetria_lote["pendentes"] += len(self.dados_processados.get("transacoes", []))
                            localidade_anterior = competencia_anterior = None
                            if "update_progress" in self.callbacks:
                                self.callbacks["update_progress"]((idx + 1) / len(self.lote_processados))
                            continue

                        localidade_anterior = localidade_atual
                        competencia_anterior = mes_ano_alvo
                        
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
                    
                    page.evaluate("document.querySelectorAll('.notificacao').forEach(e => e.remove());")
                    
                    btn_executar.click(force=True)
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                    
                    self.update_status("Abrindo menu do Extrato...", "#428BCA")
                    
                    btn_extrato = page.locator('#btn-filtro')
                    btn_extrato.wait_for(state="visible", timeout=10000)
                    btn_extrato.click()
                    time.sleep(1.5)
                    
                    is_aplicacao = (self.dados_processados.get("tipo_extrato") == "APLICACAO")
                    if is_aplicacao:
                        conta_alvo = self.dados_processados.get("conta_siga_aplicacao", "")
                    else:
                        conta_alvo = self.dados_processados.get("conta_siga_corrente", "")
                    achou_conta = False
                    
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
                    
                    extrato_siga = page.evaluate('''() => {
                        let rows = document.querySelectorAll('#grid1 tbody tr');
                        let result = [];
                        for (let tr of rows) {
                            let tds = tr.querySelectorAll('td');
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
                    telemetria_lote["siga_itens"] += qtd_siga
                    
                    self.update_status(f"Cruzando {qtd_siga} itens do SIGA com o OFX...", "#428BCA")
                    
                    novos_lancamentos = Conciliador.conciliar(self.dados_processados.get("transacoes", []), extrato_siga)
                    
                    if novos_lancamentos:
                        limite_tentativas = 3
                        tentativa = 1
                        pendentes = novos_lancamentos
                        
                        while pendentes and tentativa <= limite_tentativas:
                            if tentativa > 1:
                                self.update_status(f"🔄 Re-tentativa {tentativa}/{limite_tentativas}: Injetando {len(pendentes)} lançamentos restantes...", "#F89406")
                            else:
                                self.update_status(f"🚀 Importando automaticamente {len(pendentes)} lançamentos em {self.localidade_selecionada}...", "#428BCA")
                                
                            self._qtd_injecoes_efetuadas = 0
                            if is_aplicacao:
                                self.inserir_rendimentos_siga(page, pendentes)
                            else:
                                self.inserir_lancamentos_siga(page, pendentes)
                            
                            telemetria_lote["injecoes"] += self._qtd_injecoes_efetuadas
                            
                            self.update_status("Realizando conferência pós-lançamento...", "#428BCA")
                            time.sleep(2.5)
                            
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
                                
                                if not pendentes:
                                    self.update_status(f"✅ [{self.localidade_selecionada}] Conferência 100%: Nenhum item para trás!", "#3C763D")
                                    break
                            except Exception as e:
                                logging.error(f"Erro na conferência final: {e}")
                                self.update_status(f"✅ [{self.localidade_selecionada}] Finalizado sem prova real.", "#3C763D")
                                break
                                
                            tentativa += 1
                        
                        if pendentes:
                            telemetria_lote["pendentes"] += len(pendentes)
                            self.update_status(f"⚠️ [{self.localidade_selecionada}] Alerta: {len(pendentes)} itens não bateram após {limite_tentativas} tentativas.", "#D9534F")
                            
                    else:
                        self.update_status(f"✅ [{self.localidade_selecionada}] Tudo conciliado! Nenhum lançamento novo faltando.", "#3C763D")
                        
                    # Atualiza a barra de progresso na UI
                    if "update_progress" in self.callbacks:
                        progresso = (idx + 1) / len(self.lote_processados)
                        self.callbacks["update_progress"](progresso)
                        
                    time.sleep(2)
                
                self.update_status("✅ Todos os extratos do lote foram processados!", "#3C763D")
                if "show_dashboard" in self.callbacks:
                    self.callbacks["show_dashboard"](telemetria_lote, tempo_inicio)
                    
                self.browser_aberto = True
                while self.browser_aberto:
                    try:
                        if not context.pages:
                            break
                    except Exception:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            msg_erro = f"Erro inesperado na automação do SIGA: {e}"
            try:
                print(f"⚠️ {msg_erro}")
            except UnicodeEncodeError:
                print(f"[!] {msg_erro.encode('ascii', errors='replace').decode('ascii')}")
            logging.error(msg_erro, exc_info=True)
            traceback.print_exc()
            
            # Tenta capturar screenshot se page estiver acessível
            try:
                if 'page' in locals() and page:
                    self._capturar_tela_e_log(page, "erro_global")
            except Exception as ss_err:
                logging.warning(f"Não foi possível salvar o screenshot do erro global: {ss_err}")
                
            erro_resumido = str(e).split('\n')[0][:50]
            self.update_status(f"Erro no navegador: {erro_resumido}...", "#D9534F")
        finally:
            if "on_finish" in self.callbacks:
                self.callbacks["on_finish"]()
