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


def test_fluxo_ofertas_importa_so_as_contas_da_adm(monkeypatch):
    adm = dict(_dados(), tipo_adm="ADM", nome_adm="DOURADOS - MS", tipo_extrato="CORRENTE")
    dr = dict(_dados(), conta_id="00000-6", conta_siga_corrente="10127", tipo_adm="DR", nome_adm="DOURADOS",
              tipo_extrato="CORRENTE")
    mensagens = []
    bot = SigaBot([adm, dr], callbacks={"show_message": lambda t, tit, m: mensagens.append(m)}, tipo_lote="ofertas")
    bot.browser_aberto = True
    importadas = []
    monkeypatch.setattr(bot, "_verificar_sessao_ativa", lambda page: None)
    monkeypatch.setattr(bot, "_ajustar_localidade_competencia", lambda page, tipo, nome, comp: True)
    monkeypatch.setattr(bot, "contas_permitidas_ofertas", lambda page: None)
    monkeypatch.setattr(bot, "importar_ofertas_siga",
                        lambda page, dados: importadas.append(dados["conta_siga_corrente"]) or "importado")

    bot._fluxo_ofertas(page=None)

    # A DR fica de fora: na ADM o Banco do modal não lista a conta dela
    assert importadas == ["10130"]
    assert "Importadas: 1" in mensagens[0] and "Fora da ADM: 1" in mensagens[0]


def test_fluxo_ofertas_conta_fora_do_banco_e_pulada_sem_contar_falha(monkeypatch):
    manutencao = dict(_dados(), conta_siga_corrente="10123", tipo_adm="ADM", nome_adm="DOURADOS - MS",
                      tipo_extrato="CORRENTE")
    mensagens = []
    bot = SigaBot([manutencao], callbacks={"show_message": lambda t, tit, m: mensagens.append((t, m))},
                  tipo_lote="ofertas")
    bot.browser_aberto = True
    monkeypatch.setattr(bot, "_verificar_sessao_ativa", lambda page: None)
    monkeypatch.setattr(bot, "_ajustar_localidade_competencia", lambda page, tipo, nome, comp: True)
    monkeypatch.setattr(bot, "contas_permitidas_ofertas", lambda page: None)
    monkeypatch.setattr(bot, "importar_ofertas_siga", lambda page, dados: "sem_conta")

    bot._fluxo_ofertas(page=None)

    tipo, msg = mensagens[0]
    assert tipo == "info"
    assert "Conta sem importação: 1" in msg and "Falhas: 0" in msg


class _GradePaginada:
    """Imita o frame da TES05601: grade ngx-datatable com paginador (first/next)."""

    def __init__(self, paginas):
        self.paginas, self.atual = paginas, len(paginas) - 1  # começa fora da 1ª página

    def locator(self, seletor):
        return _LocalizadorGrade(self, seletor)


class _LocalizadorGrade:
    def __init__(self, grade, seletor):
        self.grade, self.seletor = grade, seletor

    @property
    def first(self):
        return self

    def locator(self, _seletor):
        return self

    def count(self):
        return 1

    def all_inner_texts(self):
        return self.grade.paginas[self.grade.atual]

    def inner_text(self):
        return self.grade.paginas[self.grade.atual][0]

    def _alvo(self):
        return 0 if "first page" in self.seletor else self.grade.atual + 1

    def get_attribute(self, _nome):
        desabilitado = self._alvo() in (self.grade.atual, len(self.grade.paginas))
        return "disabled" if desabilitado else ""

    def click(self):
        self.grade.atual = self._alvo()


def test_ler_grade_percorre_todas_as_paginas(monkeypatch):
    monkeypatch.setattr(ofertas.time, "sleep", lambda s: None)
    grade = _GradePaginada([["10005 01/01/2024"], ["100176 31/10/2026"]])

    linhas = _bot()._ler_grade_importacoes(grade)

    # A importação mais nova fica na 2ª página e precisa entrar na checagem de duplicidade
    assert linhas == ["10005 01/01/2024", "100176 31/10/2026"]


def test_fluxo_ofertas_pula_conta_fora_da_lista_sem_abrir_a_tela(monkeypatch):
    regional = dict(_dados(), conta_siga_corrente="10129", tipo_adm="ADM", nome_adm="DOURADOS - MS",
                    tipo_extrato="CORRENTE")
    manutencao = dict(regional, conta_id="00000-1", conta_siga_corrente="10123")
    mensagens = []
    bot = SigaBot([regional, manutencao], callbacks={"show_message": lambda t, tit, m: mensagens.append(m)},
                  tipo_lote="ofertas")
    bot.browser_aberto = True
    leituras, importadas = [], []
    monkeypatch.setattr(bot, "_verificar_sessao_ativa", lambda page: None)
    monkeypatch.setattr(bot, "_ajustar_localidade_competencia", lambda page, tipo, nome, comp: True)
    monkeypatch.setattr(bot, "contas_permitidas_ofertas", lambda page: leituras.append(1) or {"10129", "10130"})
    monkeypatch.setattr(bot, "importar_ofertas_siga",
                        lambda page, dados: importadas.append(dados["conta_siga_corrente"]) or "importado")

    bot._fluxo_ofertas(page=None)

    # A lista é lida uma vez na localidade e a 10123 nem chega a abrir a tela
    assert leituras == [1]
    assert importadas == ["10129"]
    assert "Conta sem importação: 1" in mensagens[0] and "Falhas: 0" in mensagens[0]
