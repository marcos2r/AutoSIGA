"""
Módulo de Leitura de Caixa de E-mails via Google Gmail API (Model).

Responsável por conectar ao Gmail usando autenticação OAuth2 (token.json e credentials.json),
buscar mensagens contendo faturas da Energisa e baixar os anexos PDFs: as não lidas (aba Energia,
que as marca como lidas) ou todas as de um período (provisões do lote de extratos, só leitura).
"""

import base64
import logging
import os
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from caminhos import diretorio_base

# Definimos o escopo necessário para ler e marcar mensagens como lidas
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# O Gmail limita as leituras por minuto de cada usuário (403 rateLimitExceeded, 429). A biblioteca
# tenta de novo com espera crescente, que com 7 tentativas cobre a virada do minuto da cota.
_TENTATIVAS_API = 7

class EmailReader:
    """
    Controla a autenticação OAuth2 do Google e download de faturas em formato PDF via Gmail API.
    """

    @staticmethod
    def conectado() -> bool:
        """Diz se o e-mail já foi autorizado nesta máquina (existe o token.json)."""
        return os.path.exists(os.path.join(diretorio_base(), "token.json"))

    @staticmethod
    def obter_credenciais(interativo: bool = True) -> Credentials:
        """
        Realiza a autenticação OAuth2 do Google de forma transparente.
        Salva o token.json para evitar novas solicitações de login no navegador.

        Args:
            interativo: Se False, não abre o navegador para um novo login (no meio do lote
                de extratos não há quem autorize); falha com PermissionError.
        """
        creds = None
        base_dir = diretorio_base()
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

            if not creds and not interativo:
                raise PermissionError("A autorização do e-mail expirou. Conecte de novo na aba Energia.")
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
    def _servico(service: Any = None, interativo: bool = True) -> Any:
        """Cliente da API do Gmail; os testes passam um falso."""
        if service is not None:
            return service
        return build('gmail', 'v1', credentials=EmailReader.obter_credenciais(interativo))

    @staticmethod
    def _listar_mensagens(service: Any, query: str, limite: int | None = None) -> list[dict[str, Any]]:
        """Lista todas as mensagens da busca, seguindo as páginas (a API devolve até 100 por vez).

        Args:
            service: Cliente da API do Gmail.
            query: Busca no formato da caixa do Gmail.
            limite: Para depois de juntar esse número de mensagens (None lê todas).
        """
        mensagens: list[dict[str, Any]] = []
        pagina: str | None = None
        while True:
            parametros: dict[str, Any] = {"userId": "me", "q": query}
            if pagina:
                parametros["pageToken"] = pagina
            resposta = service.users().messages().list(**parametros).execute(num_retries=_TENTATIVAS_API)
            mensagens.extend(resposta.get("messages", []))
            pagina = resposta.get("nextPageToken")
            if not pagina or (limite is not None and len(mensagens) >= limite):
                return mensagens[:limite] if limite is not None else mensagens

    @staticmethod
    def _baixar_pdfs_da_mensagem(service: Any, msg_id: str, pasta_destino: str) -> list[str]:
        """Salva os anexos PDF de uma mensagem e devolve os caminhos."""
        message = service.users().messages().get(userId='me', id=msg_id).execute(num_retries=_TENTATIVAS_API)
        payload = message.get('payload', {})
        parts = [payload]

        # Coleta todas as subpartes de e-mails multipart
        parts_to_scan = list(payload.get('parts', []))
        while parts_to_scan:
            current_part = parts_to_scan.pop(0)
            parts.append(current_part)
            if 'parts' in current_part:
                parts_to_scan.extend(current_part['parts'])

        caminhos = []
        for part in parts:
            filename = part.get('filename', '')
            attachment_id = part.get('body', {}).get('attachmentId', '')
            if not (filename and filename.lower().endswith('.pdf') and attachment_id):
                continue
            # Faz o download do anexo binário bruto
            attachment = service.users().messages().attachments().get(
                userId='me', messageId=msg_id, id=attachment_id
            ).execute(num_retries=_TENTATIVAS_API)
            file_data = base64.urlsafe_b64decode(attachment.get('data', '').encode('UTF-8'))
            caminho_salvamento = os.path.join(pasta_destino, f"temp_energisa_{msg_id}_{os.path.basename(filename)}")
            with open(caminho_salvamento, "wb") as f:
                f.write(file_data)
            caminhos.append(caminho_salvamento)
            logging.info(f"Gmail API: Anexo salvo localmente em: {caminho_salvamento}")
        return caminhos

    @staticmethod
    def buscar_faturas_periodo(inicio: date, fim: date, pasta_destino: str, service: Any = None,
                               progresso: Callable[[int, int], None] | None = None) -> list[str]:
        """Baixa os PDFs da Energisa recebidos entre duas datas, lidos ou não.

        Só lê a caixa: não marca nada como lido, para não mudar o e-mail de quem usa o robô.
        O que já foi lançado é decidido depois, no SIGA.

        Args:
            inicio: Primeiro dia da busca (inclusive).
            fim: Último dia da busca (inclusive).
            pasta_destino: Pasta onde os PDFs são salvos.
            service: Cliente da API do Gmail (None autentica pelo token.json).
            progresso: Recebe (mensagens lidas, total) a cada 10 mensagens e no fim.

        Returns:
            list[str]: Caminhos dos PDFs salvos.
        """
        os.makedirs(pasta_destino, exist_ok=True)
        service = EmailReader._servico(service, interativo=False)
        # after: e before: do Gmail excluem o próprio dia; a janela abre um dia antes e fecha um depois
        query = (f"from:energisa filename:pdf after:{(inicio - timedelta(days=1)):%Y/%m/%d}"
                 f" before:{(fim + timedelta(days=1)):%Y/%m/%d}")
        logging.info(f"Gmail API: Query de busca: {query}")
        mensagens = EmailReader._listar_mensagens(service, query)
        logging.info(f"Gmail API: {len(mensagens)} mensagem(ns) da Energisa no período.")
        caminhos: list[str] = []
        for n, msg in enumerate(mensagens, start=1):
            caminhos.extend(EmailReader._baixar_pdfs_da_mensagem(service, msg['id'], pasta_destino))
            if progresso and (n % 10 == 0 or n == len(mensagens)):
                progresso(n, len(mensagens))
        return caminhos

    @staticmethod
    def baixar_faturas_email(servidor: str, email_user: str, senha_keyring: str | None, pasta_destino: str,
                             mes_corte: str = "", service: Any = None) -> list:
        """
        Conecta ao Gmail via API oficial e baixa os PDFs da Energisa ainda não lidos (aba Energia).

        Args:
            servidor (str): Mantido para compatibilidade com o Controller.
            email_user (str): Mantido para compatibilidade com o Controller.
            senha_keyring (str): Mantido para compatibilidade com o Controller.
            pasta_destino (str): Caminho local para salvar os PDFs.
            mes_corte (str): Mês/ano de corte no formato "MM/YYYY" (ex: "06/2026").
                Se fornecido, a busca no Gmail será restrita a e-mails a partir
                do primeiro dia desse mês, evitando baixar faturas antigas desnecessárias.
            service: Cliente da API do Gmail (None autentica pelo token.json).
        """
        caminhos_baixados = []
        try:
            os.makedirs(pasta_destino, exist_ok=True)
            service = EmailReader._servico(service)

            # Monta o filtro de data (operador 'after:' do Gmail) a partir do mês de corte
            filtro_data = ""
            if mes_corte:
                try:
                    dt_corte = datetime.strptime(mes_corte, "%m/%Y")
                    filtro_data = f" after:{dt_corte.strftime('%Y/%m/%d')}"
                except ValueError:
                    logging.warning(f"Formato de mês de corte inválido: {mes_corte}. Buscando sem filtro de data.")

            # Busca mensagens não lidas vindas da Energisa contendo PDFs
            query = f"is:unread from:energisa filename:pdf{filtro_data}"
            logging.info(f"Gmail API: Query de busca: {query}")
            messages = EmailReader._listar_mensagens(service, query)

            if not messages:
                # Fallback secundário abrangendo lidas e não lidas caso esteja em depuração
                messages = EmailReader._listar_mensagens(service, f"from:energisa filename:pdf{filtro_data}", limite=10)

            logging.info(f"Gmail API: Encontradas {len(messages)} mensagens correspondentes à busca.")

            for msg_summary in messages:
                msg_id = msg_summary['id']
                baixados = EmailReader._baixar_pdfs_da_mensagem(service, msg_id, pasta_destino)
                caminhos_baixados.extend(baixados)

                # Remove a label 'UNREAD' para marcar o e-mail como lido
                if baixados:
                    try:
                        service.users().messages().batchModify(
                            userId='me',
                            body={
                                'ids': [msg_id],
                                'removeLabelIds': ['UNREAD']
                            }
                        ).execute(num_retries=_TENTATIVAS_API)
                        logging.info(f"Gmail API: Mensagem ID {msg_id} marcada como lida.")
                    except Exception as e_label:
                        logging.warning(f"Não foi possível marcar mensagem como lida: {e_label}")

        except Exception as e:
            logging.error(f"Erro ao ler e-mails via Gmail API: {e}", exc_info=True)
            raise e

        return caminhos_baixados
