import pytest

from controllers.baixa_contas_pagar import (
    BAIXADA,
    BAIXAR,
    EMPATE,
    INTERMEDIARIO,
    JA_BAIXADA,
    PIX,
    SEM_PROVISAO,
    VALOR_DIFERENTE,
    ResultadoPagamento,
    decidir_pagamentos,
    ler_pagamentos,
    linhas_do_painel,
    mesmo_fornecedor,
    parcelas_da_grade,
    periodo_de_vencimento,
)

_GUIDS = iter(f"00000000-0000-0000-0000-{i:012d}" for i in range(1, 1000))


def _boleto(data, valor, nome="FERRAGENS AURORA LTDA", cnpj="11222333000144"):
    return {"data": data, "valor": -valor, "descricao": f"LIQUIDACAO BOLETO-          {cnpj} {nome}"}


def _pix(data, valor, nome="FERRAGENS AURORA LTDA", doc="11222333000144"):
    return {"data": data, "valor": -valor, "descricao": f"PAGAMENTO PIX-PIX_DEB   {doc} {nome}"}


def _linha(venc, valor, status="Lançado", fornecedor="FERRAGENS AURORA LTDA - ME", numero="100", pago="-"):
    return {"vencimento": venc, "numero": numero, "fornecedor": fornecedor, "valor": valor,
            "status": status, "guid": next(_GUIDS), "pago": pago}


def _decidir(transacoes, linhas):
    return decidir_pagamentos(ler_pagamentos(transacoes), parcelas_da_grade(linhas))


def test_le_boletos_e_pix_com_documento_e_nome_e_ignora_o_resto():
    pagamentos = ler_pagamentos([
        {"data": "05/10/2026", "valor": -1566.18,
         "descricao": "LIQUIDACAO BOLETO SICREDI-264079728 33692255000111 TORNEARIA BOA VISTA"},
        _pix("09/10/2026", 600.0, "Maria das Dores", "12345678901"),
        {"data": "09/10/2026", "valor": 50.0, "descricao": "RECEBIMENTO PIX 12345678901 FULANO"},
        {"data": "09/10/2026", "valor": -57.8, "descricao": "DEBITO CONVENIOS-SANESUL   03982931000120 SANESUL ID 1"},
    ])
    assert [(p.valor, p.documento, p.nome, p.tipo) for p in pagamentos] == [
        (1566.18, "33692255000111", "TORNEARIA BOA VISTA", "boleto"),
        (600.0, "12345678901", "Maria das Dores", PIX)]


@pytest.mark.parametrize("banco, siga, igual", [
    ("COML ELETRICA DOUR LTDA EPP", "COMERCIAL ELETRICA DOURADOS LTDA", True),
    ("CASA DA LOCACAO DE MAQUINAS", "CASA DE LOCACAO DE MAQUINAS E EQUIPAMENTOS LTDA", True),
    ("Joao Pedro da Silva", "JOAO PEDRO DA SILVA", True),
    ("COPOMAIS", "COPOMAIS INDUSTRIA E COMERCIO LTDA", True),
    ("ADEMIR DO AMARAL GOES", "REFRIGERACAO AMARAL LTDA", False),
    ("FERRAGENS AURORA LTDA", "FERRAGENS BOREAL LTDA", False),
])
def test_compara_o_nome_do_banco_com_o_fornecedor_do_siga(banco, siga, igual):
    assert mesmo_fornecedor(banco, siga) is igual


def test_baixa_a_provisao_aberta_do_fornecedor_com_o_mesmo_valor():
    [d] = _decidir([_boleto("05/10/2026", 519.0)], [_linha("08/10/2026", "519,00", numero="8813")])
    assert d.acao == BAIXAR and [p.numero for p in d.parcelas] == ["8813"] and len(d.a_aprovar) == 1


def test_parcela_do_mes_seguinte_nao_e_baixada_quando_a_do_mes_ja_esta_paga():
    linhas = [_linha("05/10/2026", "1.638,97", "Pago", numero="1"), _linha("12/10/2026", "1.638,97", numero="2")]
    [d] = _decidir([_boleto("05/10/2026", 1638.97)], linhas)
    assert d.acao == JA_BAIXADA and d.parcelas[0].numero == "1"


def test_vencimentos_proximos_de_mesmo_valor_empatam():
    linhas = [_linha("06/10/2026", "280,63", numero="1"), _linha("08/10/2026", "280,63", "Pago", numero="2")]
    [d] = _decidir([_boleto("05/10/2026", 280.63)], linhas)
    assert d.acao == EMPATE


