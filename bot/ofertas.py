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


class OfertasMixin:
    """Gera o TXT de ofertas de uma conta, importa na TES05602 e audita a grade."""

    def importar_ofertas_siga(self, page, dados):
        """
        Importa as ofertas de um extrato de conta corrente no SIGA.

        Args:
            page: Página do Playwright no SIGA, já na localidade e competência certas.
            dados (dict): Extrato processado (transacoes, conta_id, conta_siga_corrente).

        Returns:
            str: "importado", "duplicado", "vazio" ou "falha".
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
            # Menor bloco que contém o título e o anexo: o modal (evita o select "Mostrar N" da grade)
            modal = frame.locator("div").filter(has=frame.get_by_text("Importar Extrato")).filter(
                has=frame.locator('input[type="file"]')).last

            self._preencher_data_importacao(modal, data_importacao)
            if not self._selecionar_banco(frame, modal, conta_siga):
                self.update_status(f"⚠️ Banco '{conta_siga}' não encontrado no modal Importar Extrato.", "#D9534F")
                self._capturar_tela_e_log(page, f"ofertas_banco_{conta_siga}")
                self._fechar_modal_importacao(modal)
                return "falha"

            modal.locator('input[type="file"]').first.set_input_files(caminho_txt)
            time.sleep(2)

            modal.get_by_role("button", name=re.compile("Salvar e Fechar")).click()
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
        """Abre a TES05601 pelo campo Executar e devolve o frame_locator do front novo."""
        page.locator('#f_executar_programa').fill("TES05601")
        page.evaluate("document.querySelectorAll('.notificacao').forEach(e => e.remove());")
        page.locator('#btn_executar_programa').click(force=True)
        page.wait_for_load_state("domcontentloaded")
        frame = page.frame_locator(SELETOR_IFRAME)
        frame.locator('button:has-text("Novo"):visible, a:has-text("Novo"):visible').first.wait_for(state="visible", timeout=30000)
        time.sleep(2)
        return frame

    def _ler_grade_importacoes(self, frame):
        """Retorna o texto de cada linha da grade de importações (Número, Data, Arquivo, Valor)."""
        try:
            return [t for t in frame.locator("table tbody tr").all_inner_texts() if t.strip()]
        except Exception as e:
            logging.warning(f"Não foi possível ler a grade de importações: {e}")
            return []

    def _preencher_data_importacao(self, modal, data_importacao):
        """Preenche o campo Data do modal, aceitando input de texto com máscara ou type=date."""
        campo = modal.locator('input[placeholder*="dd/mm"], input[type="date"]').first
        if campo.get_attribute("type") == "date":
            dia, mes, ano = data_importacao.split("/")
            campo.fill(f"{ano}-{mes}-{dia}")
        else:
            campo.click()
            campo.fill("")
            campo.press_sequentially(data_importacao.replace("/", ""), delay=50)
        campo.press("Tab")

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

        # Componente de busca (dropdown customizado): abre, filtra e clica na opção.
        # A lista pode ser renderizada fora do modal, então a opção é buscada no frame todo.
        modal.get_by_text("Selecione...").first.click()
        time.sleep(1)
        busca = frame.locator('input[type="text"]:focus, input[role="combobox"]').first
        if busca.count():
            busca.fill(conta_siga)
            time.sleep(1)
        opcao = frame.get_by_text(re.compile(rf"^\s*{re.escape(conta_siga)}\b")).first
        try:
            opcao.wait_for(state="visible", timeout=5000)
        except Exception:
            return False
        opcao.click()
        return True

    def _fechar_modal_importacao(self, modal):
        """Fecha o modal sem salvar."""
        try:
            modal.get_by_role("button", name="Fechar").first.click()
        except Exception:
            pass
