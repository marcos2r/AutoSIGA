from bot_falso import PaginaGravadora, criar_bot

import bot.extratos as extratos

DADOS = {"conta_siga_corrente": "10130", "conta_siga_aplicacao": "10230"}


def _lancamentos():
    return [
        {"valor": -200.0, "descricao": "APLIC FINANCEIRA", "data": "05/08/2026"},
        {"valor": 1500.5, "descricao": "RESGATE", "data": "10/08/2026"},
    ]


def test_resgate_vem_primeiro_e_inverte_origem_e_destino(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaGravadora()

    bot.inserir_lancamentos_siga(pagina, _lancamentos())

    contas = [(c, t) for c, t in reg.select2 if c in ("f_contaorigem", "f_conta", "f_historico")]
    assert contas == [
        # Resgate: sai da aplicação para a corrente, histórico 031
        ("f_contaorigem", "10230"), ("f_conta", "10130"), ("f_historico", "031"),
        # Aplicação: sai da corrente para a aplicação, histórico 002
        ("f_contaorigem", "10130"), ("f_conta", "10230"), ("f_historico", "002"),
    ]
    assert pagina.valores("#f_valor") == ["1500,50", "200,00"]
    assert reg.campos[0]["f_complemento"] == "RESGATE - RESGATE"
    assert bot._qtd_injecoes_efetuadas == 2


def test_abre_a_rotina_uma_vez_e_salva_e_novo_ate_o_ultimo(monkeypatch):
    bot, reg = criar_bot(monkeypatch, extratos, "extrato", DADOS)
    pagina = PaginaGravadora()

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