def test_outro_fornecedor_ou_vencimento_longe_nao_casa():
    linhas = [_linha("08/10/2026", "519,00", fornecedor="MADEIREIRA SOL LTDA"), _linha("30/10/2026", "519,00")]
    [d] = _decidir([_boleto("05/10/2026", 519.0)], linhas)
    assert d.acao == SEM_PROVISAO


def test_cada_parcela_quita_um_pagamento_so():
    linhas = [_linha("16/10/2026", "94,25", numero="1"), _linha("30/10/2026", "94,25", numero="2")]
    decisoes = _decidir([_boleto("14/10/2026", 94.25), _boleto("26/10/2026", 94.25)], linhas)
    assert [d.parcelas[0].numero for d in decisoes] == ["1", "2"]


def test_pagamento_que_soma_as_parcelas_do_vencimento_vai_em_lote():
    linhas = [_linha("23/10/2026", v, "Aprovado") for v in ("100,00", "591,24", "27,50")]
    [d] = _decidir([_pix("26/10/2026", 718.74)], linhas)
    assert d.acao == BAIXAR and len(d.parcelas) == 3 and d.a_aprovar == []


def test_soma_deixa_de_fora_a_parcela_paga_por_outro_pix_do_mesmo_dia():
    linhas = [_linha("23/10/2026", v, "Aprovado", numero=v) for v in ("100,00", "591,24", "594,00")]
    [lote] = _decidir([_pix("26/10/2026", 691.24)], linhas)
    assert lote.acao == BAIXAR and sorted(p.numero for p in lote.parcelas) == ["100,00", "591,24"]

    avulso, lote = _decidir([_pix("26/10/2026", 594.0), _pix("26/10/2026", 691.24)], linhas)
    assert [p.numero for p in avulso.parcelas] == ["594,00"] and len(lote.parcelas) == 2


def test_beneficiario_intermediario_nunca_e_baixado():
    linhas = [_linha("28/10/2026", "450,00", fornecedor="MARCENARIA DELTA LTDA", numero="213090")]
    [d] = _decidir([_boleto("26/10/2026", 450.0, "BMA FUNDO DE INVESTIMENTO EM DIREITOS CR")], linhas)
    assert d.acao == INTERMEDIARIO and "213090" in d.motivo


def test_pagamento_com_juros_fica_pendente_ou_ja_baixado():
    [aberta] = _decidir([_boleto("26/10/2026", 652.19)], [_linha("23/10/2026", "644,79")])
    assert aberta.acao == VALOR_DIFERENTE and "juros" in aberta.motivo

    paga = _linha("23/10/2026", "644,79", "Pago", pago="652,19")
    [d] = _decidir([_boleto("26/10/2026", 652.19)], [paga])
    assert d.acao == JA_BAIXADA


def test_grade_ignora_energisa_e_codigo_de_parcela_invalido():
    linhas = [_linha("05/10/2026", "10,00", fornecedor="ENERGISA MATO GROSSO DO SUL"),
              dict(_linha("05/10/2026", "10,00"), guid="x"), _linha("05/10/2026", "10,00")]
    assert len(parcelas_da_grade(linhas)) == 1


def test_periodo_de_vencimento_cobre_a_janela_do_extrato():
    assert periodo_de_vencimento("01/10/2026", "31/10/2026") == ("21/09/2026", "10/11/2026")
    assert periodo_de_vencimento("", "31/10/2026") is None


def test_painel_conta_baixadas_e_sem_provisao_e_detalha_o_resto():
    baixar, sem, empate = _decidir(
        [_boleto("05/10/2026", 519.0), _boleto("05/10/2026", 77.0),
         _boleto("05/10/2026", 280.63)],
        [_linha("08/10/2026", "519,00"), _linha("06/10/2026", "280,63"), _linha("07/10/2026", "280,63")])
    linhas = linhas_do_painel([ResultadoPagamento(baixar, BAIXADA), ResultadoPagamento(sem, sem.acao),
                               ResultadoPagamento(empate, empate.acao)])
    assert [n for n, _ in linhas] == ["ok", "neutro", "alerta"]
    assert "1 boleto(s)/PIX baixado(s)" in linhas[0][1] and "sem provisão" in linhas[1][1]


def test_painel_do_extrato_mostra_os_boletos_e_pix_depois_da_energia():
    from controllers.diferenca_extrato import linhas_do_extrato
    from controllers.prova_real import ResultadoExtrato

    [d] = _decidir([_boleto("05/10/2026", 519.0)], [_linha("08/10/2026", "519,00")])
    r = ResultadoExtrato("1234", "10123", "ADM - EXEMPLO", "CORRENTE", "lancado",
                         baixas_cp=[ResultadoPagamento(d, BAIXADA)])
    assert linhas_do_extrato(r) == [("ok", "💳 1 boleto(s)/PIX baixado(s) na Contas a Pagar")]
