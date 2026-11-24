"""
Lançamento das tarifas do extrato como despesa em Caixas e Bancos (TES01702), Fase 2.

Quem decide o que lançar é `controllers/tarifas.py`; aqui só se preenche a tela. Os campos
foram levantados em 23/11/2026 (docs/regras/siga.md). Depois de gravar, a grade da
TES01701 é relida e a prova real roda de novo, para a tarifa casar com a linha do extrato.
"""

import logging
import time

from bot.extratos import MesFechadoError
from controllers.tarifas import RegraTarifa, cidade_da_localidade, escolher_fornecedor, planejar, termos_do_banco

_JS_DATA = '''([campo, data]) => {
    const inp = document.getElementById(campo);
    if (!inp) return;
    inp.value = data;
    if (window.jQuery) {
        window.jQuery(inp).datepicker('update', data);
        window.jQuery(inp).trigger('change');
        window.jQuery('.datepicker').hide();
    } else {
        inp.dispatchEvent(new Event('change', {bubbles: true}));
    }
}'''

_JS_VALOR = '''([campo, valor]) => {
    const el = document.getElementById(campo);
    if (el && window.jQuery) {
        window.jQuery(el).autoNumeric("set", valor);
        window.jQuery(el).trigger("change");
        window.jQuery(el).trigger("blur");
    }
}'''


