import bot.ofertas as ofertas
from bot.siga_bot import SigaBot


def _bot():
    return SigaBot([], callbacks={}, tipo_lote="ofertas")


def _dados():
    return {
        "conta_id": "58308-2",
        "conta_siga_corrente": "10130",
        "transacoes": [
            {"valor": 100.0, "descricao": "PIX RECEBIDO", "data": "10/08/2026"},
            {"valor": 1500.5, "descricao": "PIX RECEBIDO", "data": "20/08/2026"},
            {"valor": 50.0, "descricao": "RESGATE", "data": "21/08/2026"},
        ],
    }


def test_importar_ofertas_sem_ofertas_retorna_vazio():
    dados = {"conta_siga_corrente": "10130", "transacoes": [{"valor": -5.0, "descricao": "TARIFA", "data": "01/08/2026"}]}
    assert _bot().importar_ofertas_siga(page=None, dados=dados) == "vazio"


def test_importar_ofertas_pula_quando_ja_existe_na_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(ofertas, "diretorio_base", lambda: str(tmp_path))
    bot = _bot()
    monkeypatch.setattr(bot, "_abrir_importacao_extrato", lambda page: object())
    monkeypatch.setattr(bot, "_ler_grade_importacoes",
                        lambda frame: ["100175\t31/08/2026\t2026/8 - 20260901_000000\tR$ 1.600,50"])

    assert bot.importar_ofertas_siga(page=None, dados=_dados()) == "duplicado"

    # O TXT da conta é gravado ao lado do executável, só com as ofertas
    arquivos = list((tmp_path / "ofertas_importadas").glob("OFERTAS_58308-2_202608_*.txt"))
    assert len(arquivos) == 1
    assert arquivos[0].read_text(encoding="utf-8").splitlines() == [
        "10/08/2026;PIX RECEBIDO;100,00",
        "20/08/2026;PIX RECEBIDO;1500,50",
    ]
