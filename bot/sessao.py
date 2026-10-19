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
            usuario_siga = cfg.get_usuario_siga()
            senha_siga = keyring.get_password("AutoSIGA", usuario_siga) if usuario_siga else None
            
            if usuario_siga and senha_siga:
                self.update_status("Realizando login automático seguro com credenciais do Keyring...", "#428BCA")
                try:
                    # Preenche o login (geralmente e-mail ou CPF, campo de texto perto da senha)
                    input_user = page.locator('input[type="text"], input[type="email"]').first
                    input_user.fill(usuario_siga)
                    page.locator('input[type="password"]').fill(senha_siga)
                    
                    # Marca a caixa 'Lembrar me'
                    page.evaluate("() => { let cbs = document.querySelectorAll('input[type=\"checkbox\"]'); for(let cb of cbs) { if(cb.parentElement.innerText.match(/Lembrar/i) || cb.id.indexOf('lembr') > -1) { cb.checked = true; } } }")
                    
                    # Submete o formulário
                    btn_entrar = page.locator('button[type="submit"], input[type="submit"]').first
                    btn_entrar.click()
                    page.wait_for_load_state("domcontentloaded")
                except Exception as login_err:
                    logging.warning(f"Falha na tentativa de login automático seguro: {login_err}")
            else:
                # Fallback para credenciais do .env legadas se o keyring estiver limpo
                usuario_env = os.getenv("SIGA_USUARIO", "")
                senha_env = os.getenv("SIGA_SENHA", "")
                if usuario_env and senha_env:
                    self.update_status("Realizando login automático de fallback com credenciais do .env...", "#428BCA")
                    try:
                        input_user = page.locator('input[type="text"], input[type="email"]').first
                        input_user.fill(usuario_env)
                        page.locator('input[type="password"]').fill(senha_env)
                        page.evaluate("() => { let cbs = document.querySelectorAll('input[type=\"checkbox\"]'); for(let cb of cbs) { if(cb.parentElement.innerText.match(/Lembrar/i) || cb.id.indexOf('lembr') > -1) { cb.checked = true; } } }")
                        btn_entrar = page.locator('button[type="submit"], input[type="submit"]').first
                        btn_entrar.click()
                        page.wait_for_load_state("domcontentloaded")
                    except Exception as env_login_err:
                        logging.warning(f"Falha na tentativa de login automático de fallback: {env_login_err}")
                else:
                    self.update_status("Login Mestre de Hoje: não esqueça de marcar a caixa 'Lembrar me' para a próxima!", "#D9534F")
                    try:
                        page.evaluate("() => { let cbs = document.querySelectorAll('input[type=\"checkbox\"]'); for(let cb of cbs) { if(cb.parentElement.innerText.match(/Lembrar/i) || cb.id.indexOf('lembr') > -1) { cb.checked = true; } } }")
                    except:
                        pass
            
            # Aguarda o login manual do usuário ou a conclusão do automático
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
