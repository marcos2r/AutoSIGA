"""
Descoberta das contas bancárias no SIGA (tipo_lote="descoberta"), somente leitura.

Tenta o Plano de Contas da Contabilidade (CTB00301), que traz todas as contas com a
localidade dona numa página só. Se o usuário não tiver acesso, percorre a Caixas e
Bancos (TES01701) em cada localidade ADM, DR e PIA e, no fim, volta sempre ao contexto
em que o usuário estava, sem "lembrar a escolha". Nada é gravado no SIGA.
"""

import logging
import time

from controllers.catalogo_contas import (
    TIPOS_LOCALIDADE,
    Catalogo,
    consolidar,
    ler_grade_plano_contas,
    ler_rotulo_tesouraria,
    mesma_localidade,
    separar_localidade,
)

URL_SIGA = "https://siga.congregacao.org.br"

_JS_FILTRAR_GRADE = '''() => {
    var t = jQuery('#grid1').dataTable();
    t.fnSettings()._iDisplayLength = 1000;
    t.fnFilter('CC:');
    return true;
}'''

_JS_ESTADO_GRADE = '''() => {
    var s = jQuery('#grid1').dataTable().fnSettings();
    return {
        processando: jQuery('#grid1_processing').is(':visible'),
        linhas: document.querySelectorAll('#grid1 tbody tr').length,
        total: s.fnRecordsDisplay()
    };
}'''

_JS_LER_GRADE = '''() => ({
    cabecalho: Array.from(document.querySelectorAll('#grid1 thead th')).map(th => th.innerText.trim()),
    linhas: Array.from(document.querySelectorAll('#grid1 tbody tr')).map(
        tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))
})'''

_JS_LER_CONTAS_TES = '''() => Array.from(document.querySelectorAll('select#f_conta option')).map(o => ({
    texto: o.textContent.trim(),
    inativa: !!(o.parentElement && o.parentElement.tagName === 'OPTGROUP'
                && o.parentElement.label.toUpperCase().indexOf('INATIV') > -1)
}))'''

_JS_LER_LOCALIDADES = '''() => Array.from(document.querySelectorAll('select[name="f_estabelecimento"] option'))
    .map(o => o.textContent.trim())'''


