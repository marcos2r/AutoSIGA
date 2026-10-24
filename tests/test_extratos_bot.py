from bot_falso import PaginaGravadora, criar_bot

import bot.extratos as extratos

DADOS = {"conta_siga_corrente": "10130", "conta_siga_aplicacao": "10230"}


class PaginaMovimentacao(PaginaGravadora):
    """TES01704 falsa: as contas só aparecem depois de `carregar_apos` leituras (AJAX da forma)."""

    def __init__(self, contas=("10130", "10230"), carregar_apos=0, recarregar=False):
        super().__init__()
        self.contas, self.carregar_apos, self.recarregar = contas, carregar_apos, recarregar
        self.leituras, self.escolhas, self.recargas = 0, [], 0

    def evaluate(self, script, arg=None):
        if script == extratos._JS_OPCOES_CONTA:
            self.leituras += 1
            if self.leituras <= self.carregar_apos or (self.recarregar and not self.recargas):
                return [{"texto": "* Selecione *", "valor": "", "inativa": False}]
            return [{"texto": "101 - BANCOS", "valor": "15", "inativa": True}] + [
                {"texto": f" {c} - SICREDI", "valor": f"v{c}", "inativa": False} for c in self.contas]
        if script == extratos._JS_ESCOLHER_CONTA:
            self.escolhas.append(tuple(arg))
            return True
        if script == extratos._JS_RECARREGAR_CONTAS:
            self.recargas += 1
            return None
        return super().evaluate(script, arg)


def _lancamentos():
    return [
        {"valor": -200.0, "descricao": "APLIC FINANCEIRA", "data": "05/08/2026"},
        {"valor": 1500.5, "descricao": "RESGATE", "data": "10/08/2026"},
    ]


