"""
Importação do TXT de ofertas no SIGA (Importação Extrato, TES05601/TES05602).

A tela fica no front novo do SIGA, carregado num iframe de outro domínio
(siga-front.congregacao.org.br): todo o acesso é feito com frame_locator, e os
seletores são por texto e rótulo porque os IDs internos não são conhecidos.
"""

import logging
import os
import re
import time
from datetime import datetime

from caminhos import diretorio_base
from controllers.exportador import Exportador

SELETOR_IFRAME = 'iframe[src*="siga-front"]'
MAX_PAGINAS_GRADE = 50  # trava contra laço infinito no paginador
URL_IMPORTACAO_EXTRATO ="https://siga.congregacao.org.br/SIS/Programa.aspx?programa=TES05601&f_inicio=S"


class OfertasMixin:
    """Gera o TXT de ofertas de uma conta, importa na TES05602 e audita a grade."""

    def importar_ofertas_siga(self, page, dados):
        """
        Importa as ofertas de um extrato de conta corrente no SIGA.

        Args:
            page: Página do Playwright no SIGA, já na localidade e competência certas.
            dados (dict): Extrato processado (transacoes, conta_id, conta_siga_corrente).

        Returns:
            str: "importado", "duplicado", "vazio", "sem_conta" (conta fora do Banco da TES05602) ou "falha".
        """
        conta_siga = str(dados.get("conta_siga_corrente", "")).strip()
        ofertas, _ = Exportador.filtrar_ofertas(dados.get("transacoes", []))
        total, data_importacao, competencia = Exportador.resumo_ofertas(ofertas)
        if not ofertas or not data_importacao:
            self.update_status(f"Conta {dados.get('conta_id', '')}: nenhuma oferta para importar.", "#F89406")
            return "vazio"

        caminho_txt = self._gravar_txt_ofertas(dados, competencia)
        valor_fmt = Exportador.formatar_moeda(total)
        self.update_status(f"Importando ofertas da conta {conta_siga} ({valor_fmt}, {data_importacao})...", "#428BCA")

        frame = self._abrir_importacao_extrato(page)

        linhas_antes = self._ler_grade_importacoes(frame)
        if any(data_importacao in l and valor_fmt in l for l in linhas_antes):
            self.update_status(f"⚠️ Ofertas de {data_importacao} ({valor_fmt}) já importadas na conta {conta_siga}. Pulando.", "#F89406")
            return "duplicado"

        try:
            frame.locator('button:has-text("Novo"):visible, a:has-text("Novo"):visible').first.click()
            frame.get_by_text("Importar Extrato").first.wait_for(state="visible", timeout=15000)
            time.sleep(1)
            # Modal do ng-bootstrap (evita o select "Mostrar N" da grade)
            modal = frame.locator("ngb-modal-window").last

            self._preencher_data_importacao(modal, data_importacao)
            if not self._selecionar_banco(frame, modal, conta_siga):
                # O SIGA só aceita importação nas contas listadas no Banco (ex: a de manutenção fica fora)
                self.update_status(f"⏭️ Conta {conta_siga} não recebe importação de ofertas no SIGA. Pulando.", "#F89406")
                self._fechar_modal_importacao(modal)
                return "sem_conta"

            modal.locator('input[type="file"]').first.set_input_files(caminho_txt)
            time.sleep(2)

            # Com o anexo, a prévia das ofertas deixa o modal mais alto que a tela e o Playwright
            # não consegue rolar o iframe até o rodapé ("outside of the viewport"): clique pelo DOM
            salvar = modal.get_by_role("button", name=re.compile("Salvar e Fechar"))
            salvar.wait_for(state="attached", timeout=10000)
            salvar.evaluate("b => b.click()")
            frame.get_by_text("Importar Extrato").first.wait_for(state="hidden", timeout=60000)
        except Exception as e:
            logging.error(f"Falha ao importar ofertas da conta {conta_siga}: {e}", exc_info=True)
            self._capturar_tela_e_log(page, f"ofertas_{conta_siga}")
            self.update_status(f"❌ Falha ao importar ofertas da conta {conta_siga}: {str(e)[:60]}", "#D9534F")
            return "falha"

        # Auditoria: a grade precisa ganhar uma linha com o valor total do arquivo
        time.sleep(3)
        linhas_depois = self._ler_grade_importacoes(frame)
        if len(linhas_depois) > len(linhas_antes) and any(valor_fmt in l for l in linhas_depois):
            self.update_status(f"✅ Ofertas da conta {conta_siga} importadas e conferidas ({valor_fmt}).", "#3C763D")
            return "importado"

        self.update_status(f"⚠️ Ofertas da conta {conta_siga} enviadas, mas não apareceram na grade. Confira no SIGA.", "#D9534F")
        self._capturar_tela_e_log(page, f"ofertas_auditoria_{conta_siga}")
        return "falha"

    def _gravar_txt_ofertas(self, dados, competencia):
        """Grava o TXT da conta em `ofertas_importadas/` ao lado do executável e retorna o caminho."""
        pasta = os.path.join(diretorio_base(), "ofertas_importadas")
        os.makedirs(pasta, exist_ok=True)
        conta = re.sub(r"[^\w-]", "", str(dados.get("conta_id", "conta")))
        mes, ano = competencia.split("/")
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = os.path.join(pasta, f"OFERTAS_{conta}_{ano}{mes}_{carimbo}.txt")
        Exportador.gerar_txt_ofertas(dados.get("transacoes", []), caminho)
        return caminho

    def _abrir_importacao_extrato(self, page):
        """Abre a TES05601 pelo link do menu e devolve o frame_locator do front novo."""
        # O campo Executar carrega /TES/TES05601.aspx, que dá 404 (a rotina do front novo só
        # existe em Programa.aspx) e deixa a Área de Trabalho na tela: abre pelo link do menu.
        self.esperar_loading(page)
        page.goto(URL_IMPORTACAO_EXTRATO)
        page.wait_for_load_state("domcontentloaded")
        self.esperar_loading(page)
        frame = page.frame_locator(SELETOR_IFRAME)
        frame.locator('button:has-text("Novo"):visible, a:has-text("Novo"):visible').first.wait_for(state="visible", timeout=30000)
        time.sleep(2)
        return frame

    def _ler_grade_importacoes(self, frame):
        """Retorna o texto de cada linha da grade de importações (Número, Data, Arquivo, Valor), em todas as páginas."""
        # Grade do front novo (ngx-datatable): as linhas são datatable-body-row, não <tr>.
        # Mostra 100 por página e as importações novas ficam no fim: percorre todas as páginas.
        # Erro aqui sobe de propósito: grade vazia por falha de leitura faria importar em duplicidade.
        self._ir_para_pagina(frame, "go to first page")
        linhas = []
        for _ in range(MAX_PAGINAS_GRADE):
            linhas += [t for t in frame.locator("datatable-body-row").all_inner_texts() if t.strip()]
            if not self._ir_para_pagina(frame, "go to next page"):
                break
        return linhas

    def _ir_para_pagina(self, frame, rotulo):
        """
        Clica num botão do paginador da grade e espera a página trocar.

        Returns:
            bool: False se o botão estiver desabilitado (já está na primeira ou na última página).
        """
        item = frame.locator(f'datatable-pager li:has(a[aria-label="{rotulo}"])').first
        if not item.count() or "disabled" in (item.get_attribute("class") or ""):
            return False
        primeira = frame.locator("datatable-body-row").first.inner_text()
        item.locator("a").click()
        for _ in range(20):
            time.sleep(0.5)
            if frame.locator("datatable-body-row").first.inner_text() != primeira:
                return True
        raise RuntimeError(f"A grade de importações não trocou de página ({rotulo}).")

    def _preencher_data_importacao(self, modal, data_importacao):
        """Preenche o campo Data do modal (ngbDatepicker sem máscara: a data vai com as barras)."""
        campo = modal.locator("#dataImportacao")
        campo.fill(data_importacao)
        # Fecha o calendário, se abriu, para ele não cobrir o campo Banco. Esc não serve:
        # fecharia o modal inteiro. Clique fora (no título) fecha só o calendário.
        if modal.locator("ngb-datepicker").count():
            modal.locator(".modal-title").click()
        valor = campo.input_value()
        if valor != data_importacao:
            raise RuntimeError(f"Data da importação não aceita pelo SIGA (campo ficou '{valor}').")

    def _selecionar_banco(self, frame, modal, conta_siga):
        """
        Escolhe no campo Banco a opção que contém o código da conta (ex: "10130").

        Returns:
            bool: True se a opção foi encontrada e escolhida.
        """
        if not conta_siga:
            return False
        nativo = modal.locator('select').first
        if nativo.count() and nativo.is_visible():
            for opcao in nativo.locator("option").all():
                if conta_siga in (opcao.text_content() or ""):
                    nativo.select_option(value=opcao.get_attribute("value"))
                    return True
            return False

        # ng-select com busca: digita o código no input dele e clica na opção filtrada.
        # A lista pode ser renderizada fora do modal, então a opção é buscada no frame todo.
        busca = modal.locator('ng-select[name="codigoContaBanco"] input')
        busca.click()
        busca.fill(conta_siga)
        time.sleep(1)
        opcao = frame.locator(".ng-option").filter(has_text=conta_siga).first
        try:
            opcao.wait_for(state="visible", timeout=5000)
        except Exception:
            return False
        opcao.click()
        return True

    def contas_permitidas_ofertas(self, page):
        """
        Lê no Banco do modal Importar Extrato os códigos das contas que aceitam importação.

        Abre o modal, lê as opções do ng-select e fecha sem salvar. Serve para pular de cara
        as contas fora da lista (ex: a de manutenção), sem abrir a tela para cada uma.

        Args:
            page: Página do Playwright no SIGA, já na localidade certa.

        Returns:
            set[str] | None: Códigos (ex: {"10129", "10130"}), ou None se não deu para ler
            (aí cada conta tenta normalmente no modal).
        """
        try:
            frame = self._abrir_importacao_extrato(page)
            frame.locator('button:has-text("Novo"):visible, a:has-text("Novo"):visible').first.click()
            frame.get_by_text("Importar Extrato").first.wait_for(state="visible", timeout=15000)
            modal = frame.locator("ngb-modal-window").last
            modal.locator('ng-select[name="codigoContaBanco"] input').click()
            frame.locator(".ng-option").first.wait_for(state="visible", timeout=10000)
            # Opção no formato "10129 - SICREDI - AG: 0000 CC: 00000-0 REGIONAL"
            codigos = {m.group(1) for t in frame.locator(".ng-option").all_inner_texts()
                       if (m := re.match(r"\s*(\d+)", t))}
            self._fechar_modal_importacao(modal)
            frame.locator("ngb-modal-window").first.wait_for(state="hidden", timeout=10000)
        except Exception as e:
            logging.warning(f"[Ofertas] Não foi possível ler as contas do Banco: {e}")
            # Recarrega a tela para não deixar o modal aberto (nada foi salvo)
            try:
                page.goto(URL_IMPORTACAO_EXTRATO)
            except Exception as e_goto:
                logging.debug(f"[Ofertas] Recarga da TES05601 falhou: {e_goto}")
            return None
        logging.info(f"[Ofertas] Contas que aceitam importação: {sorted(codigos)}")
        return codigos or None

    def _fechar_modal_importacao(self, modal):
        """Fecha o modal sem salvar."""
        try:
            # Com a lista do Banco aberta, o primeiro clique só fecha a lista: fecha ela antes
            modal.locator(".modal-title").click()
            # exact=True: sem ele "Fechar" também casa com "Salvar e Fechar", que vem antes no DOM
            modal.get_by_role("button", name="Fechar", exact=True).click()
        except Exception as e:
            logging.debug(f"[Ofertas] Botão Fechar do modal não encontrado: {e}")
