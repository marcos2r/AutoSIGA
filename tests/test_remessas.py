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
