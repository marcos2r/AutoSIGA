"""
Disparo do SigaBot em thread separada (extratos e energia) com callbacks via self.after(0, ...).
"""

import logging
import threading
import time
from tkinter import messagebox

from bot.siga_bot import SigaBot
from models.faturas_pendentes import FaturasPendentes
from ui.modais_energia import ModalPerguntaMapeamentoUC


class AcoesSigaMixin:
    """Inicia as automações no SIGA a partir da janela principal."""

    def iniciar_conexao_siga(self, event=None):
        """
        Valida os dados de todos os cards da tela e instiga a Thread de automação web.
        """
        if not self.verificar_e_solicitar_credenciais():
            return
        lote_valido = self._montar_lote_extratos()
        if not lote_valido:
            return

        # Bloqueia reentrância
        self.botao_conectar.configure(state="disabled")

        # Destrói navegador órfão antes de abrir um novo
        if getattr(self, 'bot_instance', None) and getattr(self.bot_instance, 'browser_aberto', False):
            self.atualizar_status("Encerrando janela antiga do SIGA...", "#F89406")
            self.bot_instance.fechar_browser()
            self.update()
            time.sleep(2)

        self.atualizar_status("Iniciando lote de automação no SIGA...", "#F89406")
        self.progress_bar.set(0.0)

        callbacks = {
            "update_status": self.atualizar_status,
            "update_progress": lambda val: self.after(0, lambda: self.progress_bar.set(val)),
            "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
            "request_authorization": lambda pend: self.after(0, lambda: self.mostrar_janela_lancamentos(pend)),
            "show_dashboard": lambda tel, t: self.after(0, lambda: self.mostrar_dashboard_produtividade(tel, t)),
            "on_finish": lambda: self.after(0, lambda: self.botao_conectar.configure(state="normal"))
        }

        self.bot_instance = SigaBot(lote_valido, callbacks)
        threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

    def _montar_lote_extratos(self):
        """
        Coleta os cards da tela, aplica o filtro manual de datas e monta o lote para o bot.

        Returns:
            list | None: Extratos prontos para o SigaBot, ou None se houve aviso ao usuário.
        """
        if not self.cards_lote:
            messagebox.showwarning("Atenção", "Nenhum extrato carregado.")
            return None

        # Garante o salvamento explícito de todos os inputs inseridos nos cards antes de coletar os dados
        for card in self.cards_lote:
            card.salvar_e_notificar()

        # Coleta os filtros manuais de datas (opcionais)
        data_ini_raw = self.entry_data_inicio.get().strip()
        data_fim_raw = self.entry_data_fim.get().strip()

        def formatar_para_data(str_d):
            import datetime
            if not str_d:
                return None
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    return datetime.datetime.strptime(str_d, fmt).date()
                except ValueError:
                    pass
            return None

        d_ini = formatar_para_data(data_ini_raw)
        d_fim = formatar_para_data(data_fim_raw)

        # Alerta se o formato de data estiver incorreto
        if (data_ini_raw and not d_ini) or (data_fim_raw and not d_fim):
            messagebox.showwarning("Aviso de Formato", "As datas inseridas no filtro manual são inválidas. Use o formato DD/MM/AAAA.")
            return None

        lote_valido = []
        for card in self.cards_lote:
            info = card.obter_dados_mapeados()
            if not info["valido"]:
                messagebox.showwarning("Atenção", f"O extrato da conta {card.conta_id} possui mapeamento incompleto!")
                return None

            dados_exec = card.dados_extrato.copy()

            # Aplica o filtro manual de datas sobre a lista de transações se os campos forem preenchidos
            if d_ini or d_fim:
                transacoes_filtradas = []
                for tx in dados_exec.get("transacoes", []):
                    tx_date = formatar_para_data(tx.get("data", ""))
                    if not tx_date:
                        transacoes_filtradas.append(tx)
                        continue
                    if d_ini and tx_date < d_ini:
                        continue
                    if d_fim and tx_date > d_fim:
                        continue
                    transacoes_filtradas.append(tx)
                dados_exec["transacoes"] = transacoes_filtradas

            dados_exec["conta_siga_corrente"] = info["corrente"]
            dados_exec["conta_siga_aplicacao"] = info["aplicacao"]
            dados_exec["tipo_adm"] = info["tipo_adm"]
            dados_exec["nome_adm"] = info["nome_adm"]
            dados_exec["localidade_selecionada"] = f"{info['tipo_adm']} - {info['nome_adm']}"

            # Só adiciona extrato se houver transações remanescentes após o filtro
            if dados_exec.get("transacoes"):
                lote_valido.append(dados_exec)

        if not lote_valido:
            messagebox.showinfo("Lote Vazio", "Nenhum lançamento restante no lote após aplicar os filtros de datas informados.")
            return None
        return lote_valido

    def iniciar_importacao_ofertas(self, event=None):
        """Importa no SIGA (TES05602) o TXT de ofertas de cada conta corrente do lote."""
        if not self.verificar_e_solicitar_credenciais():
            return
        lote_valido = self._montar_lote_extratos()
        if not lote_valido:
            return
        if not any(d.get("tipo_extrato") != "APLICACAO" for d in lote_valido):
            messagebox.showwarning("Atenção", "Nenhuma conta corrente no lote para importar ofertas.")
            return
        if not messagebox.askyesno("Importar Ofertas no SIGA",
                                   "O robô vai importar no SIGA o TXT de ofertas de cada conta corrente do lote, "
                                   "com a data do último dia do mês do extrato. Continuar?", parent=self):
            return

        self.botao_importar_ofertas.configure(state="disabled")
        self.atualizar_status("Iniciando importação de ofertas no SIGA...", "#F89406")
        self.progress_bar.set(0.0)
        callbacks = {
            "update_status": self.atualizar_status,
            "update_progress": lambda val: self.after(0, lambda: self.progress_bar.set(val)),
            "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
            "on_finish": lambda: self.after(0, lambda: self.botao_importar_ofertas.configure(state="normal"))
        }
        self.bot_instance = SigaBot(lote_valido, callbacks, tipo_lote="ofertas")
        threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

    def iniciar_importacao_energia(self):
        """
        Coleta e valida as faturas de energia e inicia a thread do SigaBot para injeção.
        """
        if not self.verificar_e_solicitar_credenciais():
            return

        self.atualizar_status("Obtendo faturas de energia do e-mail...", "#428BCA")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.panel_energia.btn_importar.configure(state="disabled")

        # Roda o processamento do controller em uma thread secundária para não travar a GUI
        def rodar_thread_energia():
            try:
                from controllers.fatura_energia_controller import FaturaEnergiaController
                lote_valido, lote_pendente = FaturaEnergiaController.processar_lote_energia(self.atualizar_status)

                if not lote_valido and not lote_pendente:
                    self.atualizar_status("Nenhuma fatura a processar.", "#F89406")
                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self.panel_energia.btn_importar.configure(state="normal"))
                    return

                # Se houver UCs pendentes de mapeamento, resolvemos de forma interativa (um a um).
                # As faturas já estão gravadas como pendentes: quem não for mapeado agora
                # continua na aba Energia para a próxima importação.
                if lote_pendente:
                    self.atualizar_status("Resolvendo UCs não mapeadas...", "#F89406")
                    pendentes = FaturasPendentes(self.config_manager)
                    locs_dict = {l["codigo"]: l["nome"] for l in self.config_manager.get_localidades_energia()}
                    for fat in lote_pendente:
                        uc_num = fat.get("uc", "")
                        # Outra fatura da mesma UC pode ter sido mapeada neste mesmo lote
                        mapeados = {m["uc"]: m["localidade_codigo"] for m in self.config_manager.get_mapeamentos_uc()}
                        codigo = mapeados.get(uc_num)

                        if not codigo:
                            resposta_codigo = [None]
                            thread_blocked = threading.Event()

                            def cb_resposta(codigo_escolhido, resposta=resposta_codigo, evento=thread_blocked):
                                resposta[0] = codigo_escolhido
                                evento.set()

                            # Abre o popup na main thread e espera a resposta do usuário
                            caminho_pdf = fat.get("caminho_arquivo", "")
                            self.after(0, lambda u=uc_num, path=caminho_pdf: ModalPerguntaMapeamentoUC(self, u, self.config_manager, cb_resposta, caminho_pdf=path))
                            thread_blocked.wait()
                            codigo = resposta_codigo[0]

                        if codigo:
                            fat["localidade_codigo"] = codigo
                            fat["localidade_nome"] = locs_dict.get(codigo, "DESCONHECIDA")
                            lote_valido.append(fat)
                            pendentes.remover(fat)
                        else:
                            self.atualizar_status(f"Fatura UC {uc_num} ficou pendente na aba Energia.", "#F89406")

                    self.after(0, self.panel_energia.atualizar_pendentes)

                if not lote_valido:
                    self.atualizar_status("Nenhuma fatura de energia restante para importar.", "#F89406")
                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self.panel_energia.btn_importar.configure(state="normal"))
                    return
            except Exception as e_thread:
                logging.error(f"Erro na thread de energia: {e_thread}", exc_info=True)
                self.atualizar_status(f"Erro: {e_thread}", "#D9534F")
                self.after(0, self.panel_energia.atualizar_pendentes)
                self.after(0, lambda: self.progress_bar.stop())
                self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                self.after(0, lambda: self.panel_energia.btn_importar.configure(state="normal"))
                # O nome da exceção some ao fim do except: a mensagem precisa ser capturada antes
                msg_erro = f"Ocorreu um erro ao buscar faturas: {e_thread}"
                self.after(0, lambda: messagebox.showerror("Erro", msg_erro, parent=self))
                return

            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
            self.atualizar_status(f"Preparando importação de {len(lote_valido)} faturas no SIGA...", "#428BCA")

            # Formata telemetria e inicia o SigaBot no modo energia
            callbacks = {
                "update_status": self.atualizar_status,
                "update_progress": lambda val: self.after(0, lambda: self.progress_bar.set(val)),
                "show_message": lambda t, tit, m: self.after(0, lambda: self.exibir_mensagem_topo(t, tit, m)),
                "request_authorization": lambda pend: self.after(0, lambda: self.mostrar_janela_lancamentos(pend)),
                "show_dashboard": lambda tel, t: self.after(0, lambda: self.mostrar_dashboard_produtividade(tel, t)),
                "on_finish": lambda: self.after(0, lambda: [
                    self.panel_energia.btn_importar.configure(state="normal"),
                    self.progress_bar.set(0.0)
                ])
            }

            # Dispara automação do SigaBot
            self.bot_instance = SigaBot(lote_valido, callbacks, tipo_lote="energia")
            threading.Thread(target=self.bot_instance.fluxo_automacao, daemon=True).start()

        threading.Thread(target=rodar_thread_energia, daemon=True).start()
