"""Remessas entre administrações reconhecidas no extrato (Fase 3, parte pura)."""

from controllers import remessas as rm

PROPRIO = "03617925000174"
OUTRA = "03794799000123"


def extrato(transacoes, conta="10125", tipo=None):
    return {"conta_siga_corrente": conta, "tipo_extrato": tipo,
            "transacoes": [{"data": d, "valor": v, "descricao": desc} for d, v, desc in transacoes]}


def desc(cnpj, codigo="SI00074", nome="CONGREGACAO CRISTA NO BRASIL"):
    return f"TRANSF ENTRE CONTAS-{codigo}   {cnpj} {nome}"


def test_recebida_de_outra_administracao_esta_pronta():
    [r] = rm.reconhecer([extrato([("13/10/2026", 75.0, desc(OUTRA))])], {PROPRIO})
    assert (r.sentido, r.valor, r.cnpj, r.codigo, r.pronta) == (rm.RECEBIDA, 75.0, OUTRA, "SI00074", True)


def test_enviada_sem_cadastro_fica_pendente_com_motivo():
    [r] = rm.reconhecer([extrato([("14/10/2026", -18899.0, desc(OUTRA, "SI01388"))])], {PROPRIO})
    assert r.sentido == rm.ENVIADA and not r.pronta
    assert OUTRA in rm.motivo_pendente(r)


def test_enviada_com_cadastro_leva_destino_e_finalidade():
    cadastro = {OUTRA: {"destino": "ADM - CAMPO GRANDE"}}
    [r] = rm.reconhecer([extrato([("14/10/2026", -100.0, desc(OUTRA))])], {PROPRIO}, cadastro)
    assert (r.destino, r.finalidade, r.pronta) == ("ADM - CAMPO GRANDE", rm.FINALIDADE_PADRAO, True)


def test_ignora_propria_terceiros_e_aplicacao():
    linhas = [("26/10/2026", 45922.43, desc(PROPRIO, "SI00119")),           # movimentação interna
              ("26/10/2026", 2178.0, desc("23447289000197", "SI00231", "LAPUCHI COMERCIO")),  # terceiro
              ("10/10/2026", 50.0, "RECEBIMENTO PIX-PIX_CRED 12345678900")]
    assert rm.reconhecer([extrato(linhas)], {PROPRIO}) == []
    assert rm.reconhecer([extrato([("13/10/2026", 75.0, desc(OUTRA))], tipo="APLICACAO")], {PROPRIO}) == []


def pendente(emissao, valor, codigo="G1"):
    return rm.RecebimentoPendente(codigo, emissao, valor, "ADM - RIO BRILHANTE - MS")


def test_casa_recebimento_pelo_valor_e_data_perto_da_emissao():
    recebidas = rm.reconhecer([extrato([("13/11/2026", 75.0, desc(OUTRA)),
                                        ("13/11/2026", 1040.0, desc(OUTRA))])], {PROPRIO})
    pendentes = [pendente("12/11/2026", 1040.0, "A"), pendente("12/11/2026", 75.0, "B"),
                 pendente("12/11/2026", 157.0, "C")]
    pares = rm.parear_recebimentos(recebidas, pendentes, "10125")
    assert sorted((r.valor, p.codigo) for r, p in pares) == [(75.0, "B"), (1040.0, "A")]


def test_nao_casa_fora_da_janela_de_datas_nem_outra_conta():
    recebidas = rm.reconhecer([extrato([("13/10/2026", 75.0, desc(OUTRA))])], {PROPRIO})
    assert rm.parear_recebimentos(recebidas, [pendente("12/11/2026", 75.0)], "10125") == []
    recebidas = rm.reconhecer([extrato([("13/11/2026", 75.0, desc(OUTRA))])], {PROPRIO})
    assert rm.parear_recebimentos(recebidas, [pendente("12/11/2026", 75.0)], "10130") == []


def test_cada_pendente_casa_uma_vez_e_prefere_a_emissao_mais_proxima():
    recebidas = rm.reconhecer([extrato([("20/11/2026", 50.0, desc(OUTRA))])], {PROPRIO})
    pendentes = [pendente("05/11/2026", 50.0, "LONGE"), pendente("19/11/2026", 50.0, "PERTO")]
    [(_, p)] = rm.parear_recebimentos(recebidas, pendentes, "10125")
    assert p.codigo == "PERTO"
