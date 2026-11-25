"""
Remessas entre administrações (Transf. Numerários, TES01301), Fase 3: confirmar recebimentos.

Quem decide é `controllers/remessas.py`. Aqui se lê a aba Recebimentos da TES01301 e,
para cada crédito do extrato que casa com um "Pendente Recebimento" (mesmo valor e data
perto da emissão), abre a TES01313 (Confirmar Recebimento), preenche a data do extrato,
o documento e a conta, e confirma. Tela levantada em 24/11/2026 (docs/regras/siga.md).
O lançamento das remessas enviadas fica para depois (falta o cadastro dos destinos).
"""

import logging
import time

from bot.extratos import MesFechadoError
from controllers.matriz_extrato import projetar
from controllers.prova_real import valor_br
from controllers.remessas import RECEBIDA, RecebimentoPendente, cnpjs_da_linha, parear_recebimentos, reconhecer

_JS_PENDENTES = r"""() => Array.from(document.querySelectorAll('a[href*="TES01313.aspx?codigo="]')).map(a => {
    const tr = a.closest('tr');
    const tds = tr ? Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()) : [];
    return {codigo: a.getAttribute('href').split('codigo=')[1], tds};
})"""

_JS_DATA = '''(data) => {
    const inp = document.getElementById("f_recebimento");
    if (!inp) return;
    inp.value = data;
    if (window.jQuery) {
        window.jQuery(inp).datepicker('update', data);
        window.jQuery(inp).trigger('change');
        window.jQuery('.datepicker').hide();
    }
}'''

# Escolhe a conta de recebimento pelo código (o remetente já sugere uma; vale a do extrato)
_JS_CONTA = r"""(codigo) => {
    const sel = document.getElementById('f_conta');
    if (!sel) return 'sem campo';
    const opt = Array.from(sel.options).find(o => o.text.trim().startsWith(codigo + ' '));
    if (!opt) return 'sem opção';
    if (sel.value !== opt.value) {
        sel.value = opt.value;
        if (window.jQuery) window.jQuery(sel).trigger('change');
    }
    return 'ok';
}"""


class RemessasMixin:
    """Confirma no SIGA os recebimentos de outras administrações que já caíram no banco."""

    def _preparar_remessas(self):
        """Reconhece as remessas do lote (uma vez). O CNPJ próprio vem das transferências internas."""
        proprios = {c for t in getattr(self, "_pares_transf", []) for c in cnpjs_da_linha(t.descricao)}
        try:
            self._remessas = reconhecer(self.lote_processados, proprios)
        except Exception as e:
            logging.error(f"Reconhecimento das remessas falhou: {e}", exc_info=True)
            self._remessas = []
        recebidas = [r for r in self._remessas if r.sentido == RECEBIDA]
        contas = sorted({r.conta_siga for r in recebidas})
        logging.info(f"{len(recebidas)} recebimento(s) de outras administrações no lote"
                     + (f" (contas {', '.join(contas)})" if contas else "") + ".")

    def _ler_recebimentos_pendentes(self, page):
        """Abre a TES01301 e lê as linhas "Pendente Recebimento" da aba Recebimentos."""
        page.goto("https://siga.congregacao.org.br/TES/TES01301.aspx")
        page.wait_for_load_state("domcontentloaded")
        self.esperar_loading(page)
        pendentes = []
        for linha in page.evaluate(_JS_PENDENTES) or []:
            tds = linha.get("tds") or []
            # Dt. Emissão; Dt. Recebim.; Remetente; Tipo; Complemento; Valor; Status; Opções
            if len(tds) < 7 or "PENDENTE" not in tds[6].upper():
                continue
            valor = valor_br(tds[5])
            if valor is None:
                continue
            pendentes.append(RecebimentoPendente(linha["codigo"], tds[0], valor, tds[2], tds[4]))
        return pendentes

    def _confirmar_recebimentos(self, page, dados, conta_alvo, telemetria_lote):
        """Confirma os recebimentos desta conta e os acrescenta à matriz do extrato.

        A grade não é relida aqui: a conferência final do extrato confere tudo de uma vez.

        Returns:
            bool: True se confirmou algum (a matriz em `dados["extrato_siga"]` já os inclui).
        """
        recebidas = [r for r in getattr(self, "_remessas", []) if r.sentido == RECEBIDA and r.conta_siga == conta_alvo]
        if not recebidas:
            return False
        try:
            pendentes = self._ler_recebimentos_pendentes(page)
        except Exception as e:
            logging.error(f"Leitura dos recebimentos pendentes falhou: {e}")
            return False
        pares = parear_recebimentos(recebidas, pendentes, conta_alvo)
        logging.info(f"Conta {conta_alvo}: {len(recebidas)} recebimento(s) no extrato, {len(pendentes)} pendente(s) "
                     f"no SIGA, {len(pares)} casado(s).")
        if not pares:
            return False
        previa = [{"data": r.data, "valor": r.valor,
                   "descricao": f"RECEBIMENTO de {p.remetente} ({p.complemento or 'remessa'})"} for r, p in pares]
        if not self._pedir_autorizacao(previa, conta_alvo, tipo="recebimentos"):
            self.update_status(f"⏭️ {len(pares)} recebimento(s) não autorizado(s) ficaram pendentes.", "#F89406")
            return False

        confirmados = []
        for i, (r, p) in enumerate(pares):
            if not self.browser_aberto:
                break
            self.update_status(f"Confirmando recebimento {i + 1}/{len(pares)}: {p.remetente}, "
                               f"R$ {r.valor:.2f} ({r.data})", "#F89406")
            try:
                page.goto(f"https://siga.congregacao.org.br/TES/TES01313.aspx?codigo={p.codigo}")
                page.wait_for_load_state("domcontentloaded")
                self.esperar_loading(page)
                page.evaluate(_JS_DATA, r.data)
                time.sleep(0.8)
                self._tratar_competencia(page, r.data)
                self._preencher_campos(page, {"f_documento": r.codigo or r.data.replace("/", "")})
                resultado = page.evaluate(_JS_CONTA, conta_alvo)
                if resultado != "ok":
                    raise RuntimeError(f"conta {conta_alvo} não disponível no recebimento ({resultado})")
                time.sleep(0.5)
                page.locator('#mainContent button[type=submit].btn-success').filter(has_text="Confirmar").first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                if self._mes_fechado_na_tela(page):
                    raise MesFechadoError(r.data)
                self._recusar_se_invalido(page)
                self._confirmar_gravacao(page, timeout_ms=25000)
                confirmados.append((r.data, r.valor, f"RECEBIMENTO de {p.remetente}"))
            except MesFechadoError:
                raise
            except Exception as e:
                logging.error(f"Erro confirmando o recebimento {p.codigo}: {e}", exc_info=True)
                self._capturar_tela_e_log(page, "erro_confirmar_recebimento")
                self.update_status(f"Falha ao confirmar o recebimento de {p.remetente}: {e}", "#D9534F")
        telemetria_lote["injecoes"] += len(confirmados)
        if not confirmados:
            return False
        self.update_status(f"✅ {len(confirmados)} recebimento(s) de outras administrações confirmado(s).", "#3C763D")
        dados["extrato_siga"] = projetar(dados.get("extrato_siga"), confirmados)
        return True
