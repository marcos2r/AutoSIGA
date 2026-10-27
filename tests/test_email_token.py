"""Renovação do token do Gmail: queda de rede não vira "autorização expirada"."""

import pytest
from google.auth.exceptions import RefreshError, TransportError

import models.email_reader as email_reader
from models.email_reader import EmailReader


class _Credenciais:
    """Token vencido que falha na renovação conforme a lista `falhas` (None = renova)."""

    valid = False
    expired = True
    refresh_token = "r"

    def __init__(self, falhas):
        self.falhas = list(falhas)
        self.renovacoes = 0

    def refresh(self, request):
        self.renovacoes += 1
        falha = self.falhas.pop(0) if self.falhas else None
        if falha:
            raise falha
        self.valid = True

    def to_json(self):
        return "{}"


@pytest.fixture
def token(tmp_path, monkeypatch):
    """token.json falso na pasta base e sem espera entre as tentativas."""
    (tmp_path / "token.json").write_text("{}")
    monkeypatch.setattr(email_reader, "diretorio_base", lambda: str(tmp_path))
    monkeypatch.setattr(email_reader.time, "sleep", lambda s: None)

    def usar(falhas):
        creds = _Credenciais(falhas)
        monkeypatch.setattr(email_reader.Credentials, "from_authorized_user_file", lambda *a: creds)
        return creds
    return usar


def test_queda_de_rede_passageira_renova_na_segunda_tentativa(token):
    creds = token([TransportError("Connection aborted")])

    assert EmailReader.obter_credenciais(interativo=False) is creds
    assert creds.renovacoes == 2


def test_rede_fora_do_ar_nao_pede_nova_autorizacao(token):
    creds = token([TransportError("Connection aborted")] * 3)

    with pytest.raises(ConnectionError, match="internet"):
        EmailReader.obter_credenciais(interativo=False)
    assert creds.renovacoes == 3


def test_token_recusado_pelo_google_pede_nova_conexao(token):
    token([RefreshError("invalid_grant")])

    with pytest.raises(PermissionError, match="aba Energia"):
        EmailReader.obter_credenciais(interativo=False)
