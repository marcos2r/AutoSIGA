"""
Módulo de Leitura de Caixa de E-mails via Google Gmail API (Model).

Responsável por conectar ao Gmail usando autenticação OAuth2 (token.json e credentials.json),
buscar mensagens contendo faturas da Energisa, baixar os anexos PDFs e marcá-los como lidos.
"""

import os
import logging
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Definimos o escopo necessário para ler e marcar mensagens como lidas
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class EmailReader:
    """
    Controla a autenticação OAuth2 do Google e download de faturas em formato PDF via Gmail API.
    """

    @staticmethod
    def obter_credenciais() -> Credentials:
        """
        Realiza a autenticação OAuth2 do Google de forma transparente.
        Salva o token.json para evitar novas solicitações de login no navegador.
        """
        creds = None
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        token_path = os.path.join(base_dir, "token.json")
        credentials_path = os.path.join(base_dir, "credentials.json")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        # Se as credenciais não forem válidas, faz login no navegador
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logging.warning(f"Não foi possível fazer refresh no token: {e}. Solicitando novo login...")
                    creds = None
            
            if not creds:
                if not os.path.exists(credentials_path):
                    raise FileNotFoundError(
                        f"Arquivo credentials.json não encontrado em {credentials_path}. "
                        "Por favor, gere e coloque o arquivo na raiz do projeto conforme o walkthrough."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Salva o token gerado para a próxima execução
            with open(token_path, "w") as token:
                token.write(creds.to_json())

        return creds

    @staticmethod
    def baixar_faturas_email(servidor: str, email_user: str, senha_keyring: str, pasta_destino: str, mes_corte: str = "") -> list:
        """
        Conecta ao Gmail via API oficial e baixa os PDFs da Energisa que possuem anexo.

        Args:
            servidor (str): Mantido para compatibilidade com o Controller.
            email_user (str): Mantido para compatibilidade com o Controller.
            senha_keyring (str): Mantido para compatibilidade com o Controller.
            pasta_destino (str): Caminho local para salvar os PDFs.
            mes_corte (str): Mês/ano de corte no formato "MM/YYYY" (ex: "06/2026").
                Se fornecido, a busca no Gmail será restrita a e-mails a partir
                do primeiro dia desse mês, evitando baixar faturas antigas desnecessárias.
        """
        caminhos_baixados = []
        try:
            os.makedirs(pasta_destino, exist_ok=True)
            creds = EmailReader.obter_credenciais()
            service = build('gmail', 'v1', credentials=creds)

            # Monta o filtro de data (operador 'after:' do Gmail) a partir do mês de corte
            filtro_data = ""
            if mes_corte:
                try:
                    from datetime import datetime
                    dt_corte = datetime.strptime(mes_corte, "%m/%Y")
                    filtro_data = f" after:{dt_corte.strftime('%Y/%m/%d')}"
                except ValueError:
                    logging.warning(f"Formato de mês de corte inválido: {mes_corte}. Buscando sem filtro de data.")

            # Busca mensagens não lidas vindas da Energisa contendo PDFs
            query = f"is:unread from:energisa filename:pdf{filtro_data}"
            logging.info(f"Gmail API: Query de busca: {query}")
            results = service.users().messages().list(userId='me', q=query).execute()
            messages = results.get('messages', [])

            if not messages:
                # Fallback secundário abrangendo lidas e não lidas caso esteja em depuração
                query_fallback = f"from:energisa filename:pdf{filtro_data}"
                results_fallback = service.users().messages().list(userId='me', q=query_fallback).execute()
                messages = results_fallback.get('messages', [])[:10] # Limite de segurança

            logging.info(f"Gmail API: Encontradas {len(messages)} mensagens correspondentes à busca.")

            for msg_summary in messages:
                msg_id = msg_summary['id']
                message = service.users().messages().get(userId='me', id=msg_id).execute()
                
                payload = message.get('payload', {})
                parts = [payload]
                
                # Coleta todas as subpartes de e-mails multipart
                parts_to_scan = payload.get('parts', [])
                while parts_to_scan:
                    current_part = parts_to_scan.pop(0)
                    parts.append(current_part)
                    if 'parts' in current_part:
                        parts_to_scan.extend(current_part['parts'])

                anexo_baixado = False
                for part in parts:
                    filename = part.get('filename', '')
                    if filename and filename.lower().endswith('.pdf'):
                        body = part.get('body', {})
                        attachment_id = body.get('attachmentId', '')
                        
                        if attachment_id:
                            # Faz o download do anexo binário bruto
                            attachment = service.users().messages().attachments().get(
                                userId='me', messageId=msg_id, id=attachment_id
                            ).execute()
                            
                            file_data = base64.urlsafe_b64decode(attachment.get('data', '').encode('UTF-8'))
                            
                            caminho_salvamento = os.path.join(
                                pasta_destino, 
                                f"temp_energisa_{msg_id}_{filename}"
                            )
                            with open(caminho_salvamento, "wb") as f:
                                f.write(file_data)
                            
                            caminhos_baixados.append(caminho_salvamento)
                            logging.info(f"Gmail API: Anexo salvo localmente em: {caminho_salvamento}")
                            anexo_baixado = True

                # Remove a label 'UNREAD' para marcar o e-mail como lido
                if anexo_baixado:
                    try:
                        service.users().messages().batchModify(
                            userId='me',
                            body={
                                'ids': [msg_id],
                                'removeLabelIds': ['UNREAD']
                            }
                        ).execute()
                        logging.info(f"Gmail API: Mensagem ID {msg_id} marcada como lida.")
                    except Exception as e_label:
                        logging.warning(f"Não foi possível marcar mensagem como lida: {e_label}")

        except Exception as e:
            logging.error(f"Erro ao ler e-mails via Gmail API: {e}", exc_info=True)

        return caminhos_baixados
