"""
Transferências entre contas da mesma localidade como Movimentação Interna (TES01704).

Quem decide é `controllers/transferencias_internas.py` (pareia as pontas pelo código SI do
extrato). Aqui só se preenche a tela, que já é usada para aplicação e resgate (bot/extratos.py).
Cada transferência é gravada pela conta de origem; depois a grade é relida e a prova real
roda de novo.
"""

import logging
import time

from bot.extratos import MesFechadoError
from controllers.prova_real import moeda
from controllers.transferencias_internas import parear

# Histórico da transferência: o destino da TES01704 já vem bloqueado em "032 - TRANSFER..."
HISTORICO_TRANSFERENCIA = "032"


class TransferenciasInternasMixin:
    """Lança as transferências entre contas correntes do mesmo departamento."""

    def _preparar_transferencias(self):
        """Pareia as transferências do lote inteiro (uma vez, no começo do lote de extratos)."""
        try:
            self._pares_transf, self._soltas_transf = parear(self.lote_processados)
        except Exception as e:
            logging.error(f"Pareamento das transferências entre contas falhou: {e}", exc_info=True)
            self._pares_transf, self._soltas_transf = [], []
        if self._pares_transf:
            logging.info(f"{len(self._pares_transf)} transferência(s) entre contas pareada(s) no lote.")

    def avisos_transferencias(self, conta_siga):
        """Pontas soltas desta conta, como frases para o painel."""
        return [f"Transferência de {s.data} ({moeda(s.valor)}) não lançada: {s.motivo}."
                for s in getattr(self, "_soltas_transf", []) if s.conta_siga == conta_siga]

    def _lancar_transferencias(self, page, transferencias, conta_alvo, consulta, dados, telemetria_lote):
        """Pede a prévia (se ligada), grava e relê a grade da conta.

        Returns:
            bool: True se gravou e a grade na tela é a relida.
        """
        if not transferencias:
            return False
        previa = [{"data": t.data, "valor": -t.valor,
                   "descricao": f"TRANSFERÊNCIA {t.codigo}: {t.conta_origem} → {t.conta_destino}"}
                  for t in transferencias]
        if not self._pedir_autorizacao(previa, conta_alvo, tipo="transferencias"):
            self.update_status(f"⏭️ {len(transferencias)} transferência(s) não autorizada(s) ficaram pendentes.",
                               "#F89406")
            return False
        gravadas = self.inserir_transferencias_siga(page, transferencias)
        telemetria_lote["injecoes"] += gravadas
        if not gravadas:
            return False
        try:
            extrato = self._abrir_consulta_tes01701(page, *consulta)
        except Exception as e:
            logging.error(f"Releitura da TES01701 depois das transferências falhou: {e}")
            return False
        if extrato is None:
            return False
        dados["extrato_siga"] = extrato
        return True

    def inserir_transferencias_siga(self, page, transferencias):
        """Grava uma Movimentação Interna por transferência ("Salvar e Novo" entre elas).

        Returns:
            int: Quantas foram gravadas antes de terminar ou de uma falha.
        """
        gravadas = 0
        try:
            for i, t in enumerate(transferencias):
                if not self.browser_aberto:
                    break
                self._verificar_sessao_ativa(page)
                self.update_status(f"Lançando transferência {i + 1}/{len(transferencias)}: "
                                   f"{t.conta_origem} → {t.conta_destino}, R$ {t.valor:.2f} ({t.data})", "#F89406")
                if i == 0:
                    page.locator('#f_executar_programa').fill("TES01704")
                    page.locator('#btn_executar_programa').click()
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(2)
                else:
                    time.sleep(1.5)

                page.evaluate('''(data) => {
                    const inp = document.getElementById("f_data");
                    if (!inp) return;
                    inp.value = data;
                    if (window.jQuery) {
                        window.jQuery(inp).datepicker('update', data);
                        window.jQuery(inp).trigger('change');
                        window.jQuery('.datepicker').hide();
                    }
                }''', t.data)
                time.sleep(1)
                self._tratar_competencia(page, t.data)

                valor = page.locator('#f_valor')
                valor.click()
                valor.fill("")
                valor.type(f"{t.valor:.2f}".replace(".", ","))
                time.sleep(0.5)

                self.selecionar_select2(page, "f_formapagamento", "TRANSF. BANCÁRIA", dropdown_is_ajax=False)
                self._escolher_conta_movimentacao(page, "f_contaorigem", t.conta_origem)
                self._escolher_conta_movimentacao(page, "f_conta", t.conta_destino)
                self.selecionar_select2(page, "f_historicoorigem", HISTORICO_TRANSFERENCIA, dropdown_is_ajax=True)
                complemento = f"TRANSFERENCIA {t.codigo} - {self.sanitizar_descricao(t.descricao)}"
                self._preencher_campos(page, {"f_complementoorigem": complemento, "f_complemento": complemento,
                                              "f_documento": t.codigo})
                time.sleep(1)

                ultimo = i == len(transferencias) - 1
                botao = page.locator(f'button.btn-salvar[data-comando="{"F" if ultimo else "N"}"]')
                if botao.count() > 0:
                    botao.first.click()
                else:
                    page.locator('button.btn-success:has(i.icon-ok)').first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                if self._mes_fechado_na_tela(page):
                    raise MesFechadoError(t.data)
                self._confirmar_gravacao(page, timeout_ms=25000)
                gravadas += 1
            if gravadas:
                self.update_status(f"✅ {gravadas} transferência(s) entre contas lançada(s) no SIGA.", "#3C763D")
        except MesFechadoError:
            raise
        except Exception as e:
            logging.error(f"Erro lançando transferências: {e}", exc_info=True)
            self._capturar_tela_e_log(page, "erro_inserir_transferencias")
            self.update_status(f"Falha ao lançar transferência: {e}", "#D9534F")
        return gravadas
