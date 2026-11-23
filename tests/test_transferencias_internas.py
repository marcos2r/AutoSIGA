"""Transferências entre contas do mesmo departamento (Movimentação Interna)."""

from controllers import transferencias_internas as ti

PROPRIO = "03617925000174"


def extrato(conta, transacoes, nome="DOURADOS - MS", tipo_adm="ADM", tipo=None):
    return {"conta_siga_corrente": conta, "tipo_adm": tipo_adm, "nome_adm": nome, "tipo_extrato": tipo,
            "transacoes": [{"data": d, "valor": v, "descricao": desc} for d, v, desc in transacoes]}


def transf(codigo, cnpj=PROPRIO):
    return f"TRANSF ENTRE CONTAS-{codigo}   {cnpj} CONGREGACAO CRISTA"


CAPTACAO = extrato("10130", [("26/10/2026", -45922.43, transf("SI00119")),
                             ("26/10/2026", -5000.0, transf("SI00084")),
                             ("22/10/2026", -55000.0, transf("SI00825"))])
MANUTENCAO = extrato("10123", [("26/10/2026", 45922.43, transf("SI00119")),
                               ("13/10/2026", 75.0, transf("SI00074", "03794799000123"))])
COZINHA = extrato("10126", [("26/10/2026", 5000.0, transf("SI00084"))])


def test_codigo_da_transferencia():
    assert ti.codigo_transferencia(transf("SI00119")) == "SI00119"
    assert ti.codigo_transferencia("RECEBIMENTO PIX") is None


def test_junta_as_pontas_com_origem_e_destino():
    pares, _ = ti.parear([CAPTACAO, MANUTENCAO, COZINHA])
    assert {(p.codigo, p.conta_origem, p.conta_destino, p.valor) for p in pares} == {
        ("SI00119", "10130", "10123", 45922.43), ("SI00084", "10130", "10126", 5000.0)}


def test_pontas_soltas_tem_motivo():
    _, soltas = ti.parear([CAPTACAO, MANUTENCAO, COZINHA])
    motivos = {(s.conta_siga, s.valor): s.motivo for s in soltas}
    assert motivos[("10130", -55000.0)] == ti.MOTIVO_SEM_PAR          # destino fora do lote
    assert motivos[("10123", 75.0)] == ti.MOTIVO_OUTRO_CNPJ           # outra administração


def test_localidades_diferentes_nao_sao_movimentacao_interna():
    piedade = extrato("20101", [("26/10/2026", 5000.0, transf("SI00084"))], tipo_adm="PIA")
    pares, soltas = ti.parear([CAPTACAO, piedade])
    assert not any(p.codigo == "SI00084" for p in pares)
    assert sum(s.motivo == ti.MOTIVO_OUTRO_DEPARTAMENTO for s in soltas) == 2


def test_aplicacao_nao_entra():
    aplic = extrato("10315", [("26/10/2026", 5000.0, transf("SI00084"))], tipo="APLICACAO")
    pares, _ = ti.parear([CAPTACAO, aplic])
    assert pares == []


def test_lanca_so_pela_origem_e_so_o_que_falta_na_grade():
    pares, _ = ti.parear([CAPTACAO, MANUTENCAO, COZINHA])
    grade = [{"data": "26/10/2026", "entrada": "", "saida": "5.000,00", "historico": "TRANSF.VLR DOC"}]
    faltam = ti.a_lancar(pares, "10130", grade)
    assert [t.codigo for t in faltam] == ["SI00119"]
    assert ti.a_lancar(pares, "10123", []) == []  # destino nunca lança
