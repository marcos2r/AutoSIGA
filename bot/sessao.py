"""
Abertura do navegador e validação de sessão (login) do SigaBot.
"""

import logging
import os
import time

from bot.navegador import conectar_edge
from caminhos import diretorio_base


class SessaoMixin:
    """Inicialização do Edge persistente e login no SIGA."""

    def _iniciar_navegador(self, p):
        """Conecta ao Edge do AutoSIGA (abrindo-o se preciso) e instala o log de cliques.

        O Edge é um programa à parte: continua aberto e logado quando o robô termina ou o
        AutoSIGA fecha, e a próxima execução reaproveita a mesma janela.

        Returns:
            tuple: (context, page) do Playwright.
        """
        # Ao lado do executável, independente da pasta de início do atalho
        user_data_dir = os.path.join(diretorio_base(), 'siga_browser_data')
        browser = conectar_edge(p, user_data_dir)
        context = browser.contexts[0] if browser.contexts else browser.new_context(no_viewport=True)

        # No Edge reaproveitado, prefere a aba que já está no SIGA (o Edge pode abrir abas de propaganda)
        abas_siga = [aba for aba in context.pages if "siga.congregacao" in aba.url]
        page = (abas_siga or context.pages or [None])[0] or context.new_page()
        page.bring_to_front()

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

        return context, page

    def _validar_sessao(self, page):
        """Garante o login no SIGA (Keyring, .env ou manual) e aguarda o dashboard."""
        self.update_status("Iniciando navegador e validando sessão...", "#428BCA")
        page.goto("https://siga.congregacao.org.br/")
        page.wait_for_load_state("domcontentloaded")

        try:
            senha_locator = page.locator('input[type="password"]')
            senha_locator.wait_for(state="visible", timeout=3000)
            precisa_fazer_login = True
        except Exception:
            precisa_fazer_login = False

        if precisa_fazer_login:
            # Tenta ler as credenciais do Windows Credential Manager via Keyring
            import keyring

            from models.config_manager import ConfigManager
            cfg = ConfigManager()
            usuario = cfg.get_usuario_siga()
            senha = keyring.get_password("AutoSIGA", usuario) if usuario else None
            if not (usuario and senha):
                # Fallback para credenciais do .env legadas se o keyring estiver limpo
                usuario = os.getenv("SIGA_USUARIO", "")
                senha = os.getenv("SIGA_SENHA", "")

            # O SIGA exige reCAPTCHA: o botão Entrar só habilita depois que o usuário
            # marca a caixa, então o bot apenas preenche os campos e não clica.
            preenchido = False
            if usuario and senha:
                try:
                    input_user = page.locator('input[type="text"], input[type="email"]').first
                    input_user.fill(usuario)
                    senha_locator.fill(senha)
                    preenchido = True
                except Exception as login_err:
                    logging.warning(f"Falha ao preencher as credenciais do SIGA: {login_err}")
            try:
                page.evaluate("() => { let cbs = document.querySelectorAll('input[type=\"checkbox\"]'); for(let cb of cbs) { if(cb.parentElement.innerText.match(/Lembrar/i) || cb.id.indexOf('lembr') > -1) { cb.checked = true; } } }")
            except Exception as e:
                logging.debug(f"Checkbox do login não marcado: {e}")

            if preenchido:
                self.update_status("Credenciais preenchidas: marque o reCAPTCHA e clique em Entrar no navegador.", "#D9534F")
            else:
                self.update_status("Faça o login no navegador (usuário, senha e reCAPTCHA) e clique em Entrar.", "#D9534F")

            # Aguarda o usuário concluir o login
            senha_locator.wait_for(state="hidden", timeout=0)

        self.update_status("Sessão Validada. Aguardando carregamento do sistema...", "#428BCA")

        # Aguarda o input de pesquisa do menu carregar, indicando que o dashboard principal apareceu
        try:
            page.locator('#f_executar_programa').wait_for(state="visible", timeout=30000)
        except Exception as e:
            logging.warning(f"O dashboard principal demorou a carregar ou não exibiu a barra de busca: {e}")

        # Agora sim, com o dashboard carregado, fechamos as notificações
        self.fechar_notificacoes(page)
        self.update_status("Sessão Validada. Iniciando processamento do lote...", "#428BCA")

    # O modal "Outros Meses" tem dois form.modal-form; só o que contém a localidade troca o contexto
    _FORM_LOCALIDADE = 'form.modal-form:has(select[name="f_estabelecimento"])'

    _JS_PREENCHER_CONTEXTO = '''([tipo, nome, mes]) => {
        var selectLoc = jQuery('select[name="f_estabelecimento"]').first();
        var form = selectLoc.closest('form');
        var opcoes = selectLoc.find('option');
        // Prefere a opção que começa com "TIPO - " (evita "DR" casar com outro nome qualquer)
        var optLoc = opcoes.filter(function() {
            var t = jQuery(this).text().toUpperCase().trim();
            return t.indexOf(tipo + " - ") === 0 && t.indexOf(nome) > -1;
        });
        if (optLoc.length === 0) {
            optLoc = opcoes.filter(function() {
                var t = jQuery(this).text().toUpperCase();
                return t.indexOf(tipo) > -1 && t.indexOf(nome) > -1;
            });
        }
        if (optLoc.length > 0) {
            selectLoc.val(optLoc.first().val()).trigger('change');
        }
        if (mes !== "") {
            var selectMes = form.find('select[name="f_competencia"]');
            var optMes = selectMes.find('option').filter(function() {
                return jQuery(this).text().indexOf(mes) > -1;
            });
            if (optMes.length > 0) {
                selectMes.val(optMes.first().val()).trigger('change');
            }
        }
        // Nunca "lembra a escolha": a troca vale só para esta sessão e não muda o padrão do usuário
        jQuery('#f-mudarpadrao').prop('checked', false);
    }'''

    def _ajustar_localidade_competencia(self, page, tipo_adm, nome_adm, mes_ano_alvo):
        """Troca a localidade e o Mês de Trabalho ativos no SIGA pelo modal "Outros Meses".

        Args:
            page: Página do Playwright no SIGA.
            tipo_adm (str): Tipo da localidade (ex: "ADM").
            nome_adm (str): Nome da localidade (ex: "DOURADOS - MS").
            mes_ano_alvo (str): Competência "mm/aaaa"; vazio mantém a atual.

        Returns:
            bool: True se, após a troca, o cabeçalho do SIGA mostra a localidade e o mês pedidos.
        """
        self.update_status("Ajustando configurações de Localidade e Mês de Trabalho...", "#428BCA")

        page.locator('#a_competencia').click()
        time.sleep(1)

        page.locator('a.showModal:has-text("Outros Meses")').click()

        btn_confirmar = page.locator(f'{self._FORM_LOCALIDADE} button[type="submit"]:has-text("Confirmar")').first
        btn_confirmar.wait_for(state="attached", timeout=15000)
        time.sleep(1.5)

        # Valores vão como argumento, não interpolados no JS
        page.evaluate(self._JS_PREENCHER_CONTEXTO,
                      [tipo_adm.strip().upper(), nome_adm.strip().upper(), mes_ano_alvo or ""])
        time.sleep(1.5)

        btn_confirmar.evaluate("el => el.click()")

        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        if self._contexto_ativo_confere(page, tipo_adm, nome_adm, mes_ano_alvo):
            return True
        # O modal ignora em silêncio um mês ou localidade inexistente: sem esta checagem,
        # os lançamentos cairiam no mês de trabalho que já estava ativo.
        self.update_status(f"❌ O SIGA não ficou em {tipo_adm} - {nome_adm} ({mes_ano_alvo or 'mês atual'}). "
                           "Confira se o mês de trabalho existe e está aberto.", "#D9534F")
        self._capturar_tela_e_log(page, "contexto_divergente")
        return False

    @staticmethod
    def _contexto_ativo_confere(page, tipo_adm, nome_adm, mes_ano_alvo):
        """Compara a localidade e o Mês de Trabalho exibidos no cabeçalho do SIGA com os esperados."""
        try:
            localidade = (page.locator('li.green span.user-info').first.text_content() or "").upper()
            competencia = (page.locator('span#f_competencianome').first.text_content() or "").strip()
        except Exception as e:
            logging.warning(f"Não foi possível ler o contexto ativo do SIGA: {e}")
            return False
        localidade_ok = tipo_adm.upper() in localidade and nome_adm.upper() in localidade
        competencia_ok = not mes_ano_alvo or competencia == mes_ano_alvo
        return localidade_ok and competencia_ok
