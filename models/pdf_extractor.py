"""
Módulo de Extração de Dados de PDFs (Model).

Responsável por abrir o arquivo PDF da fatura e extrair os campos necessários
(Número da UC, Valor, Data de Vencimento, Número da Nota Fiscal e Mês de Referência).
"""

import re
import logging
from pypdf import PdfReader

class PdfExtractor:
    """
    Extrator de dados estruturados a partir do arquivo PDF da fatura Energisa.
    """

    @staticmethod
    def extrair_dados_fatura(caminho_pdf: str) -> dict:
        """
        Lê o PDF e extrai as informações da fatura.

        Args:
            caminho_pdf (str): Caminho absoluto do PDF na máquina.

        Returns:
            dict: Dados extraídos {"uc", "valor", "vencimento", "numero_fatura", "referencia", "texto"}
        """
        dados = {
            "uc": "",
            "valor": 0.0,
            "vencimento": "",
            "numero_fatura": "",
            "emissao": "",
            "referencia": "",
            "consumo": "",
            "texto": ""
        }

        try:
            reader = PdfReader(caminho_pdf)
            texto = ""
            for page in reader.pages:
                texto_page = page.extract_text()
                if texto_page:
                    texto += texto_page + "\n"
            
            dados["texto"] = texto

            # 1. Extração do Número da UC (Unidade Consumidora)
            # Padrão da Energisa no PDF: "Número da UC\n890.005.051-36" ou semelhante.
            # Também tentamos o formato com pontos/hífen ou direto.
            uc_match = re.search(r'Número\s+da\s+UC\s*[\r\n]+([\d\.\-]+)', texto, re.IGNORECASE)
            if not uc_match:
                # Fallback Regex para os formatos X.XXX.XXX.XXX-XX, XXX.XXX.XXX-XX ou XX.XXX.XXX-XX
                uc_match = re.search(r'\d+(?:\.\d{3})+-\d{2}', texto)
            if not uc_match:
                # Layout antigo: número puro antes de "DOM.  ENT.:" (ex: "64348DOM.  ENT.:")
                uc_match = re.search(r'(\d{4,8})DOM\.?\s+ENT', texto, re.IGNORECASE)
            if not uc_match:
                # Layout antigo: "MATRÍCULA: 64348-2026-4-1" ou "CADASTRE...CÓDIGO: 0000064348-6"
                uc_match = re.search(r'MATRÍCULA:\s*(\d{4,8})', texto, re.IGNORECASE)
            
            if uc_match:
                dados["uc"] = uc_match.group(1).strip() if uc_match.groups() else uc_match.group(0).strip()

            # 2. Extração do Mês de Referência (REF: MÊS / ANO)
            # Padrão: "Julho / 2026" ou "07/2026"
            ref_match = re.search(r'REF:\s*MÊS\s*/\s*ANO\s*[\r\n]+([a-zA-Zç]+)\s*/\s*(\d{4})', texto, re.IGNORECASE)
            if ref_match:
                meses_dict = {
                    "janeiro": "01", "fevereiro": "02", "março": "03", "abril": "04",
                    "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
                    "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12"
                }
                mes_ext = ref_match.group(1).strip().lower()
                ano = ref_match.group(2).strip()
                mes_num = meses_dict.get(mes_ext, "01")
                dados["referencia"] = f"{mes_num}/{ano}"
            else:
                # Procura por "Referência: 07/2026" no texto (vindo do corpo do e-mail ou do próprio PDF)
                ref_match_alt = re.search(r'Referência:\s*(\d{2}/\d{4})', texto, re.IGNORECASE)
                if ref_match_alt:
                    dados["referencia"] = ref_match_alt.group(1).strip()

            # 3. Extração da Data de Vencimento
            # Padrão: "VENCIMENTO\n26/07/2026" ou "26/07/2026" perto de vencimento
            venc_match = re.search(r'VENCIMENTO\s*[\r\n]+(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
            if not venc_match:
                # Procura por datas comuns antes da expressão R$ valor (padrão de tabela unida do pypdf)
                venc_match = re.search(r'(\d{2}/\d{2}/\d{4})\s+R\$\s*[\d\.,]+', texto)
            if not venc_match:
                # Procura por datas comuns próximas à palavra "vencimento"
                venc_match = re.search(r'vencimento\b.{1,20}(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE | re.DOTALL)
            if not venc_match:
                # Fallback para data concatenada na linha de Nº FATURA
                venc_match = re.search(r'Nº\s+FATURA\s*[\r\n]+(?:\d+)?(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
            if venc_match:
                dados["vencimento"] = venc_match.group(1).strip() if venc_match.groups() else venc_match.group(0).strip()

            # 4. Extração do Valor
            # Padrão: "TOTAL A PAGAR\nR$ 167,48"
            valor_match = re.search(r'TOTAL\s+A\s+PAGAR\s*[\r\n]+(?:R\$\s*)?([\d\.,]+)', texto, re.IGNORECASE)
            if not valor_match:
                # Procura por "R$ 167,48" ou similar na linha de total a pagar ou matrícula
                valor_match = re.search(r'TOTAL\s+A\s+PAGAR\s+R\$\s*([\d\.,]+)', texto, re.IGNORECASE)
            if not valor_match:
                # Layout antigo: "R$ 877,69" aparece na mesma linha da referência
                # Captura o valor após "R$" que vem depois de uma data (dd/mm/aaaa R$ nnn,nn)
                valor_match = re.search(r'\d{2}/\d{2}/\d{4}\s+R\$\s*([\d\.,]+)', texto)
            if not valor_match:
                # Layout antigo: "TOTAL: 877,69" (sem "A PAGAR")
                valor_match = re.search(r'TOTAL:\s*([\d\.,]+)', texto, re.IGNORECASE)
            if valor_match:
                valor_str = valor_match.group(1).strip().replace('.', '').replace(',', '.')
                try:
                    dados["valor"] = float(valor_str)
                except ValueError:
                    pass

            # 5. Extração do Número da Fatura / Nota Fiscal
            # Padrão: "NOTA FISCAL Nº: 017.268.416" ou "Nº FATURA\n17268416"
            nf_match = re.search(r'NOTA\s+FISCAL\s+Nº\s*:\s*([\d\.]+)', texto, re.IGNORECASE)
            if nf_match:
                dados["numero_fatura"] = nf_match.group(1).strip().replace('.', '')
            else:
                nf_match_alt = re.search(r'Nº\s+FATURA\s*[\r\n]+(\d+)', texto, re.IGNORECASE)
                if nf_match_alt:
                    dados["numero_fatura"] = nf_match_alt.group(1).strip()

            # 6. Extração da Data de Emissão
            # Padrão: "DATA DE EMISSÃO:07/07/2026" ou "Data de Apresentação: 09/07/2026"
            emissao_match = re.search(r'DATA\s+DE\s+EMISSÃO\s*:\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
            if not emissao_match:
                emissao_match = re.search(r'Apresentação\s*:\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
            if emissao_match:
                dados["emissao"] = emissao_match.group(1).strip()

            # 7. Extração do Consumo (kWh)
            consumo_match = re.search(r'Consumo kWh\s*[\r\n]*\s*([\d\.,]+)', texto, re.IGNORECASE)
            if not consumo_match:
                # Tenta capturar do formato "KWH 100,00" ou "KWH Ponta 100,00"
                consumo_match = re.search(r'KWH\s*(?:Ponta\s*)?([\d\.,]+)', texto, re.IGNORECASE)
            if consumo_match:
                dados["consumo"] = consumo_match.group(1).strip()

        except Exception as e:
            logging.error(f"Erro ao ler PDF de fatura {caminho_pdf}: {e}", exc_info=True)

        return dados
