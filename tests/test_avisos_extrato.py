"""Avisos de rendimento e tarifa faltando (Fase 1 do plano de automações)."""

from controllers.avisos_extrato import avisos_do_extrato
from controllers.diferenca_extrato import linhas_do_extrato
from controllers.prova_real import CONFERE, MovimentoBanco, ResultadoExtrato, ResultadoSaldo
from ui import tema


def aplicacao(saldo, transacoes):
    return {"tipo_extrato": "APLICACAO", "saldo_atual": saldo, "transacoes": transacoes}


def test_aplicacao_com_saldo_sem_rendimento_avisa():
    avisos = avisos_do_extrato(aplicacao(5000.0, [{"descricao": "APLICACAO", "valor": 100.0}]), [])
    assert len(avisos) == 1 and "rendimento" in avisos[0]


def test_aplicacao_com_rendimento_ou_sem_saldo_nao_avisa():
    assert avisos_do_extrato(aplicacao(5000.0, [{"descricao": "RENDIMENTOS", "valor": 3.2}]), []) == []
    assert avisos_do_extrato(aplicacao(0.0, []), []) == []
    assert avisos_do_extrato(aplicacao(None, []), []) == []


def test_conta_corrente_nao_cobra_rendimento():
    assert avisos_do_extrato({"tipo_extrato": None, "saldo_atual": 900.0, "transacoes": []}, []) == []


def test_tarifa_sem_lancamento_avisa_com_total():
    faltas = [MovimentoBanco("05/10/2026", -45.0, "CESTA DE RELACIONAMENTO"),
              MovimentoBanco("06/10/2026", -20.0, "RECEBIMENTO PIX")]
    avisos = avisos_do_extrato({"transacoes": []}, faltas)
    assert len(avisos) == 1 and "1 tarifa" in avisos[0] and "45,00" in avisos[0]


def test_aviso_aparece_no_painel_mesmo_com_saldo_conferido():
    r = ResultadoExtrato("1", "10315", "ADM", "APLICACAO", "ok", saldo=ResultadoSaldo(CONFERE, 1.0, 1.0),
                         avisos=["Aplicação sem rendimento"])
    assert ("alerta", "   Aviso: Aplicação sem rendimento") in linhas_do_extrato(r)


def test_cores_antigas_do_robo_viram_tokens_que_passam_no_contraste():
    for antiga, nova in tema.COR_LEGADA.items():
        assert nova.startswith("#") and nova != antiga
