import json

from models.config_manager import ConfigManager


def test_salvar_e_ler_config(tmp_path):
    caminho = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(caminho))

    cm.save_config_data({"tipo_adm": "ADM", "nome_adm": "CENTRAL"})

    assert cm.get_config_data() == {"tipo_adm": "ADM", "nome_adm": "CENTRAL"}
    # A gravação atômica não pode deixar o temporário para trás
    assert not (tmp_path / "config.json.tmp").exists()


def test_config_inexistente_retorna_vazio(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    assert cm.get_config_data() == {}


def test_config_corrompido_e_preservado_como_backup(tmp_path):
    caminho = tmp_path / "config.json"
    conteudo_truncado = '{"mapeamentos": [{"conta_id": "12345-6"'
    caminho.write_text(conteudo_truncado, encoding="utf-8")
    cm = ConfigManager(config_path=str(caminho))

    assert cm.get_config_data() == {}

    backups = list(tmp_path.glob("config.json.corrompido-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == conteudo_truncado

    # Uma nova gravação cria um config válido sem sobrescrever o backup
    cm.save_config_data({"tipo_adm": "DR"})
    assert json.loads(caminho.read_text(encoding="utf-8")) == {"tipo_adm": "DR"}
    assert backups[0].read_text(encoding="utf-8") == conteudo_truncado


def test_falha_na_gravacao_preserva_config_anterior(tmp_path, monkeypatch):
    caminho = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(caminho))
    cm.save_config_data({"nome_adm": "ORIGINAL"})

    def dump_com_falha(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(json, "dump", dump_com_falha)
    cm.save_config_data({"nome_adm": "NOVO"})
    monkeypatch.undo()

    assert cm.get_config_data() == {"nome_adm": "ORIGINAL"}


def test_baixa_de_energia_e_a_previa_das_baixas_ligadas_por_padrao(tmp_path):
    caminho = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(caminho))
    assert cm.get_baixar_energia_pelo_extrato() is True and cm.get_revisar_baixas() is True

    cm.salvar_baixar_energia_pelo_extrato(False)
    cm.salvar_revisar_baixas(False)

    recarregado = ConfigManager(config_path=str(caminho))
    assert recarregado.get_baixar_energia_pelo_extrato() is False and recarregado.get_revisar_baixas() is False


def test_xls_de_conta_corrente_nao_herda_o_mapeamento_da_aplicacao(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.salvar_mapeamento_conta("12345-6", "ADM", "CENTRAL - SP", "", "10313", produto="SICREDINVEST AUTOMATICO")

    # Conta corrente (sem produto): sem mapeamento próprio, fica para a sugestão do catálogo
    _, _, dados = cm.get_mapeamento_conta("12345-6", "ADM", "CENTRAL - SP")
    assert "conta_id" not in dados

    _, _, dados = cm.get_mapeamento_conta("12345-6", "ADM", "CENTRAL - SP", produto="SICREDINVEST AUTOMATICO")
    assert dados["aplicacao"] == "10313"

    # Em outra localidade, a busca reversa também respeita o produto
    _, _, dados = cm.get_mapeamento_conta("12345-6", "DR", "OUTRA")
    assert "conta_id" not in dados
