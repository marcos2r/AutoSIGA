"""Busca das faturas de energia do período do lote no e-mail (Gmail falso, dados fictícios)."""

import base64
from datetime import date

from controllers.fatura_energia_controller import FaturaEnergiaController
from controllers.periodo_energia import competencia_da_fatura, janela_de_busca, mes_de_corte, meses_do_lote
from models.config_manager import ConfigManager
from models.email_reader import EmailReader
from models.faturas_pendentes import FaturasPendentes


class _Chamada:
    def __init__(self, resultado):
        self.resultado = resultado

    def execute(self):
        return self.resultado


class GmailFalso:
    """Imita `service.users().messages()` com páginas de 2 mensagens."""

    def __init__(self, mensagens: dict[str, list[str]], por_pagina: int = 2):
        self.mensagens = mensagens  # id -> nomes dos anexos
        self.por_pagina = por_pagina
        self.buscas: list[dict] = []
        self.modificadas: list = []

    def users(self):
        return self

    def messages(self):
        return self

    def attachments(self):
        return self

    def list(self, userId, q, pageToken=None):
        self.buscas.append({"q": q, "pageToken": pageToken})
        ids = list(self.mensagens)
        ini = int(pageToken or 0)
        resposta = {"messages": [{"id": i} for i in ids[ini:ini + self.por_pagina]]}
        if ini + self.por_pagina < len(ids):
            resposta["nextPageToken"] = str(ini + self.por_pagina)
        return _Chamada(resposta)

    def get(self, userId, id=None, messageId=None):
        if messageId is not None:  # attachments().get
            return _Chamada({"data": base64.urlsafe_b64encode(b"%PDF-1.4").decode()})
        partes = [{"filename": nome, "body": {"attachmentId": f"a-{nome}"}} for nome in self.mensagens[id]]
        return _Chamada({"payload": {"parts": [{"filename": "", "body": {}}, *partes]}})

    def batchModify(self, userId, body):
        self.modificadas.append(body)
        return _Chamada({})


def test_meses_do_lote_cobre_o_periodo_e_o_mes_anterior():
    extratos = [{"data_inicial": "01/10/2026", "data_final": "23/10/2026"},
                {"data_inicial": "01/09/2026", "data_final": "30/09/2026"},
                {"data_inicial": None, "data_final": None}]

    assert meses_do_lote(extratos) == ["08/2026", "09/2026", "10/2026"]
    assert meses_do_lote([{"data_inicial": "15/01/2027", "data_final": "10/02/2027"}]) == \
        ["12/2026", "01/2027", "02/2027"]
    assert meses_do_lote([]) == []


def test_janela_de_busca_vai_alem_do_ultimo_mes():
    assert janela_de_busca(["09/2026", "10/2026"]) == (date(2026, 9, 1), date(2026, 11, 10))


def test_corte_da_aba_energia_e_o_mes_anterior():
    assert mes_de_corte(date(2026, 10, 23)) == "09/2026"
    assert mes_de_corte(date(2027, 1, 5)) == "12/2026"


def test_competencia_e_o_mes_da_emissao():
    assert competencia_da_fatura({"emissao": "29/09/2026", "referencia": "08/2026"}) == "09/2026"
    assert competencia_da_fatura({"emissao": ""}) == ""


def test_busca_por_periodo_le_todas_as_paginas_lidas_ou_nao_sem_marcar_como_lida(tmp_path):
    gmail = GmailFalso({"m1": ["f1.pdf"], "m2": ["f2.pdf", "leia-me.txt"], "m3": ["f3.PDF"]})

    caminhos = EmailReader.buscar_faturas_periodo(date(2026, 9, 1), date(2026, 11, 10), str(tmp_path), service=gmail)

    assert [b["pageToken"] for b in gmail.buscas] == [None, "2"]
    assert gmail.buscas[0]["q"] == "from:energisa filename:pdf after:2026/08/31 before:2026/11/11"
    assert "is:unread" not in gmail.buscas[0]["q"]
    assert sorted(p.rsplit("_", 1)[-1] for p in caminhos) == ["f1.pdf", "f2.pdf", "f3.PDF"]
    assert all(open(p, "rb").read() == b"%PDF-1.4" for p in caminhos)
    assert gmail.modificadas == []


def test_busca_por_periodo_avisa_o_progresso(tmp_path):
    gmail = GmailFalso({f"m{i}": [f"f{i}.pdf"] for i in range(12)}, por_pagina=100)
    avisos = []

    EmailReader.buscar_faturas_periodo(date(2026, 9, 1), date(2026, 9, 30), str(tmp_path), service=gmail,
                                       progresso=lambda n, total: avisos.append((n, total)))

    assert avisos == [(10, 12), (12, 12)]


