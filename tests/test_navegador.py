"""Edge à parte do AutoSIGA: porta de depuração, reaproveitamento e abertura de um Edge novo."""

import pytest

from bot import navegador


class _Chromium:
    def __init__(self, falhar_em=()):
        self.urls = []
        self.falhar_em = falhar_em

    def connect_over_cdp(self, url, timeout):
        self.urls.append(url)
        if url in self.falhar_em:
            raise ConnectionError("recusada")
        return f"browser@{url}"


class _Playwright:
    def __init__(self, chromium):
        self.chromium = chromium


def _gravar_porta(pasta, texto):
    (pasta / navegador.ARQUIVO_PORTA).write_text(texto, encoding="utf-8")


def test_porta_ativa_le_a_primeira_linha_e_ignora_arquivo_ausente_ou_invalido(tmp_path):
    assert navegador.porta_ativa(str(tmp_path)) is None
    _gravar_porta(tmp_path, "51234\n/devtools/browser/abc\n")
    assert navegador.porta_ativa(str(tmp_path)) == 51234
    _gravar_porta(tmp_path, "lixo\n")
    assert navegador.porta_ativa(str(tmp_path)) is None
    _gravar_porta(tmp_path, "")
    assert navegador.porta_ativa(str(tmp_path)) is None


def test_reaproveita_o_edge_aberto_sem_abrir_outro(tmp_path, monkeypatch):
    _gravar_porta(tmp_path, "51234\n")
    monkeypatch.setattr(navegador, "abrir_edge", lambda *a: pytest.fail("não deveria abrir outro Edge"))
    chromium = _Chromium()

    assert navegador.conectar_edge(_Playwright(chromium), str(tmp_path)) == "browser@http://127.0.0.1:51234"
    assert chromium.urls == ["http://127.0.0.1:51234"]


def test_porta_que_sobrou_de_edge_fechado_abre_um_edge_novo(tmp_path, monkeypatch):
    _gravar_porta(tmp_path, "51234\n")
    abertos = []
    monkeypatch.setattr(navegador, "localizar_edge", lambda: "msedge.exe")
    monkeypatch.setattr(navegador, "abrir_edge", lambda exe, pasta: abertos.append(exe))
    monkeypatch.setattr(navegador, "aguardar_porta", lambda pasta: 60000)
    chromium = _Chromium(falhar_em=("http://127.0.0.1:51234",))

    assert navegador.conectar_edge(_Playwright(chromium), str(tmp_path)) == "browser@http://127.0.0.1:60000"
    assert abertos == ["msedge.exe"]


def test_sem_edge_instalado_explica_o_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(navegador, "localizar_edge", lambda: None)
    with pytest.raises(RuntimeError, match="Edge não encontrado"):
        navegador.conectar_edge(_Playwright(_Chromium()), str(tmp_path))


def test_abrir_edge_apaga_a_porta_antiga_e_pede_porta_livre(tmp_path, monkeypatch):
    _gravar_porta(tmp_path, "51234\n")
    chamadas = []
    monkeypatch.setattr(navegador.subprocess, "Popen", lambda args, **kw: chamadas.append(args))

    navegador.abrir_edge("msedge.exe", str(tmp_path))

    assert navegador.porta_ativa(str(tmp_path)) is None
    assert "--remote-debugging-port=0" in chamadas[0]
    assert f"--user-data-dir={tmp_path}" in chamadas[0]


def test_edge_que_nao_libera_a_porta_avisa_para_fechar_o_edge(tmp_path):
    with pytest.raises(RuntimeError, match="Feche todas as janelas"):
        navegador.aguardar_porta(str(tmp_path), limite_s=0.3)
