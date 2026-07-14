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

from models.config_manager import ConfigManager
from models.email_reader import EmailReader
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
        
        if not email_user:
            log_msg("⚠️ Configuração de e-mail incompleta. Preencha na aba Energia.", "#D9534F")
            return [], []

        # Define pasta temporária para downloads
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pasta_temp = os.path.join(base_dir, "faturas_temporarias")
        pasta_organizada = os.path.join(base_dir, "faturas_energisa")
        os.makedirs(pasta_organizada, exist_ok=True)

        log_msg("Conectando à caixa de e-mail e baixando anexos...", "#428BCA")
        pdfs_baixados = EmailReader.baixar_faturas_email(servidor, email_user, None, pasta_temp, mes_corte=mes_corte)

        if not pdfs_baixados:
            log_msg("Nenhuma fatura nova encontrada no e-mail.", "#F89406")
            return [], []

        log_msg(f"Processando {len(pdfs_baixados)} faturas baixadas...", "#428BCA")

        lote_valido = []
        lote_pendente_mapeamento = []
        mapeamentos_uc = {m["uc"]: m["localidade_codigo"] for m in config_mgr.get_mapeamentos_uc()}
        localidades_dict = {l["codigo"]: l["nome"] for l in config_mgr.get_localidades_energia()}

        for pdf_path in pdfs_baixados:
            try:
                dados_fat = PdfExtractor.extrair_dados_fatura(pdf_path)
                
                # Validações estruturais mínimas
                if not dados_fat["uc"] or not dados_fat["vencimento"] or dados_fat["valor"] <= 0.0:
                    log_msg(f"Fatura inválida ou ilegível ignorada: {os.path.basename(pdf_path)}", "#D9534F")
                    os.remove(pdf_path)
                    continue

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
                            continue
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

                # 3. Cruzamento com Localidades e UCs mapeadas
                uc_cadastrada = dados_fat["uc"]
                if uc_cadastrada in mapeamentos_uc:
                    codigo_loc = mapeamentos_uc[uc_cadastrada]
                    dados_fat["localidade_codigo"] = codigo_loc
                    dados_fat["localidade_nome"] = localidades_dict.get(codigo_loc, "DESCONHECIDA")
                    lote_valido.append(dados_fat)
                else:
                    lote_pendente_mapeamento.append(dados_fat)

            except Exception as err:
                log_msg(f"Erro ao processar fatura: {err}", "#D9534F")
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)

        # Remove diretório temporário
        try:
            if os.path.exists(pasta_temp):
                shutil.rmtree(pasta_temp)
        except Exception:
            pass

        log_msg(f"Processamento concluído. {len(lote_valido)} válidas, {len(lote_pendente_mapeamento)} pendentes de UC.", "#3C763D")
        return lote_valido, lote_pendente_mapeamento