def test_busca_da_aba_energia_tambem_pagina_e_marca_como_lida(tmp_path):
    gmail = GmailFalso({"m1": ["f1.pdf"], "m2": ["f2.pdf"], "m3": ["f3.pdf"]})

    caminhos = EmailReader.baixar_faturas_email("", "", None, str(tmp_path), service=gmail)

    assert len(caminhos) == 3
    assert [m["ids"] for m in gmail.modificadas] == [["m1"], ["m2"], ["m3"]]


def _fatura(tmp_path, nome, emissao, uc="890.005.051-36"):
    caminho = tmp_path / nome
    caminho.write_bytes(b"%PDF-1.4")
    return {"uc": uc, "valor": 150.75, "vencimento": "10/10/2026", "numero_fatura": nome,
            "emissao": emissao, "referencia": "08/2026", "caminho_arquivo": str(caminho)}


def _preparar(tmp_path, monkeypatch, lidas):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.salvar_localidade_energia("BR 10-0516", "ADM DOURADOS")
    cm.salvar_mapeamento_uc("890.005.051-36", "BR 10-0516")
    monkeypatch.setattr("controllers.fatura_energia_controller.ConfigManager", lambda: cm)
    monkeypatch.setattr("controllers.fatura_energia_controller.diretorio_base", lambda: str(tmp_path))
    janelas = []
    monkeypatch.setattr("controllers.fatura_energia_controller.EmailReader.buscar_faturas_periodo",
                        lambda inicio, fim, pasta, service=None, progresso=None: janelas.append((inicio, fim)) or
                        [f"temp_{i}.pdf" for i in range(len(lidas))])
    fila = list(lidas)
    monkeypatch.setattr(FaturaEnergiaController, "_extrair_e_organizar", staticmethod(lambda *a, **k: fila.pop(0)))
    return cm, janelas


def test_lote_do_periodo_fica_so_com_as_competencias_pedidas(tmp_path, monkeypatch):
    setembro = _fatura(tmp_path, "set.pdf", "28/09/2026")
    outubro = _fatura(tmp_path, "out.pdf", "05/10/2026")
    julho = _fatura(tmp_path, "jul.pdf", "30/07/2026")  # fica guardado para o índice, mas fora do lote
    sem_uc = _fatura(tmp_path, "uc_nova.pdf", "06/10/2026", uc="999.999.999-99")
    sem_data = _fatura(tmp_path, "sem_data.pdf", "")
    cm, janelas = _preparar(tmp_path, monkeypatch, [setembro, outubro, julho, sem_uc, sem_data])

    validas, pendentes, sem_emissao = FaturaEnergiaController.buscar_faturas_do_periodo(["09/2026", "10/2026"])

    assert janelas == [(date(2026, 9, 1), date(2026, 11, 10))]
    assert [f["numero_fatura"] for f in validas] == ["set.pdf", "out.pdf"]
    assert validas[0]["localidade_codigo"] == "BR 10-0516"
    assert [f["numero_fatura"] for f in pendentes] == ["uc_nova.pdf"]
    assert [p["uc"] for p in FaturasPendentes(cm).listar()] == ["999.999.999-99"]
    assert [f["numero_fatura"] for f in sem_emissao] == ["sem_data.pdf"]


def test_segunda_via_e_fatura_descartada_nao_entram_duas_vezes(tmp_path, monkeypatch):
    fat = _fatura(tmp_path, "out.pdf", "05/10/2026")
    descartada = _fatura(tmp_path, "descartada.pdf", "06/10/2026")
    cm, _ = _preparar(tmp_path, monkeypatch, [fat, dict(fat), descartada])
    FaturasPendentes(cm).descartar(descartada)

    validas, _, _ = FaturaEnergiaController.buscar_faturas_do_periodo(["10/2026"])

    assert [f["numero_fatura"] for f in validas] == ["out.pdf"]


def test_sem_meses_nao_busca_no_email(tmp_path, monkeypatch):
    _, janelas = _preparar(tmp_path, monkeypatch, [])

    assert FaturaEnergiaController.buscar_faturas_do_periodo([]) == ([], [], [])
    assert janelas == []


def test_sem_autorizacao_a_busca_do_lote_nao_abre_o_navegador(tmp_path, monkeypatch):
    monkeypatch.setattr("models.email_reader.diretorio_base", lambda: str(tmp_path))

    assert EmailReader.conectado() is False
    try:
        EmailReader.obter_credenciais(interativo=False)
    except PermissionError as erro:
        assert "aba Energia" in str(erro)
    else:
        raise AssertionError("deveria pedir nova conexão na aba Energia")
