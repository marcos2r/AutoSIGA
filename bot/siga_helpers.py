"""
Helpers de baixo nível do SigaBot: preenchimento de campos, Select2,
loading, notificações, verificação de sessão e captura de tela.
"""

import logging
import os
import time
import unicodedata

from caminhos import diretorio_base

# Limites da espera pelos resultados do Select2 (busca AJAX no servidor x filtro local)
TIMEOUT_SELECT2_AJAX = 10.0
TIMEOUT_SELECT2_LOCAL = 3.0
INTERVALO_POLL_SELECT2 = 0.2
# "Nenhum resultado" só encerra a espera depois disso: o Select2 3.x usa a mesma classe
# para "digite mais caracteres", que fica na tela até a busca disparar.
ESPERA_MIN_SEM_RESULTADO = 1.5


def _normalizar(texto):
    """Remove acentos, espaços e caixa para comparar textos do Select2."""
    if not texto:
        return ""
    t_clean = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')
    return "".join(t_clean.lower().split())


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

    _JS_MES_FECHADO = '''() => {
        let fechado = false;
        document.querySelectorAll('.bootbox.modal').forEach(m => {
            const t = m.innerText;
            if (t.includes('Fechamento de competência já realizado') || t.includes('fora da Competência')
                    || t.includes('Fechamento mensal')) {
                fechado = true;
                const fechar = m.querySelector('.bootbox-close-button') || m.querySelector('.close')
                    || m.querySelector('.btn-primary');
                if (fechar) fechar.click(); else m.remove();
            }
        });
        if (fechado) {
            const fundo = document.querySelector('.modal-backdrop');
            if (fundo) fundo.remove();
        }
        return fechado;
    }'''

    def _mes_fechado_na_tela(self, page):
        """True se o SIGA mostrou o aviso de competência fechada (e fecha o aviso)."""
        try:
            return bool(page.evaluate(self._JS_MES_FECHADO))
        except Exception as e:
            logging.debug(f"Não foi possível checar o aviso de mês fechado: {e}")
            return False

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
        except Exception as e:
            logging.debug(f"Falha ao fechar notificações: {e}")

    def esperar_loading(self, page):
        """
        Aguarda os overlays de loading/blockUI do SIGA desaparecerem.
        """
        try:
            time.sleep(0.5)
            # O SIGA empilha várias camadas .blockUI (fundo e mensagem); espera todas sumirem.
            # Um locator único falhava na hora com "strict mode violation" sem esperar nada.
            page.wait_for_function(
                "() => !Array.from(document.querySelectorAll('.blockUI')).some(e => e.getClientRects().length > 0"
                " && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none')",
                timeout=15000)
            self.fechar_notificacoes(page)
        except Exception as e:
            logging.warning(f"Loading do SIGA não terminou em 15 s: {e}")

    def _confirmar_gravacao(self, page, timeout_ms):
        """
        Fecha a modal "Ok" de gravação bem-sucedida e espera o SIGA liberar a tela.

        Substitui as pausas fixas antes e depois do clique: espera o botão ficar
        visível, clica, confere se a modal fechou (clica de novo uma vez, caso o
        primeiro clique tenha caído na animação de abertura) e aguarda o loading.

        Args:
            page (Page): Página ativa no navegador.
            timeout_ms (int): Limite para a modal de sucesso aparecer, em milissegundos.
        """
        try:
            btn_sucesso = page.locator('.modal.in button:text-matches("Ok", "i")').first
            btn_sucesso.wait_for(state="visible", timeout=timeout_ms)
            modal = page.locator('.modal.in').first
            for _ in range(2):
                btn_sucesso.evaluate("el => el.click()")
                try:
                    modal.wait_for(state="hidden", timeout=3000)
                    break
                except Exception:
                    logging.debug("[Gravação] Modal de sucesso ainda aberta; clicando em Ok de novo.")
        except Exception as e:
            logging.debug(f"[Gravação] Modal de sucesso não tratada: {e}")
        self.esperar_loading(page)

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
        normalizar = _normalizar
        tentativas = 3
        ultimo_erro = None

        # 1. Verifica se o Select2 já está com o valor correto para otimizar
        try:
            texto_inicial = page.locator(f'#s2id_{select_id} .select2-chosen').text_content() or ""
            if normalizar(termo_busca) in normalizar(texto_inicial):
                return
        except Exception as e:
            logging.debug(f"[Select2] Valor atual de '{select_id}' não lido: {e}")

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
                except Exception as e:
                    logging.debug(f"[Select2] API select2('open') indisponível em '{select_id}': {e}")
                container.click(timeout=3000, force=True)

                # 2. Digita no input temporário que nasce dinamicamente no final do <body>
                input_search = page.locator('#select2-drop:visible .select2-input')
                input_search.wait_for(state="visible", timeout=3000)
                input_search.fill("", timeout=3000)
                input_search.type(str(termo_busca), delay=10)

                timeout = TIMEOUT_SELECT2_AJAX if dropdown_is_ajax else TIMEOUT_SELECT2_LOCAL
                if not self._aguardar_resultados_select2(page, input_search, termo_busca, timeout):
                    logging.info(f"[Select2] Resultado para '{termo_busca}' em '{select_id}' não apareceu em {timeout}s; tentando selecionar assim mesmo.")

                # 3. Pressiona Enter no input_search para garantir a seleção e fechamento nativo
                input_search.press("Enter")
                try:
                    page.locator('#select2-drop').wait_for(state="hidden", timeout=1000)
                except Exception as e:
                    logging.debug(f"[Select2] Dropdown de '{select_id}' ainda aberto após Enter: {e}")

                # Tenta clicar no LI caso o Enter não tenha sido suficiente
                try:
                    opcao_li = page.locator('#select2-drop:visible .select2-results li.select2-result-selectable').first
                    if opcao_li.count() > 0:
                        opcao_li.click(force=True)
                except Exception as e:
                    logging.debug(f"[Select2] Clique na opção de '{select_id}' falhou: {e}")

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
                except Exception as e:
                    logging.debug(f"[Select2] Falha ao fechar o dropdown de '{select_id}': {e}")

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

    def _aguardar_resultados_select2(self, page, input_search, termo_busca, timeout):
        """
        Espera o dropdown do Select2 mostrar o resultado do termo digitado.

        Substitui as pausas fixas: consulta a lista a cada INTERVALO_POLL_SELECT2
        segundos e retorna assim que a primeira opção (a que o Enter seleciona)
        contém o termo. Se o SIGA pedir "tecle Enter" para disparar a busca AJAX,
        pressiona Enter uma vez e continua esperando.

        Args:
            page (Page): Página ativa no navegador.
            input_search (Locator): Campo de busca do dropdown aberto.
            termo_busca (str): Texto digitado no campo.
            timeout (float): Limite da espera, em segundos.

        Returns:
            bool: True se a opção apareceu ou o SIGA respondeu "nenhum resultado"
            antes do limite; False se o limite estourou.
        """
        termo_norm = _normalizar(termo_busca)
        enter_enviado = False
        msg_busca = page.locator('#select2-drop:visible .select2-searching').first
        primeira_opcao = page.locator('#select2-drop:visible .select2-results li.select2-result-selectable').first
        sem_resultado = page.locator('#select2-drop:visible .select2-no-results').first
        inicio = time.monotonic()
        limite = inicio + timeout

        while True:
            try:
                if msg_busca.count() > 0:
                    texto_msg = (msg_busca.text_content() or "").lower()
                    # Busca AJAX que só dispara com Enter
                    if not enter_enviado and ("tecle enter" in texto_msg or "enter para" in texto_msg):
                        input_search.press("Enter")
                        enter_enviado = True
                elif primeira_opcao.count() > 0 and termo_norm in _normalizar(primeira_opcao.text_content()):
                    return True
                elif sem_resultado.count() > 0 and time.monotonic() - inicio >= ESPERA_MIN_SEM_RESULTADO:
                    return True
            except Exception as e:
                # O dropdown é recriado durante a busca; tenta de novo na próxima volta
                logging.debug(f"[Select2] Dropdown instável ao ler resultados: {e}")

            if time.monotonic() >= limite:
                return False
            time.sleep(INTERVALO_POLL_SELECT2)