class TarifasMixin:
    """Grava as tarifas que a prova real apontou como faltando no SIGA."""

    def _lancar_tarifas(self, page, dados, conta_alvo, faltas, consulta, telemetria_lote):
        """Planeja, pede a prévia (se ligada), grava e relê a grade.

        Returns:
            bool: True se gravou alguma tarifa e a grade na tela é a relida (a prova real deve
            rodar de novo); False se não havia o que lançar ou nada foi gravado.
        """
        regra = getattr(self, "regra_tarifas", None) or RegraTarifa.da_config(None)
        plano = planejar(faltas, regra)
        if not plano:
            return False
        previa = [{"data": lc.data, "valor": -lc.valor, "descricao": f"TARIFA - {lc.descricao}"} for lc in plano]
        if not self._pedir_autorizacao(previa, conta_alvo, tipo="tarifas"):
            self.update_status(f"⏭️ {len(plano)} tarifa(s) não autorizada(s) ficaram pendentes.", "#F89406")
            return False

        termos = termos_do_banco(dados.get("banco"), dict(regra.fornecedores))
        if not termos:
            self.update_status(f"⏭️ Banco {dados.get('banco') or '?'} sem fornecedor conhecido: "
                               f"{len(plano)} tarifa(s) ficaram pendentes.", "#F89406")
            return False
        fornecedor = (termos, cidade_da_localidade(dados.get("nome_adm")))
        gravadas = self.inserir_tarifas_siga(page, plano, conta_alvo, regra, fornecedor)
        telemetria_lote["injecoes"] += gravadas
        if not gravadas:
            return False
        try:
            extrato = self._abrir_consulta_tes01701(page, *consulta)
        except Exception as e:
            logging.error(f"Releitura da TES01701 depois das tarifas falhou: {e}")
            return False
        if extrato is None:
            return False
        dados["extrato_siga"] = extrato
        return True

    def inserir_tarifas_siga(self, page, plano, conta_alvo, regra, fornecedor=(("SICREDI",), ""), simular=False):
        """Preenche e grava uma despesa por tarifa na TES01702 ("Salvar e Novo" entre elas).

        Com `simular=True` preenche a primeira e para antes de salvar (conferência na tela real).

        Returns:
            int: Quantas foram gravadas antes de terminar ou de uma falha.
        """
        gravadas = 0
        try:
            for i, lc in enumerate(sorted(plano, key=lambda x: tuple(reversed(x.data.split("/"))))):
                if not self.browser_aberto:
                    break
                self._verificar_sessao_ativa(page)
                self.update_status(f"Lançando tarifa {i + 1}/{len(plano)}: R$ {lc.valor:.2f} ({lc.data})", "#F89406")
                if i == 0:
                    page.locator('#f_executar_programa').fill("TES01702")
                    page.locator('#btn_executar_programa').click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                else:
                    time.sleep(1.5)  # o "Salvar e Novo" já devolve o formulário limpo

                # Documento
                page.evaluate(_JS_DATA, ["f_data", lc.data])
                time.sleep(1)
                self._tratar_competencia(page, lc.data)
                self.selecionar_select2(page, "f_tipodocumento", regra.tipo_documento, dropdown_is_ajax=False)
                self._preencher_campos(page, {"f_documento": lc.documento})
                page.evaluate(_JS_VALOR, ["f_valor", lc.valor])
                time.sleep(0.5)

                # Rateio: uma linha, 100% na despesa bancária da ADM
                self.selecionar_select2(page, "f_despesa_rateio", regra.despesa, dropdown_is_ajax=False)
                self.selecionar_select2(page, "f_centrocusto_rateio", regra.centro_custo, dropdown_is_ajax=False)
                if not (page.locator('#f_valorRateio').input_value() or "").strip():
                    page.evaluate(_JS_VALOR, ["f_percentualRateio", 100])
                self.selecionar_select2(page, "f_historico_debito", regra.historico, dropdown_is_ajax=False)
                # Fornecedor obrigatório: o próprio banco da conta, pesquisado no cadastro do SIGA
                self._escolher_fornecedor(page, *fornecedor)
                complemento = f"TARIFA - {self.sanitizar_descricao(lc.descricao)}"
                self._preencher_campos(page, {"f_complemento2": complemento})

                # Pagamento: débito automático na conta corrente do extrato
                page.evaluate(_JS_DATA, ["f_datapagamento", lc.data])
                time.sleep(0.5)
                self.selecionar_select2(page, "f_formapagamento", regra.forma_pagamento, dropdown_is_ajax=False)
                self._preencher_campos(page, {"f_documento2": lc.documento})
                self._escolher_conta_movimentacao(page, "f_conta", conta_alvo)
                self.selecionar_select2(page, "f_historico", regra.historico, dropdown_is_ajax=True)
                self._preencher_campos(page, {"f_complemento": complemento})
                time.sleep(1)
                # As datas às vezes voltam vazias depois dos Select2 (visto em 23/11/2026): confere e repõe
                self._garantir_datas(page, lc.data)
                if simular:
                    return 0

                ultimo = i == len(plano) - 1
                botao = page.locator(f'button.btn-salvar[data-comando="{"F" if ultimo else "N"}"]')
                if botao.count() > 0:
                    botao.first.click()
                else:
                    page.locator('button.btn-success:has(i.icon-ok)').first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                if self._mes_fechado_na_tela(page):
                    raise MesFechadoError(lc.data)
                self._recusar_se_invalido(page)
                self._confirmar_gravacao(page, timeout_ms=25000)
                gravadas += 1
            if gravadas:
                self.update_status(f"✅ {gravadas} tarifa(s) lançada(s) como despesa no SIGA.", "#3C763D")
        except MesFechadoError:
            raise  # o laço do lote pula os outros extratos da mesma localidade e mês
        except Exception as e:
            logging.error(f"Erro lançando tarifas: {e}", exc_info=True)
            self._capturar_tela_e_log(page, "erro_inserir_tarifas")
            self.update_status(f"Falha ao lançar tarifa: {e}", "#D9534F")
        return gravadas

    def _escolher_fornecedor(self, page, termos, cidade):
        """Pesquisa o banco no Select2 de fornecedor (AJAX, busca com Enter) e escolhe o resultado.

        Tenta cada termo (ex.: "SICREDI"); entre os resultados, prefere o da cidade da
        administração (o cadastro da cooperativa local), como `escolher_fornecedor` decide.

        Raises:
            RuntimeError: nenhum termo trouxe um fornecedor do banco.
        """
        for termo in termos:
            self._esperar_sem_overlay(page)
            page.evaluate("() => window.jQuery && window.jQuery('#f_fornecedor').select2('open')")
            busca = page.locator('#select2-drop:visible .select2-input')
            busca.wait_for(state="visible", timeout=5000)
            busca.fill("")
            busca.type(termo, delay=50)
            busca.press("Enter")
            resultados = page.locator('#select2-drop:visible .select2-result-selectable')
            try:
                resultados.first.wait_for(state="visible", timeout=8000)
            except Exception:
                page.keyboard.press("Escape")
                continue
            textos = resultados.all_inner_texts()
            escolhido = escolher_fornecedor(textos, termo, cidade)
            if escolhido is None:
                page.keyboard.press("Escape")
                continue
            resultados.nth(escolhido).click()
            time.sleep(0.5)
            # O Select2 de fornecedor ficava aberto depois do clique e o próximo campo digitava na
            # busca dele (teste de 23/11/2026): fecha e confere antes de seguir
            page.evaluate("() => window.jQuery && window.jQuery('#f_fornecedor').select2('close')")
            if page.locator('#select2-drop:visible').count() > 0:
                page.keyboard.press("Escape")
            time.sleep(0.3)
            logging.info(f"Fornecedor da tarifa: {' '.join(textos[escolhido].split())[:80]}")
            return
        raise RuntimeError(f"fornecedor do banco não encontrado no SIGA (buscou: {', '.join(termos)})")

    def _garantir_datas(self, page, data):
        """Repõe Data Documento e Data Pagamento se algum Select2 as limpou."""
        for campo in ("f_data", "f_datapagamento"):
            try:
                if (page.locator(f"#{campo}").input_value() or "").strip() != data:
                    logging.info(f"{campo} estava vazio ou diferente; repondo {data}.")
                    page.evaluate(_JS_DATA, [campo, data])
                    time.sleep(0.5)
                    self._tratar_competencia(page, data)
            except MesFechadoError:
                raise
            except Exception as e:
                logging.warning(f"Não foi possível conferir {campo}: {e}")

    def _recusar_se_invalido(self, page):
        """Para se o SIGA recusou a gravação ("Formulário Incompleto", campo obrigatório).

        Sem isso, a modal de erro era fechada como se fosse a de sucesso e o robô contava a
        tarifa como gravada (teste de 23/11/2026, faltava o fornecedor).

        Raises:
            RuntimeError: com o texto da mensagem do SIGA.
        """
        try:
            texto = page.evaluate("""() => Array.from(document.querySelectorAll('.modal.in, .bootbox'))
                .filter(m => m.offsetParent !== null).map(m => m.innerText).join(' | ')""") or ""
        except Exception:
            return
        if any(p in texto.upper() for p in ("INCOMPLETO", "OBRIGAT", "PREENCHA", "INVÁLID", "INVALID")):
            self._capturar_tela_e_log(page, "gravacao_recusada")
            raise RuntimeError(f"o SIGA recusou a gravação: {' '.join(texto.split())[:200]}")

    def _tratar_competencia(self, page, data):
        """Responde "Sim" ao pop-up de competência e para se o mês estiver fechado (como no rendimento)."""
        if self._mes_fechado_na_tela(page):
            raise MesFechadoError(data)
        try:
            botao = page.locator('.bootbox button:has-text("Sim")').first
            botao.wait_for(state="visible", timeout=2000)
            botao.click()
            time.sleep(0.5)
        except Exception as e:
            logging.debug(f"Pop-up de competência não apareceu: {e}")
        if self._mes_fechado_na_tela(page):
            raise MesFechadoError(data)
