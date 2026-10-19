"""
Abertura do navegador e validação de sessão (login) do SigaBot.
"""

import os
import logging

from caminhos import diretorio_base


class SessaoMixin:
    """Inicialização do Edge persistente e login no SIGA."""

    def _iniciar_navegador(self, p):
        """Abre o Edge em contexto persistente e instala o log de cliques.

        Returns:
            tuple: (context, page) do Playwright.
        """
        # Ao lado do executável, independente da pasta de início do atalho
        user_data_dir = os.path.join(diretorio_base(), 'siga_browser_data')
        
        # Utiliza o Microsoft Edge nativo
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            no_viewport=True,
            channel="msedge",
            args=[
                "--start-maximized",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-gpu-compositing"
            ]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
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
        except:
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
            except Exception:
                pass

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
