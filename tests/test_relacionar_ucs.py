"""UCs sem localidade no lote de extratos: pergunta uma vez por UC, antes de abrir o SIGA."""

import threading

import bot.provisoes_energia as provisoes_energia
from bot.siga_bot import SigaBot
from controllers.fatura_energia_controller import relacionar_localidades
from models.config_manager import ConfigManager
from models.faturas_pendentes import FaturasPendentes


def _config(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.salvar_localidade_energia("BR 10-0001", "ADM CENTRAL")
    return cm


def _fatura(uc, arquivo):
    return {"uc": uc, "caminho_arquivo": f"faturas_energisa/{arquivo}", "valor": 81.41,
            "referencia": "08/2026", "vencimento": "01/09/2026"}


def test_pergunta_uma_vez_por_uc_e_tira_das_pendentes(tmp_path):
    cm = _config(tmp_path)
    pendentes = FaturasPendentes(cm)
    faturas = [_fatura("2.000.111.051-00", "a_08.pdf"), _fatura("2.000.111.051-00", "a_09.pdf"),
               _fatura("3.000.222.051-00", "b_08.pdf")]
    for f in faturas:
        pendentes.adicionar(f)
    perguntas = []

    def perguntar(fat):
        perguntas.append(fat["uc"])
        if fat["uc"] == "2.000.111.051-00":
            cm.salvar_mapeamento_uc(fat["uc"], "BR 10-0001")  # quem responde salva, como a janela
            return "BR 10-0001"
        return None

    relacionadas, puladas = relacionar_localidades(faturas, perguntar, cm)

    assert perguntas == ["2.000.111.051-00", "3.000.222.051-00"]
    assert [f["caminho_arquivo"] for f in relacionadas] == ["faturas_energisa/a_08.pdf", "faturas_energisa/a_09.pdf"]
    assert all(f["localidade_nome"] == "ADM CENTRAL" for f in relacionadas)
    # A pulada continua pendente na aba Energia; as relacionadas saem
    assert [p["caminho_arquivo"] for p in pendentes.listar()] == ["faturas_energisa/b_08.pdf"]
    assert puladas == [faturas[2]]


def test_uc_relacionada_em_outra_tela_nao_e_perguntada(tmp_path):
    cm = _config(tmp_path)
    cm.salvar_mapeamento_uc("2.000.111.051-00", "BR 10-0001")

    relacionadas, _ = relacionar_localidades([_fatura("2.000.111.051-00", "a.pdf")],
                                             lambda f: (_ for _ in ()).throw(AssertionError("perguntou")), cm)

    assert relacionadas[0]["localidade_codigo"] == "BR 10-0001"


def test_bot_pergunta_pela_ui_e_espera_a_resposta(tmp_path, monkeypatch):
    cm = _config(tmp_path)
    monkeypatch.setattr(provisoes_energia, "ConfigManager", lambda: cm)
    perguntas = []

    def janela(fatura, responder):
        perguntas.append(fatura["uc"])
        # A UI responde em outra thread, como o clique na janela
        threading.Timer(0.05, lambda: responder(None)).start()

    bot = SigaBot([], {"request_uc_mapping": janela})
    bot.browser_aberto = True
    validas, puladas, sem_emissao = bot._relacionar_ucs_novas([], [_fatura("2.000.111.051-00", "a.pdf")], [])

    assert perguntas == ["2.000.111.051-00"]
    assert (validas, len(puladas), sem_emissao) == ([], 1, [])


def test_sem_janela_na_ui_segue_como_antes():
    bot = SigaBot([], {})
    sem_localidade = [_fatura("2.000.111.051-00", "a.pdf")]

    assert bot._relacionar_ucs_novas([], sem_localidade, []) == ([], sem_localidade, [])