def test_resgate_vem_primeiro_e_inverte_origem_e_destino(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaMovimentacao()

    bot.inserir_lancamentos_siga(pagina, _lancamentos())

    # Resgate: sai da aplicação para a corrente; aplicação: da corrente para a aplicação
    assert pagina.escolhas == [("f_contaorigem", "v10230"), ("f_conta", "v10130"),
                               ("f_contaorigem", "v10130"), ("f_conta", "v10230")]
    assert [t for c, t in reg.select2 if c == "f_historico"] == ["031", "002"]
    assert pagina.valores("#f_valor") == ["1500,50", "200,00"]
    assert reg.campos[0]["f_complemento"] == "RESGATE - RESGATE"
    # Nº Documento em branco, como num lançamento manual
    assert all(c["f_documento"] == c["f_documentoorigem"] == c["f_documentodestino"] == "" for c in reg.campos)
    assert bot._qtd_injecoes_efetuadas == 2


def test_abre_a_rotina_uma_vez_e_salva_e_novo_ate_o_ultimo(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaMovimentacao()

    bot.inserir_lancamentos_siga(pagina, _lancamentos())

    assert pagina.valores("#f_executar_programa", "fill") == ["TES01704"]
    cliques = [s for s, a, _ in pagina.acoes if a == "click" and "btn-salvar" in s]
    assert cliques == ['button.btn-salvar[data-comando="N"]', 'button.btn-salvar[data-comando="F"]']
    assert reg.gravacoes == 2


def test_para_quando_o_navegador_e_fechado(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    bot.browser_aberto = False

    bot.inserir_lancamentos_siga(PaginaGravadora(), _lancamentos())

    assert reg.select2 == []
    assert reg.gravacoes == 0


def test_falha_no_select2_gera_captura_e_status_sem_propagar(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)

    def falhar(page, campo, termo, dropdown_is_ajax=True):
        raise RuntimeError("Select2 travado")

    monkeypatch.setattr(bot, "selecionar_select2", falhar)

    bot.inserir_lancamentos_siga(PaginaGravadora(), _lancamentos())

    assert reg.capturas == ["erro_inserir_lancamentos"]
    assert "Select2 travado" in reg.status[-1]
    assert bot._qtd_injecoes_efetuadas == 0


def test_espera_as_contas_carregarem_depois_da_forma(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaMovimentacao(carregar_apos=3)

    bot.inserir_lancamentos_siga(pagina, _lancamentos()[:1])

    assert pagina.escolhas == [("f_contaorigem", "v10130"), ("f_conta", "v10230")]
    assert pagina.recargas == 0 and reg.gravacoes == 1


def test_dispara_a_forma_de_novo_se_as_contas_nao_carregam(monkeypatch):
    # No SIGA real (23/10/2026) a lista ficou vazia mesmo com a forma escolhida
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaMovimentacao(recarregar=True)

    bot.inserir_lancamentos_siga(pagina, _lancamentos()[:1])

    assert pagina.recargas == 1
    assert pagina.escolhas == [("f_contaorigem", "v10130"), ("f_conta", "v10230")]
    assert reg.gravacoes == 1


def test_conta_fora_da_lista_nao_grava_e_nao_escolhe_parecida(monkeypatch):
    # "110130" contém "10130", mas não é a mesma conta
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaMovimentacao(contas=("110130", "10230"))

    bot.inserir_lancamentos_siga(pagina, _lancamentos()[:1])

    assert pagina.escolhas == [] and reg.gravacoes == 0
    assert reg.capturas == ["conta_f_contaorigem", "erro_inserir_lancamentos"]
    assert "10130" in reg.status[-1]


def test_rendimentos_em_ordem_de_data_na_conta_de_aplicacao(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaGravadora()
    rendimentos = [
        {"valor": 12.3, "descricao": "REND", "data": "20/08/2026", "documento": "777"},
        {"valor": 4.5, "descricao": "REND", "data": "03/08/2026"},
    ]

    bot.inserir_rendimentos_siga(pagina, rendimentos)

    assert pagina.valores("#f_executar_programa", "fill") == ["TES01703"]
    # 03/08 antes de 20/08; sem documento no extrato, vai "0"
    assert pagina.valores("#f_valor") == ["4,50", "12,30"]
    assert pagina.valores("#f_documento") == ["0", "777"]
    assert ("f_receita", "4100") in reg.select2
    assert ("f_conta", "10230") in reg.select2
    assert ("f_historico_debito", "029") in reg.select2
    assert reg.gravacoes == 2
    assert len(reg.mensagens) == 1


def test_mes_fechado_interrompe_lancamentos_sem_gravar(monkeypatch):
    import pytest

    from bot.extratos import MesFechadoError
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)

    with pytest.raises(MesFechadoError):
        bot.inserir_lancamentos_siga(PaginaGravadora(competencia_fechada=True), _lancamentos())

    assert reg.gravacoes == 0
    assert reg.capturas == []  # não é tratado como erro genérico


def test_mes_fechado_interrompe_rendimentos_sem_gravar(monkeypatch):
    import pytest

    from bot.extratos import MesFechadoError
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)

    with pytest.raises(MesFechadoError):
        bot.inserir_rendimentos_siga(PaginaGravadora(competencia_fechada=True),
                                     [{"valor": 4.5, "descricao": "REND", "data": "03/08/2026"}])

    assert reg.gravacoes == 0


def test_mes_fechado_vale_por_localidade_e_so_nesta_execucao(monkeypatch):
    from bot.siga_bot import SigaBot
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", {"conta_id": "1", "transacoes": [{}, {}]})
    bot.lote_processados = [{}, {}]
    telemetria = {"pendentes": 0}
    bot.competencias_fechadas.add(("PIA - CENTRAL", "05/2026"))

    assert bot._pular_competencia_fechada(("PIA - CENTRAL", "05/2026"), telemetria, 0)
    assert telemetria["pendentes"] == 2
    # A DR no mesmo mês e a PIA em outro mês continuam sendo tentadas
    assert not bot._pular_competencia_fechada(("DR - CENTRAL", "05/2026"), telemetria, 0)
    assert not bot._pular_competencia_fechada(("PIA - CENTRAL", "06/2026"), telemetria, 0)
    # Uma nova execução começa sem memória: o mês pode ter sido reaberto
    assert SigaBot([], callbacks={}).competencias_fechadas == set()