class DescobertaContasMixin:
    """Lê o catálogo de contas do SIGA e o entrega à UI pelo callback `on_catalogo`."""

    def _fluxo_descoberta(self, page):
        """Monta o catálogo (CTB00301 ou TES01701) e chama `on_catalogo(catalogo)`.

        Returns:
            Catalogo | None: O catálogo lido, ou None se nada pôde ser lido.
        """
        catalogo = self._ler_plano_contas(page)
        if catalogo is None:
            catalogo = self._ler_contas_tesouraria(page)

        if catalogo is None or catalogo.vazio:
            self.update_status("❌ Não foi possível ler as contas do SIGA. Veja o log e tente de novo.", "#D9534F")
            return None

        resumo = f"✅ {len(catalogo.contas)} contas lidas do SIGA ({catalogo.fonte})."
        if catalogo.localidades_sem_acesso:
            resumo += f" Sem acesso a: {', '.join(catalogo.localidades_sem_acesso)}."
        self.update_status(resumo, "#3C763D")
        logging.info(f"Descoberta de contas: {len(catalogo.contas)} contas via {catalogo.fonte}; "
                     f"sem acesso: {catalogo.localidades_sem_acesso}")
        if "on_catalogo" in self.callbacks:
            self.callbacks["on_catalogo"](catalogo)
        return catalogo

    def _esperar(self, condicao, tentativas=60, intervalo=0.5):
        """Repete `condicao()` até ela ser verdadeira (espera por condição, não por tempo fixo)."""
        for _ in range(tentativas):
            try:
                if condicao():
                    return True
            except Exception as e:
                logging.debug(f"Condição ainda não satisfeita: {e}")
            time.sleep(intervalo)
        return False

    def _ler_plano_contas(self, page):
        """Lê as contas bancárias da CTB00301 com a busca `CC:`.

        Returns:
            Catalogo | None: None quando o usuário não tem acesso ou a grade não abriu.
        """
        self.update_status("Verificando acesso ao Plano de Contas (Contabilidade)...", "#428BCA")
        try:
            page.goto(f"{URL_SIGA}/CTB/CTB00301.aspx")
            page.wait_for_load_state("domcontentloaded")
            # Sem acesso, o SIGA redireciona para outra tela
            if "CTB00301" not in (page.url or "").upper():
                logging.info("Sem acesso ao Plano de Contas (CTB00301): redirecionado.")
                return None
            page.locator('#grid1').wait_for(state="attached", timeout=15000)
            self.esperar_loading(page)

            page.evaluate(_JS_FILTRAR_GRADE)
            anterior = {}

            def grade_estavel():
                nonlocal anterior
                estado = page.evaluate(_JS_ESTADO_GRADE)
                estavel = (not estado["processando"] and estado == anterior
                           and estado["linhas"] >= min(estado["total"], 1000))
                anterior = estado
                return estavel

            if not self._esperar(grade_estavel):
                logging.warning("A grade do Plano de Contas não estabilizou a tempo.")
                return None

            grade = page.evaluate(_JS_LER_GRADE)
            contas = ler_grade_plano_contas(grade.get("cabecalho", []), grade.get("linhas", []))
        except Exception as e:
            logging.info(f"Plano de Contas indisponível, usando a Tesouraria: {e}")
            return None

        if not contas:
            logging.info("Plano de Contas sem contas bancárias legíveis, usando a Tesouraria.")
            return None
        return Catalogo(contas=contas, fonte="CTB00301")

    def _ler_contexto(self, page):
        """Localidade e Mês de Trabalho ativos, lidos do cabeçalho do SIGA.

        Returns:
            tuple[str, str] | None: ("ADM - DOURADOS - MS", "10/2026"), ou None se não leu.
        """
        try:
            texto = page.locator('li.green span.user-info').first.text_content() or ""
            competencia = (page.locator('span#f_competencianome').first.text_content() or "").strip()
        except Exception as e:
            logging.warning(f"Não foi possível ler o contexto ativo do SIGA: {e}")
            return None
        # O chip mostra o nome do usuário/cidade numa linha e "TIPO - NOME" na outra
        linhas = [" ".join(l.split()).upper() for l in texto.splitlines() if " - " in l]
        if not linhas:
            return None
        return linhas[-1], competencia

    def _localidades_disponiveis(self, page):
        """Localidades ADM, DR e PIA que o modal "Outros Meses" oferece ao usuário."""
        page.locator('#a_competencia').click()
        page.locator('a.showModal:has-text("Outros Meses")').click()
        page.locator('select[name="f_estabelecimento"]').first.wait_for(state="attached", timeout=15000)
        textos = page.evaluate(_JS_LER_LOCALIDADES) or []
        page.keyboard.press("Escape")

        localidades = []
        for texto in textos:
            tipo, nome = separar_localidade(texto)
            loc = f"{tipo} - {nome}"
            if tipo in TIPOS_LOCALIDADE and nome and loc not in localidades:
                localidades.append(loc)
        return localidades

    def _contas_da_tesouraria_atual(self, page, localidade):
        """Lê o `select#f_conta` da TES01701 na localidade ativa."""
        page.goto(f"{URL_SIGA}/TES/TES01701.aspx")
        page.wait_for_load_state("domcontentloaded")
        page.locator('select#f_conta').first.wait_for(state="attached", timeout=20000)
        opcoes = page.evaluate(_JS_LER_CONTAS_TES) or []
        contas = [ler_rotulo_tesouraria(o.get("texto", ""), localidade, bool(o.get("inativa")))
                  for o in opcoes]
        return [c for c in contas if c]

    def _ler_contas_tesouraria(self, page):
        """Percorre a TES01701 em cada localidade e restaura o contexto original no fim.

        Returns:
            Catalogo | None: None se o contexto atual não pôde ser lido (não é seguro trocar).
        """
        self.update_status("Sem acesso ao Plano de Contas. Lendo as contas pela Tesouraria...", "#428BCA")
        contexto = self._ler_contexto(page)
        if contexto is None:
            self._capturar_tela_e_log(page, "descoberta_contexto")
            self.update_status("❌ Não foi possível ler a localidade atual do SIGA.", "#D9534F")
            return None
        local_original, mes_original = contexto

        contas, sem_acesso = [], []
        trocou = False
        try:
            localidades = self._localidades_disponiveis(page)
            if (not any(mesma_localidade(l, local_original) for l in localidades)
                    and separar_localidade(local_original)[0] in TIPOS_LOCALIDADE):
                localidades.insert(0, local_original)

            for idx, loc in enumerate(localidades):
                if not self.browser_aberto:
                    break
                self.update_status(f"Lendo contas de {loc} ({idx + 1}/{len(localidades)})...", "#428BCA")
                if trocou or not mesma_localidade(loc, local_original):
                    tipo, nome = separar_localidade(loc)
                    trocou = True
                    if not self._ajustar_localidade_competencia(page, tipo, nome, ""):
                        sem_acesso.append(loc)
                        continue
                try:
                    lidas = self._contas_da_tesouraria_atual(page, loc)
                except Exception as e:
                    logging.warning(f"Contas de {loc} não puderam ser lidas: {e}")
                    lidas = []
                if not lidas:
                    sem_acesso.append(loc)
                contas.extend(lidas)
                if "update_progress" in self.callbacks:
                    self.callbacks["update_progress"]((idx + 1) / len(localidades))
        except Exception as e:
            logging.error(f"Falha ao percorrer as localidades na descoberta: {e}", exc_info=True)
            self._capturar_tela_e_log(page, "descoberta_tesouraria")
        finally:
            if trocou:
                self._restaurar_contexto(page, local_original, mes_original)

        return Catalogo(contas=consolidar(contas), fonte="TES01701", localidades_sem_acesso=sem_acesso)

    def _restaurar_contexto(self, page, localidade, competencia):
        """Volta à localidade e ao mês em que o usuário estava antes da descoberta."""
        tipo, nome = separar_localidade(localidade)
        try:
            ok = self._ajustar_localidade_competencia(page, tipo, nome, competencia)
        except Exception as e:
            logging.error(f"Erro ao restaurar o contexto do SIGA: {e}", exc_info=True)
            ok = False
        if not ok:
            self.update_status(f"⚠️ Não consegui voltar para {localidade} ({competencia}). "
                               "Troque a localidade manualmente no SIGA.", "#D9534F")
