from datetime import datetime

from controllers.catalogo_contas import Catalogo, ContaSiga
from models.config_manager import ConfigManager


def _cm(tmp_path):
    return ConfigManager(config_path=str(tmp_path / "config.json"))


def test_config_antigo_sem_catalogo_carrega_vazio(tmp_path):
    cm = _cm(tmp_path)
    cm.save_config_data({"mapeamentos": [{"conta_id": "12345-6", "tipo_adm": "ADM", "nome_adm": "CENTRAL"}]})
    cat = cm.get_catalogo()
    assert cat.vazio
    assert cm.catalogo_vencido(cat)


def test_salvar_e_ler_catalogo_preserva_o_resto(tmp_path):
    cm = _cm(tmp_path)
    cm.save_config_data({"tipo_adm": "ADM", "nome_adm": "CENTRAL"})
    conta = ContaSiga("10130", "101", "ADM - CENTRAL - SP", "SICREDI", "101", "123456", "CAPTAÇÃO")
    cm.salvar_catalogo(Catalogo([conta], fonte="CTB00301", localidades_sem_acesso=["PIA - CENTRAL"]))

    cat = cm.get_catalogo()
    assert cat.contas == [conta]
    assert cat.fonte == "CTB00301"
    assert cat.localidades_sem_acesso == ["PIA - CENTRAL"]
    assert cat.lido_em  # data gravada sozinha
    assert cm.get_geral() == ("ADM", "CENTRAL")


def test_catalogo_corrompido_vira_vazio(tmp_path):
    cm = _cm(tmp_path)
    cm.save_config_data({"catalogo_contas": "lixo"})
    assert cm.get_catalogo().vazio
    cm.save_config_data({"catalogo_contas": {"contas": ["lixo", {"codigo": ""}]}})
    assert cm.get_catalogo().vazio


def test_validade_de_30_dias():
    agora = datetime(2026, 10, 23, 12, 0)
    assert not ConfigManager.catalogo_vencido(Catalogo(lido_em="2026-09-24T12:00:00"), agora)
    assert ConfigManager.catalogo_vencido(Catalogo(lido_em="2026-09-22T12:00:00"), agora)
    assert ConfigManager.catalogo_vencido(Catalogo(lido_em="ontem"), agora)


def test_localidade_preferida_e_localidades_mapeadas(tmp_path):
    cm = _cm(tmp_path)
    cm.save_config_data({"mapeamentos": [
        {"conta_id": "0101000000333333", "tipo_adm": "PIA", "nome_adm": "CENTRAL"},
        {"conta_id": "12345-6", "tipo_adm": "ADM", "nome_adm": "CENTRAL"},
        {"conta_id": "12345-6", "tipo_adm": "ADM", "nome_adm": "CENTRAL", "produto": "POUPANCA TRADICIONAL"},
    ]})
    assert cm.localidade_preferida("0101000000333333") == "PIA - CENTRAL"
    assert cm.localidade_preferida("123456") == "ADM - CENTRAL"
    assert cm.localidade_preferida("999999") == ""
    assert cm.localidades_mapeadas() == ["PIA - CENTRAL", "ADM - CENTRAL"]
