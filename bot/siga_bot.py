"""
Módulo de Automação Web (Bot).

Este módulo concentra toda a interação com o navegador através da biblioteca
Playwright. Ele é desenhado para agir como um "humano invisível" preenchendo
formulários no portal web do SIGA.
"""

import logging
import threading
import time
import traceback

from playwright.sync_api import sync_playwright

from bot.baixa_provisoes import BaixaProvisoesMixin
from bot.descoberta_contas import DescobertaContasMixin
from bot.energia import EnergiaMixin
from bot.energia_auditoria import AuditoriaEnergiaMixin
from bot.extratos import ExtratosMixin
from bot.fluxo_extratos import FluxoExtratosMixin
from bot.ofertas import OfertasMixin
from bot.sessao import SessaoMixin
from bot.siga_helpers import HelpersMixin
from controllers.exportador import Exportador


class SigaBot(HelpersMixin, SessaoMixin, ExtratosMixin, FluxoExtratosMixin, AuditoriaEnergiaMixin, EnergiaMixin,
             OfertasMixin, DescobertaContasMixin, BaixaProvisoesMixin):
    """
    Controlador do Navegador Playwright.

    A classe instancia o Microsoft Edge local em modo persistente, injeta cookies,
    fura formulários complexos do SIGA (como Select2 e Datepickers) e delega as
    perguntas/alertas para a View (via callbacks), sem nunca importar nada de GUI.
    """

    def __init__(self, lote_processados, callbacks, tipo_lote="extrato", revisar_antes_de_lancar=False):
        """
        Inicializa a configuração do bot de automação em lote.

        Args:
            lote_processados (list): Lista de extratos mapeados e filtrados.
            callbacks (dict): Dicionário de funções para acionar a UI. Possui:
                - update_status(msg, color)
                - show_message(tipo, titulo, msg)
                - request_authorization(lancamentos_pendentes, contexto) (só com a prévia ligada)
                - show_dashboard(telemetria, tempo_inicio)
                - on_finish()
                - on_catalogo(catalogo) (só na descoberta de contas)
            tipo_lote (str): Tipo de lote ("extrato", "energia", "ofertas" ou "descoberta").
            revisar_antes_de_lancar (bool): Mostra a prévia de cada extrato e só grava com autorização.
        """
        # Ordena o lote por localidade_selecionada para agrupar os lançamentos da mesma filial,
        # minimizando as trocas de localidade no portal SIGA.
        self.lote_processados = sorted(
            lote_processados,
            key=lambda x: f"{x.get('tipo_adm', '').strip().upper()} - {x.get('nome_adm', '').strip().upper()}"
        )
        self.callbacks = callbacks
        self.tipo_lote = tipo_lote
        self.browser_aberto = False
        self._qtd_injecoes_efetuadas = 0
        self.revisar_antes_de_lancar = revisar_antes_de_lancar
        # Prévia: a UI responde por responder_autorizacao(), que libera a thread do bot
        self._evento_autorizacao = threading.Event()
        self._autorizado = False
        self.faturas_energia_sucesso = []
        # (localidade, mm/aaaa) que o SIGA recusou nesta execução. Fica só em memória:
        # numa nova execução o mês pode ter sido reaberto, então tenta de novo.
        self.competencias_fechadas = set()

        # Atributos reativos que serão setados a cada iteração do lote:
        self.dados_processados = None
        self.localidade_selecionada = ""
        self.tipo_alvo = ""
        self.nome_alvo = ""

    def _pular_competencia_fechada(self, chave, telemetria_lote, idx):
        """Pula o extrato se a localidade e o mês já se mostraram fechados nesta execução."""
        if chave not in self.competencias_fechadas:
            return False
        qtd = len(self.dados_processados.get("transacoes", []))
        telemetria_lote["pendentes"] += qtd
        self.update_status(f"⏭️ [{chave[0]}] Mês {chave[1]} fechado no SIGA: extrato da conta "
                           f"{self.dados_processados.get('conta_id', '')} pulado ({qtd} itens pendentes).", "#D9534F")
        if "update_progress" in self.callbacks:
            self.callbacks["update_progress"]((idx + 1) / len(self.lote_processados))
        return True

    def update_status(self, msg, color="#666666"):
        """Envia um log de texto simples para o painel da interface."""
        logging.info(f"[STATUS] {msg}")
        if "update_progress" in self.callbacks:
            # Mantém a reatividade do terminal Windows limpa
            pass
        if "update_status" in self.callbacks:
            self.callbacks["update_status"](msg, color)

    def show_message(self, tipo, titulo, msg):
        """Aciona um popup na interface para alertas e erros genéricos."""
        if "show_message" in self.callbacks:
            self.callbacks["show_message"](tipo, titulo, msg)

    def fechar_browser(self):
        """Força a finalização do loop principal do Playwright."""
        self.browser_aberto = False

    def _aguardar_fechamento(self, context):
        """Mantém o navegador aberto para conferência até o usuário fechá-lo."""
        self.browser_aberto = True
        while self.browser_aberto:
            try:
                if not context.pages:
                    break
            except Exception:
                break
            time.sleep(1)

    def _fluxo_ofertas(self, page):
        """Importa o TXT de ofertas de cada conta corrente do lote na TES05602."""
        contas = [d for d in self.lote_processados if d.get("tipo_extrato") != "APLICACAO"]
        resultados = {"importado": 0, "duplicado": 0, "vazio": 0, "falha": 0}
        localidade_anterior = competencia_anterior = None

        for idx, dados in enumerate(contas):
            if not self.browser_aberto:
                break
            self._verificar_sessao_ativa(page)
            ofertas, _ = Exportador.filtrar_ofertas(dados.get("transacoes", []))
            _, _, competencia = Exportador.resumo_ofertas(ofertas)
            localidade = f"{dados['tipo_adm']}-{dados['nome_adm']}"
            if competencia and (localidade != localidade_anterior or competencia != competencia_anterior):
                if not self._ajustar_localidade_competencia(page, dados["tipo_adm"], dados["nome_adm"], competencia):
                    resultados["falha"] += 1
                    localidade_anterior = competencia_anterior = None
                    continue
                localidade_anterior, competencia_anterior = localidade, competencia

            # Uma conta com erro (ex: timeout ao abrir a tela) não interrompe as demais
            try:
                resultados[self.importar_ofertas_siga(page, dados)] += 1
            except Exception as e:
                logging.error(f"Erro ao importar ofertas da conta {dados.get('conta_id', '')}: {e}", exc_info=True)
                self._capturar_tela_e_log(page, "ofertas_erro")
                self.update_status(f"❌ Erro nas ofertas da conta {dados.get('conta_id', '')}: {str(e)[:60]}", "#D9534F")
                resultados["falha"] += 1
            if "update_progress" in self.callbacks:
                self.callbacks["update_progress"]((idx + 1) / len(contas))

        resumo = (f"Importadas: {resultados['importado']} | Já existentes: {resultados['duplicado']} | "
                  f"Sem ofertas: {resultados['vazio']} | Falhas: {resultados['falha']}")
        cor = "#D9534F" if resultados["falha"] else "#3C763D"
        self.update_status(f"Importação de ofertas concluída. {resumo}", cor)
        self.show_message("warning" if resultados["falha"] else "info", "Importação de Ofertas", resumo)

    def fluxo_automacao(self):
        """
        Coração assíncrono do bot. Roteiriza a abertura do navegador, injeção em lote e encerramento.
        """
        self.browser_aberto = True
        tempo_inicio = time.time()

        # Telemetria acumulada de todo o lote
        telemetria_lote = {
            "ofx_itens": sum(len(d.get("transacoes", [])) for d in self.lote_processados),
            "siga_itens": 0,
            "injecoes": 0,
            "pendentes": 0,
            "total_contas": len(self.lote_processados),
            "volume_financeiro": 0.0
        }

        try:
            with sync_playwright() as p:
                context, page = self._iniciar_navegador(p)

                self._validar_sessao(page)

                if self.tipo_lote == "descoberta":
                    # Só leitura: fecha o navegador sozinho ao terminar
                    self._fluxo_descoberta(page)
                    context.close()
                    return

                if self.tipo_lote == "energia":
                    self.update_status(f"Iniciando importação de {len(self.lote_processados)} faturas de energia...", "#428BCA")
                    self.inserir_faturas_energia_siga(page, self.lote_processados)

                    telemetria_lote = {
                        "tipo_lote": "energia",
                        "ofx_itens": len(self.lote_processados),
                        "siga_itens": len(self.lote_processados),
                        "injecoes": self._qtd_injecoes_efetuadas,
                        "pendentes": len(self.lote_processados) - self._qtd_injecoes_efetuadas,
                        "total_contas": len(self.lote_processados),
                        "volume_financeiro": sum(f.get("valor", 0.0) for f in self.faturas_energia_sucesso)
                    }
                    if "update_progress" in self.callbacks:
                        self.callbacks["update_progress"](1.0)

                    self.update_status("✅ Processamento de faturas de energia concluído!", "#3C763D")
                    if "show_dashboard" in self.callbacks:
                        self.callbacks["show_dashboard"](telemetria_lote, tempo_inicio)

                    self.browser_aberto = True
                    while self.browser_aberto:
                        try:
                            if not context.pages:
                                break
                        except Exception:
                            break
                        time.sleep(1)
                    return

                if self.tipo_lote == "ofertas":
                    self._fluxo_ofertas(page)
                    self._aguardar_fechamento(context)
                    return

                self._fluxo_extratos(page, telemetria_lote)
                if "show_dashboard" in self.callbacks:
                    self.callbacks["show_dashboard"](telemetria_lote, tempo_inicio)

                self.browser_aberto = True
                while self.browser_aberto:
                    try:
                        if not context.pages:
                            break
                    except Exception:
                        break
                    time.sleep(1)

        except Exception as e:
            msg_erro = f"Erro inesperado na automação do SIGA: {e}"
            try:
                print(f"⚠️ {msg_erro}")
            except UnicodeEncodeError:
                print(f"[!] {msg_erro.encode('ascii', errors='replace').decode('ascii')}")
            logging.error(msg_erro, exc_info=True)
            traceback.print_exc()

            # Tenta capturar screenshot se page estiver acessível
            try:
                if 'page' in locals() and page:
                    self._capturar_tela_e_log(page, "erro_global")
            except Exception as ss_err:
                logging.warning(f"Não foi possível salvar o screenshot do erro global: {ss_err}")

            erro_resumido = str(e).split('\n')[0][:50]
            self.update_status(f"Erro no navegador: {erro_resumido}...", "#D9534F")
        finally:
            if "on_finish" in self.callbacks:
                self.callbacks["on_finish"]()
