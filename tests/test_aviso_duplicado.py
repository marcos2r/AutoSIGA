"""Aviso de extrato repetido no lote: diz qual arquivo ficou de fora e qual entrou no lugar."""

from ui.lote_extratos import _aviso_duplicado


def test_aviso_diz_qual_arquivo_entrou_e_o_extrato():
    mantido = {"caminho_arquivo": "C:/x/extrato (93).ofx", "conta_id": "12345-6",
               "data_inicial": "01/09/2026", "data_final": "30/09/2026"}

    aviso = _aviso_duplicado("C:/x/extrato (92).xls", mantido)

    assert aviso.startswith("• extrato (92).xls: ficou de fora; entrou extrato (93).ofx (o OFX traz")
    assert "Conta 12345-6, 01/09/2026 a 30/09/2026" in aviso


def test_entre_dois_xls_nao_cita_o_ofx():
    mantido = {"caminho_arquivo": "a.xls", "conta_id": "12345-6", "data_inicial": "01/09/2026",
               "data_final": "30/09/2026"}

    assert "OFX" not in _aviso_duplicado("b.xls", mantido)
