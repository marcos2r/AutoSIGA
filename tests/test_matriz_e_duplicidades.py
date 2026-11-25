"""Matriz do extrato em memória, prováveis duplicidades no SIGA e tempos por etapa."""

import openpyxl

from bot.cronometro import Cronometro
from controllers.diferenca_extrato import linhas_do_extrato
from controllers.exportador import Exportador
from controllers.matriz_extrato import ORIGEM_PROJETADA, linha_projetada, projetar, tem_projecao
from controllers.prova_real import (
    MovimentoSiga,
    ResultadoExtrato,
    conferir_saldo,
    duplicidades,
    normalizar_linhas_siga,
    parear,
    resumo_resultado,
)


def _linha(data, valor, historico="", lote=""):
    texto = f"{abs(valor):.2f}".replace(".", ",")
    return {"data": data, "lote": lote, "documento": "", "historico": historico, "origem": "",
            "entrada": texto if valor > 0 else "", "saida": texto if valor < 0 else "", "saldo": ""}


# --- matriz em memória ---------------------------------------------------------------------

def test_linha_projetada_le_igual_a_grade_do_siga():
    linhas = [linha_projetada("05/05/2026", -1234.5, "TARIFA"), linha_projetada("06/05/2026", 300.0)]

    movimentos = normalizar_linhas_siga(linhas)

    assert [(m.data, m.valor) for m in movimentos] == [("05/05/2026", -1234.5), ("06/05/2026", 300.0)]
    assert linhas[0]["saida"] == "1.234,50" and linhas[0]["origem"] == ORIGEM_PROJETADA


def test_projetar_nao_altera_a_leitura_original():
    lida = [_linha("01/05/2026", -10.0)]

    matriz = projetar(lida, [("02/05/2026", -45.0, "TARIFA")])

    assert len(lida) == 1 and len(matriz) == 2
    assert not tem_projecao(lida) and tem_projecao(matriz)
    # A tarifa projetada já tira a falta do banco: a etapa seguinte não a lança de novo
    assert parear([("02/05/2026", -45.0, "CESTA")], matriz)[1] == []


# --- prováveis duplicidades ----------------------------------------------------------------

def test_copia_a_mais_no_siga_e_provavel_duplicidade():
    grade = [_linha("05/05/2026", -200.0, "002 - APLICACAO", "101"), _linha("05/05/2026", -200.0, "002 - APLICACAO", "102")]
    sobras, _ = parear([("05/05/2026", -200.0, "APLIC")], grade)

    [dup] = duplicidades(sobras, grade)

    assert (dup.excluir.lote, dup.original.lote) == ("102", "101")


def test_duas_tarifas_iguais_tambem_no_banco_nao_sao_duplicidade():
    grade = [_linha("05/05/2026", -2.5, "TARIFA"), _linha("05/05/2026", -2.5, "TARIFA")]
    sobras, _ = parear([("05/05/2026", -2.5, "TAR"), ("05/05/2026", -2.5, "TAR")], grade)

    assert sobras == [] and duplicidades(sobras, grade) == []


def test_sobra_sem_gemeo_ou_de_historico_diferente_nao_e_duplicidade():
    grade = [_linha("05/05/2026", -50.0, "PIX FORNECEDOR A"), _linha("06/05/2026", -50.0, "PIX FORNECEDOR B"),
             _linha("07/05/2026", -99.0, "VALOR ERRADO")]
    sobras, _ = parear([("05/05/2026", -50.0, "PIX")], grade)

    assert len(sobras) == 2
    assert duplicidades(sobras, grade) == []


def test_duplicidade_com_data_do_dia_util_seguinte():
    grade = [_linha("08/05/2026", 300.0, "031 - RESGATE", "7"), _linha("11/05/2026", 300.0, "031 - RESGATE", "9")]
    sobras, _ = parear([("08/05/2026", 300.0, "RESG")], grade)

    assert [d.excluir.lote for d in duplicidades(sobras, grade)] == ["9"]


def _resultado_com_duplicidade():
    sobra = MovimentoSiga("05/05/2026", -200.0, "APLICACAO", "102")
    r = ResultadoExtrato("12345-6", "10130", "DR - CENTRAL", "CORRENTE", "conciliado",
                         saldo=conferir_saldo(1.0, -199.0), sobras=[sobra], faltas=[])
    r.duplicidades = duplicidades([sobra], [_linha("05/05/2026", -200.0, "APLICACAO", "101"),
                                           _linha("05/05/2026", -200.0, "APLICACAO", "102")])
    return r


def test_painel_pede_a_exclusao_com_o_numero_do_lancamento():
    r = _resultado_com_duplicidade()

    textos = [texto for _, texto in linhas_do_extrato(r)]

    assert any("Excluir no SIGA" in t for t in textos)
    assert any("lançto 102" in t and "repete o lançamento 101 de 05/05/2026" in t for t in textos)
    assert "1 provável(is) duplicidade(s)" in resumo_resultado(r)[1]


def test_excel_tem_as_abas_excluir_no_siga_e_tempos(tmp_path):
    caminho = tmp_path / "lote.xlsx"

    Exportador.gerar_excel_lote({"extratos": [_resultado_com_duplicidade()],
                                 "tempos": [("Consulta da TES01701", 4, 40.0)]}, [], str(caminho))

    wb = openpyxl.load_workbook(caminho)
    excluir = list(wb["Excluir no SIGA"].iter_rows(values_only=True))
    assert excluir[1] == ("DR - CENTRAL", "10130", "102", "05/05/2026", "APLICACAO", -200.0, "101", "05/05/2026")
    assert list(wb["Tempos por Etapa"].iter_rows(values_only=True))[1] == ("Consulta da TES01701", 4, "40s", "10s")


def test_excel_sem_duplicidade_nem_tempos_nao_cria_as_abas(tmp_path):
    caminho = tmp_path / "lote.xlsx"
    r = ResultadoExtrato("1", "10130", "DR", "CORRENTE", "conciliado", saldo=conferir_saldo(1.0, 1.0), sobras=[])

    Exportador.gerar_excel_lote({"extratos": [r]}, [], str(caminho))

    nomes = openpyxl.load_workbook(caminho).sheetnames
    assert "Excluir no SIGA" not in nomes and "Tempos por Etapa" not in nomes


# --- cronômetro ----------------------------------------------------------------------------

def test_cronometro_soma_por_etapa_mesmo_com_erro(monkeypatch):
    relogio = iter([0.0, 2.0, 10.0, 13.5, 20.0, 21.0])
    monkeypatch.setattr("bot.cronometro.time.perf_counter", lambda: next(relogio))
    c = Cronometro()

    with c.medir("Consulta"):
        pass
    with c.medir("Lançamentos"):
        pass
    try:
        with c.medir("Consulta"):
            raise RuntimeError("falhou")
    except RuntimeError:
        pass

    assert c.resumo() == [("Lançamentos", 1, 3.5), ("Consulta", 2, 3.0)]
