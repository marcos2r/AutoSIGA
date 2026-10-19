"""
Helpers de baixo nível do SigaBot: preenchimento de campos, Select2,
loading, notificações, verificação de sessão e captura de tela.
"""

import os
import time
import logging
from caminhos import diretorio_base


class HelpersMixin:
    """Utilitários de interação com a página do SIGA usados pelos fluxos do bot."""

    @staticmethod
    def sanitizar_descricao(texto):
        """
        Sanitiza a descrição removendo aspas duplas, simples e outros caracteres
        que possam quebrar a injeção via código JavaScript ou causar erros no ASP.
        """
        if not texto:
            return ""
        # Remove caracteres de controle de quebra de linha
        t = str(texto).replace("\n", " ").replace("\r", " ")
        # Substitui aspas por aspas simples ou as remove
        t = t.replace('"', '').replace("'", "")
        # Remove caracteres de barra invertida que escapam injeções de string js
        t = t.replace("\\", "/")
        # Remove outros caracteres perigosos comuns
        for char in ["&", "<", ">", "%", "*", ";", "`", "$"]:
            t = t.replace(char, "")
        return t.strip()

    @staticmethod
    def _preencher_campos(page, valores):
        """
        Preenche campos do formulário do SIGA por id, ignorando os que não existem na tela.

        Os valores vão como argumento do page.evaluate (serializados pelo Playwright),
        nunca concatenados no código JavaScript, então aspas ou barras vindas do extrato
        não conseguem quebrar nem alterar o script executado.

        Args:
            page (Page): Página ativa no navegador.
            valores (dict): Mapa {id_do_campo: valor}.
        """
        page.evaluate('''(valores) => {
            for (const [id, valor] of Object.entries(valores)) {
                const campo = document.getElementById(id);
                if (campo) campo.value = valor;
            }
        }''', valores)

    def _capturar_tela_e_log(self, page, identificador):
        """
        Tira um screenshot da página ativa e grava no diretório de logs.
        
        Args:
            page (Page): Instância da página ativa do Playwright.
            identificador (str): Nome descritivo para compor o nome do arquivo.
        """
        try:
            log_dir = os.path.join(diretorio_base(), "logs")
            screenshot_dir = os.path.join(log_dir, "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
            filename = f"erro_{identificador}_{timestamp}.png"
            filepath = os.path.join(screenshot_dir, filename)
            
            # Tira o screenshot da página inteira
            page.screenshot(path=filepath, full_page=True)
            logging.info(f"[AUDITORIA] Screenshot de erro salvo em: {filepath}")
        except Exception as e:
            logging.warning(f"Falha ao realizar captura de tela para auditoria: {e}")

    def _verificar_sessao_ativa(self, page):
        """
        Inspeciona a aba do navegador para verificar se a sessão do SIGA continua ativa.
        
        Caso tenha sido deslogado ou redirecionado para a tela de login, lança um erro.
        """
        try:
            url_atual = page.url
            if "/login" in url_atual or "login.php" in url_atual:
                raise ConnectionError("A sessão do SIGA expirou e foi redirecionada para a tela de login.")
            
            # Se o campo de senha do login principal reaparecer no DOM e estiver visível
            senha_locator = page.locator('input[type="password"]')
            if senha_locator.count() > 0 and senha_locator.first.is_visible():
                raise ConnectionError("A tela de autenticação do SIGA foi detectada. Sessão inativa.")
        except Exception as e:
            if isinstance(e, ConnectionError):
                raise e

    def fechar_notificacoes(self, page):
        """
        Fecha popups de notificação e alertas globais que podem cobrir elementos da página e atrapalhar os cliques.
        """
        try:
            page.evaluate('''() => {
                var notificacoes = document.querySelectorAll('.notificacao');
                if (notificacoes) {
                    notificacoes.forEach(n => n.style.display = 'none');
                }
                var widgets = document.querySelectorAll('.widget-box.showNotificacao');
                if (widgets) {
                    widgets.forEach(w => w.remove());
                }
            }''')
        except Exception:
            pass

    def esperar_loading(self, page):
        """
        Aguarda os overlays de loading/blockUI do SIGA desaparecerem.
        """
        try:
            time.sleep(0.5)
            page.locator('.blockUI').wait_for(state="hidden", timeout=15000)
            self.fechar_notificacoes(page)
        except Exception:
            pass

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
        import unicodedata
        
        def normalizar(t):
            if not t:
                return ""
            t_clean = unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('ASCII')
            return "".join(t_clean.lower().split())

        tentativas = 3
        ultimo_erro = None

        # 1. Verifica se o Select2 já está com o valor correto para otimizar
        try:
            texto_inicial = page.locator(f'#s2id_{select_id} .select2-chosen').text_content() or ""
            if normalizar(termo_busca) in normalizar(texto_inicial):
                return
        except Exception:
            pass

        for tentativa in range(1, tentativas + 1):
            try:
                container = page.locator(f'#s2id_{select_id}')
                container.wait_for(state="visible", timeout=3000)
                
                classes = container.get_attribute("class") or ""
                if "select2-container-disabled" in classes:
                    # Campo bloqueado via JS (somente leitura), abortamos a injeção.
                    return
                    
                # Tenta abrir via API do Select2 nativo primeiro, fallback para click
                try:
                    page.evaluate(f"if (window.jQuery) window.jQuery('#{select_id}').select2('open');")
                except Exception:
                    pass
                container.click(timeout=3000, force=True)
                time.sleep(1.0)
                
                # 2. Digita no input temporário que nasce dinamicamente no final do <body>
                input_search = page.locator('#select2-drop:visible .select2-input')
                input_search.fill("", timeout=3000)
                input_search.type(str(termo_busca), delay=10)
                
                # Verifica dinamicamente se o Select2 exige pressionar Enter para disparar a busca AJAX
                try:
                    msg_busca = page.locator('#select2-drop:visible .select2-searching').first
                    if msg_busca.count() > 0:
                        texto_msg = msg_busca.text_content() or ""
                        texto_msg_lower = texto_msg.lower()
                        if "tecle enter" in texto_msg_lower or "enter para" in texto_msg_lower:
                            input_search.press("Enter")
                            # Dá um tempo extra para a busca AJAX do servidor responder
                            time.sleep(1.8)
                except Exception:
                    pass
                
                if dropdown_is_ajax:
                    time.sleep(1.2) # Espera o SIGA carregar
                else:
                    time.sleep(0.5) # Filtro local instantâneo
                    
                # 3. Pressiona Enter no input_search para garantir a seleção e fechamento nativo
                input_search.press("Enter")
                time.sleep(0.5)

                # Tenta clicar no LI caso o Enter não tenha sido suficiente
                try:
                    opcao_li = page.locator('#select2-drop:visible .select2-results li.select2-result-selectable').first
                    if opcao_li.count() > 0:
                        opcao_li.click(force=True)
                        time.sleep(0.5)
                except Exception:
                    pass
                
                # Limpa o mask e o dropdown usando a API nativa do Select2 para desvincular eventos de teclado globais
                try:
                    page.evaluate(f'''() => {{
                        if (window.jQuery) {{
                            // Fecha via API nativa para limpar os listeners de teclado do document
                            window.jQuery('#{select_id}').select2('close');
                            
                            // Garante a remoção visual por segurança
                            let mask = document.getElementById('select2-drop-mask');
                            if (mask) mask.style.display = 'none';
                            window.jQuery('#select2-drop').css('display', 'none');
                            window.jQuery('.select2-drop-active').removeClass('select2-drop-active');
                        }}
                    }}''')
                except Exception:
                    pass

                # Validação de estado pós-seleção
                texto_selecionado = page.locator(f'#s2id_{select_id} .select2-chosen').text_content() or ""
                if normalizar(termo_busca) in normalizar(texto_selecionado):
                    logging.info(f"[Select2] Sucesso ao selecionar '{termo_busca}' no campo '{select_id}' na tentativa {tentativa}.")
                    return
                else:
                    raise ValueError(f"Texto selecionado '{texto_selecionado}' não corresponde ao termo buscado '{termo_busca}'.")

            except Exception as e:
                ultimo_erro = e
                logging.warning(f"[Select2] Falha na tentativa {tentativa}/{tentativas} para selecionar '{termo_busca}' em '{select_id}': {e}")
                time.sleep(1.5)

        erro_msg = f"Falha definitiva ao usar Select2 {select_id} para o termo {termo_busca} após {tentativas} tentativas. Último erro: {ultimo_erro}"
        logging.error(erro_msg)
        self._capturar_tela_e_log(page, f"select2_{select_id}")
        raise RuntimeError(erro_msg) from ultimo_erro
