"""
Controller de Faturas de Energia (Energisa).

Responsável por fazer o download do e-mail, extrair os dados e aplicar os filtros de regras
de negócio (Data de corte, UCs duplicadas, relacionamento de UC -> Localidade).
"""

import os
import shutil
import logging
from datetime import datetime
import keyring

from caminhos import diretorio_base
from models.config_manager import ConfigManager
from models.email_reader import EmailReader
from models.faturas_pendentes import FaturasPendentes
from models.pdf_extractor import PdfExtractor

class FaturaEnergiaController:
    """
    Coordena o processamento em lote de faturas de energia.
    """

    @staticmethod
    def processar_lote_energia(callback_status=None) -> tuple:
        """
        Executa o fluxo completo de obtenção, processamento e validação de faturas.

        Args:
            callback_status (callable): Função para atualizar status na interface.

        Returns:
            tuple: (lote_valido, lote_pendente_mapeamento)
        """
        def log_msg(msg, cor="#666666"):
            if callback_status:
                callback_status(msg, cor)
            logging.info(msg)

        config_mgr = ConfigManager()
        email_cfg = config_mgr.get_email_config()
        
        email_user = email_cfg.get("email", "")
        servidor = email_cfg.get("servidor", "imap.gmail.com")
        mes_corte = email_cfg.get("mes_corte", "")
        
        # Define pastas de trabalho
        base_dir = diretorio_base()
        pasta_temp = os.path.join(base_dir, "faturas_temporarias")
        pasta_organizada = os.path.join(base_dir, "faturas_energisa")
        os.makedirs(pasta_organizada, exist_ok=True)

        pdfs_baixados = []
        if email_user:
            log_msg("Conectando à caixa de e-mail e baixando anexos...", "#428BCA")
            pdfs_baixados = EmailReader.baixar_faturas_email(servidor, email_user, None, pasta_temp, mes_corte=mes_corte)
        else:
            log_msg("⚠️ Configuração de e-mail incompleta. Preencha na aba Energia.", "#D9534F")

        if pdfs_baixados:
            log_msg(f"Processando {len(pdfs_baixados)} faturas baixadas...", "#428BCA")
        else:
            log_msg("Nenhuma fatura nova encontrada no e-mail.", "#F89406")

        novas = []
        for pdf_path in pdfs_baixados:
            dados_fat = FaturaEnergiaController._extrair_e_organizar(pdf_path, mes_corte, pasta_organizada, log_msg)
            if dados_fat:
                novas.append(dados_fat)

        # Remove diretório temporário
        try:
            if os.path.exists(pasta_temp):
                shutil.rmtree(pasta_temp)
        except Exception:
            pass

        # 3. Junta as novas com as pendentes de execuções anteriores (a nova prevalece
        # se o mesmo PDF voltar do e-mail) e cruza com as UCs mapeadas
        pendentes = FaturasPendentes(config_mgr)
        candidatas = {FaturasPendentes.chave(fat): fat for fat in pendentes.listar()}
        if candidatas:
            log_msg(f"{len(candidatas)} fatura(s) pendente(s) de execuções anteriores incluída(s).", "#428BCA")
        for fat in novas:
            if pendentes.foi_descartada(fat):
                log_msg(f"Fatura UC {fat['uc']} ({fat['referencia']}) já foi descartada pelo usuário. Ignorada.", "#666666")
                continue
            candidatas[FaturasPendentes.chave(fat)] = fat

        lote_valido = []
        lote_pendente_mapeamento = []
        mapeamentos_uc = {m["uc"]: m["localidade_codigo"] for m in config_mgr.get_mapeamentos_uc()}
        localidades_dict = {l["codigo"]: l["nome"] for l in config_mgr.get_localidades_energia()}

        for dados_fat in candidatas.values():
            if not os.path.exists(dados_fat.get("caminho_arquivo", "")):
                log_msg(f"PDF da fatura UC {dados_fat.get('uc', '')} não encontrado. Removida das pendentes.", "#D9534F")
                pendentes.remover(dados_fat)
                continue

            codigo_loc = mapeamentos_uc.get(dados_fat["uc"])
            if codigo_loc:
                dados_fat["localidade_codigo"] = codigo_loc
                dados_fat["localidade_nome"] = localidades_dict.get(codigo_loc, "DESCONHECIDA")
                lote_valido.append(dados_fat)
                pendentes.remover(dados_fat)
            else:
                # Grava já como pendente: se o usuário pular o mapeamento ou o app
                # fechar no meio, a fatura continua disponível na próxima importação
                pendentes.adicionar(dados_fat)
                lote_pendente_mapeamento.append(dados_fat)

        log_msg(f"Processamento concluído. {len(lote_valido)} válidas, {len(lote_pendente_mapeamento)} pendentes de UC.", "#3C763D")
        return lote_valido, lote_pendente_mapeamento

    @staticmethod
    def _extrair_e_organizar(pdf_path: str, mes_corte: str, pasta_organizada: str, log_msg) -> dict | None:
        """
        Extrai os dados de um PDF baixado, aplica os filtros e move o arquivo para a pasta final.

        Args:
            pdf_path (str): PDF temporário baixado do e-mail.
            mes_corte (str): Mês de corte "MM/AAAA" (vazio desativa o filtro).
            pasta_organizada (str): Pasta onde o PDF é guardado como UC_REFERENCIA.pdf.
            log_msg (callable): Função de log/status.

        Returns:
            dict | None: Dados da fatura, ou None se ela foi descartada.
        """
        try:
            dados_fat = PdfExtractor.extrair_dados_fatura(pdf_path)

            # Validações estruturais mínimas
            if not dados_fat["uc"] or not dados_fat["vencimento"] or dados_fat["valor"] <= 0.0:
                log_msg(f"Fatura inválida ou ilegível ignorada: {os.path.basename(pdf_path)}", "#D9534F")
                os.remove(pdf_path)
                return None

            # 2. Filtro de Mês/Ano de corte (competência)
            # Usa a data de emissão para determinar o mês real da fatura,
            # pois o campo "referência" indica o período de consumo/leitura
            # e é tipicamente 1-2 meses anterior ao mês da fatura.
            if mes_corte and dados_fat["emissao"]:
                try:
                    dt_emissao = datetime.strptime(dados_fat["emissao"], "%d/%m/%Y")
                    dt_corte = datetime.strptime(mes_corte, "%m/%Y")
                    # Compara o mês/ano da emissão com o mês de corte
                    if dt_emissao.replace(day=1) < dt_corte:
                        log_msg(f"Fatura emitida em {dados_fat['emissao']} anterior ao mês de corte ({mes_corte}). Ignorada.", "#666666")
                        os.remove(pdf_path)
                        return None
                except Exception:
                    pass

            # Move para pasta organizada final nomeando apropriadamente
            # Nome do arquivo: UC_REFERENCIA.pdf (Ex: 89000505136_07_2026.pdf)
            uc_limpa = "".join(c for c in dados_fat["uc"] if c.isdigit())
            ref_limpa = dados_fat["referencia"].replace("/", "_")
            nome_final = f"{uc_limpa}_{ref_limpa}.pdf"
            caminho_final = os.path.join(pasta_organizada, nome_final)

            # Trata colisão
            shutil.copy2(pdf_path, caminho_final)
            os.remove(pdf_path)
            dados_fat["caminho_arquivo"] = caminho_final
            return dados_fat

        except Exception as err:
            log_msg(f"Erro ao processar fatura: {err}", "#D9534F")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            return None
