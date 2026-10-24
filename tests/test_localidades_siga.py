"""Localidades lidas do seletor "Local de Trabalho" do SIGA: só acrescenta e corrige nomes."""

from bot.siga_bot import SigaBot
from controllers.localidades_siga import (
    codigo_localidade_valido,
    localidades_do_seletor,
    mesclar_localidades,
    sincronizar_localidades,
)
from models.config_manager import ConfigManager

# Como o modal mostra: duas cópias do seletor (dois formulários), grupos e casas de oração
SELETOR = ["* Selecione *", "ADM - CENTRAL - SP", "DR - CENTRAL", "SET - SETOR 01", "SET - SETOR 02",
           "BR 10-0001 - VILA NOVA", "XX 10-0002 - ALDEIA  SÃO JOÃO", "ADM - CENTRAL - SP", "texto solto"]


def test_seletor_vira_pares_sem_repeticao_e_sem_codigo_ambiguo():
    assert localidades_do_seletor(SELETOR) == [
        ("ADM", "CENTRAL - SP"), ("DR", "CENTRAL"),
        ("BR 10-0001", "VILA NOVA"), ("XX 10-0002", "ALDEIA SÃO JOÃO")]


def test_codigo_valido():
    assert codigo_localidade_valido("br 10-0054")
    assert codigo_localidade_valido("ADM")
    assert not codigo_localidade_valido("BR 10-54")
    assert not codigo_localidade_valido("* SELECIONE *")
    assert not codigo_localidade_valido("")


def test_mescla_acrescenta_renomeia_e_nunca_remove():
    atuais = [{"codigo": "ADM", "nome": "CENTRAL - SP"}, {"codigo": "BR 10-0001", "nome": "VL NOVA"},
              {"codigo": "BR 10-0009", "nome": "SEM ACESSO NESTA MAQUINA"}]

    cadastro, novas, renomeadas = mesclar_localidades(
        atuais, [("ADM", "CENTRAL - SP"), ("BR 10-0001", "VILA NOVA"), ("BR 10-0003", "JARDIM")])

    assert cadastro == [{"codigo": "ADM", "nome": "CENTRAL - SP"}, {"codigo": "BR 10-0001", "nome": "VILA NOVA"},
                        {"codigo": "BR 10-0009", "nome": "SEM ACESSO NESTA MAQUINA"},
                        {"codigo": "BR 10-0003", "nome": "JARDIM"}]
    assert novas == ["BR 10-0003 - JARDIM"]
    assert renomeadas == ["BR 10-0001 - VILA NOVA"]
    assert atuais[1]["nome"] == "VL NOVA"  # não altera a lista recebida


def test_sincroniza_no_config_e_mantem_os_mapeamentos(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.salvar_localidade_energia("BR 10-0001", "VILA NOVA")
    cm.salvar_mapeamento_uc("2.000.111.051-00", "BR 10-0001")

    novas, renomeadas = sincronizar_localidades(SELETOR, cm)

    assert novas == ["ADM - CENTRAL - SP", "DR - CENTRAL", "XX 10-0002 - ALDEIA SÃO JOÃO"]
    assert renomeadas == []
    assert [l["codigo"] for l in cm.get_localidades_energia()] == ["BR 10-0001", "ADM", "DR", "XX 10-0002"]
    assert cm.get_mapeamentos_uc()[0]["localidade_codigo"] == "BR 10-0001"
    # Segunda leitura igual não muda nada
    assert sincronizar_localidades(SELETOR, cm) == ([], [])


def test_seletor_vazio_nao_mexe_no_cadastro(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.salvar_localidade_energia("BR 10-0001", "VILA NOVA")

    assert sincronizar_localidades(["* Selecione *"], cm) == ([], [])
    assert len(cm.get_localidades_energia()) == 1


class _Pagina:
    def __init__(self, opcoes=None, erro=False):
        self.opcoes, self.erro, self.leituras = opcoes or [], erro, 0

    def evaluate(self, script, arg=None):
        self.leituras += 1
        if self.erro:
            raise RuntimeError("modal fechou")
        return self.opcoes


def test_bot_entrega_o_seletor_uma_vez_por_execucao():
    recebidas = []
    bot = SigaBot([], {"on_localidades_siga": recebidas.append})
    pagina = _Pagina(["DR - CENTRAL"])

    bot._enviar_localidades_do_seletor(pagina)
    bot._enviar_localidades_do_seletor(pagina)

    assert recebidas == [["DR - CENTRAL"]]
    assert pagina.leituras == 1


def test_falha_na_leitura_nao_atrapalha_a_troca_de_localidade():
    recebidas = []
    bot = SigaBot([], {"on_localidades_siga": recebidas.append})

    bot._enviar_localidades_do_seletor(_Pagina(erro=True))  # não levanta
    bot._enviar_localidades_do_seletor(_Pagina(["DR - CENTRAL"]))  # tenta de novo na próxima troca

    assert recebidas == [["DR - CENTRAL"]]


def test_sem_callback_nem_le_o_seletor():
    pagina = _Pagina(["DR - CENTRAL"])
    SigaBot([], {})._enviar_localidades_do_seletor(pagina)
    assert pagina.leituras == 0
