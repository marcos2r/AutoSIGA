import pytest
from bot_falso import PaginaGravadora, criar_bot

import bot.energia as energia
import models.config_manager as config_manager


class ConfigFalsa:
    processadas: list = []
    localidades = [{"codigo": "BR 10-0516", "nome": "ADM DOURADOS"}]

    def get_localidades_energia(self):
        return self.localidades

    def marcar_fatura_processada(self, numero):
        ConfigFalsa.processadas.append(numero)


def _fatura(numero="F1", emissao="29/06/2026", localidade="BR 10-0516"):
    return {
        "numero_fatura": numero, "emissao": emissao, "vencimento": "15/07/2026",
        "valor": 321.45, "uc": "123456", "referencia": "06/2026", "consumo": "150",
        "localidade_codigo": localidade, "caminho_arquivo": "",
    }


@pytest.fixture
def bot_energia(monkeypatch):
    ConfigFalsa.processadas = []
    monkeypatch.setattr(config_manager, "ConfigManager", ConfigFalsa)
    bot, reg = criar_bot(monkeypatch, energia, "energia")
    reg.consultas = []
    reg.ja_lancadas = set()
    reg.no_banco = set()
    reg.consulta_falha = set()

    def verificar(page, numero, emissao=None, vencimento=None, fatura=None):
        reg.consultas.append(numero)
        if numero in reg.consulta_falha:
            raise RuntimeError("grade cortada")
        # Na primeira consulta (pré-check) responde pelo que já existia; depois, pelo banco
        if reg.consultas.count(numero) == 1:
            return numero in reg.ja_lancadas
        return numero in reg.no_banco

    monkeypatch.setattr(bot, "verificar_fatura_ja_lancada", verificar)
    monkeypatch.setattr(bot, "_garantir_localidade_competencia", lambda page, uc, comp: None)
    return bot, reg


def test_lanca_fatura_e_confirma_na_auditoria(bot_energia):
    bot, reg = bot_energia
    reg.no_banco = {"F1"}
    pagina = PaginaGravadora()

    bot.inserir_faturas_energia_siga(pagina, [_fatura()])

    assert pagina.valores("#f_executar_programa", "fill") == ["TES01502"]
    assert pagina.valores("#f_documento") == ["F1"]
    assert ("f_centrocusto_rateio", "10-0516") in reg.select2
    assert ("f_fornecedor", "ENERGISA") in reg.select2
    assert pagina.valores('input[name="f_observacao1"]') == [
        "PROVISÃO ENERGIA ELÉTRICA - UC 123456 - REF 06/2026 - CONSUMO: 150 kWh"]
    assert reg.gravacoes == 1
    assert ConfigFalsa.processadas == ["F1"]
    assert bot.faturas_energia_sucesso == [_fatura()]
    assert bot._qtd_injecoes_efetuadas == 1


def test_auditoria_nao_confirma_fatura_ausente_do_banco(bot_energia):
    bot, reg = bot_energia

    bot.inserir_faturas_energia_siga(PaginaGravadora(), [_fatura()])

    assert reg.gravacoes == 1
    assert bot.faturas_energia_sucesso == []
    assert bot._qtd_injecoes_efetuadas == 0


def test_fatura_ja_lancada_e_pulada_e_marcada(bot_energia):
    bot, reg = bot_energia
    reg.ja_lancadas = {"F1"}
    pagina = PaginaGravadora()

    bot.inserir_faturas_energia_siga(pagina, [_fatura()])

    assert pagina.valores("#f_executar_programa", "fill") == []
    assert reg.gravacoes == 0
    assert ConfigFalsa.processadas == ["F1"]


def test_competencia_fechada_pula_as_demais_do_mesmo_mes(bot_energia):
    bot, reg = bot_energia
    pagina = PaginaGravadora(competencia_fechada=True)

    bot.inserir_faturas_energia_siga(pagina, [_fatura("F1"), _fatura("F2"), _fatura("F3", emissao="10/07/2026")])

    assert reg.gravacoes == 0
    # F2 é pulada sem nem consultar o SIGA; F3 é de outro mês e é tentada
    assert reg.consultas == ["F1", "F3"]
    assert ConfigFalsa.processadas == []


@pytest.mark.parametrize("codigo, nome, esperado", [
    ("BR 10-0516", "QUALQUER", "10-0516"),
    ("X1", "BR 10-0244 - POSTO", "10-0244"),
    ("X1", "ADM DOURADOS", "ADM"),
    ("X1", "POSTO - CAARAPO", "CAARAPO"),
])
def test_centro_de_custo_vem_do_codigo_ou_do_nome(bot_energia, monkeypatch, codigo, nome, esperado):
    bot, reg = bot_energia
    monkeypatch.setattr(ConfigFalsa, "localidades", [{"codigo": codigo, "nome": nome}])

    bot.inserir_faturas_energia_siga(PaginaGravadora(), [_fatura(localidade=codigo)])

    assert ("f_centrocusto_rateio", esperado) in reg.select2


def test_sem_conseguir_conferir_no_siga_a_fatura_nao_e_lancada(bot_energia):
    bot, reg = bot_energia
    reg.consulta_falha = {"F1"}
    pagina = PaginaGravadora()

    bot.inserir_faturas_energia_siga(pagina, [_fatura("F1")])

    assert pagina.valores("#f_executar_programa", "fill") == []
    assert reg.gravacoes == 0
    assert "conferir" in bot.motivos_energia["F1"]


def test_fatura_sem_numero_nao_e_lancada(bot_energia):
    bot, reg = bot_energia

    bot.inserir_faturas_energia_siga(PaginaGravadora(), [_fatura("")])

    assert reg.gravacoes == 0
    assert reg.consultas == []


def test_ja_lancada_por_outra_pessoa_fica_com_o_motivo(bot_energia):
    bot, reg = bot_energia
    reg.ja_lancadas = {"F1"}

    bot.inserir_faturas_energia_siga(PaginaGravadora(), [_fatura("F1")])

    assert "já estava no SIGA" in bot.motivos_energia["F1"]
