"""Código de débito automático no PDF e índice das faturas de energia (dados fictícios)."""

from types import SimpleNamespace

import models.pdf_extractor as pdf_extractor
from models.indice_faturas_energia import FaturaEnergia, montar_indice
from models.pdf_extractor import PdfExtractor

TEXTO_FATURA = (
    "Número da UC\n1.234.567.051-00\n"
    "VENCIMENTO\n26/08/2026\n"
    "TOTAL A PAGAR\nR$ 133,48\n"
    "NOTA FISCAL Nº: 017.111.222\n"
    "SUA FATURA ESTÁ CADASTRADA EM DÉBITO AUTOMÁTICO.\n"
    "DÉBITO AUTOMÁTICO UTILIZANDO O CÓDIGO: 0001234567-8\n"
)


def _pdf_falso(monkeypatch, texto):
    monkeypatch.setattr(pdf_extractor, "PdfReader",
                        lambda caminho: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: texto)]))


def test_extrai_o_codigo_de_debito_sem_o_traco(monkeypatch):
    _pdf_falso(monkeypatch, TEXTO_FATURA)

    dados = PdfExtractor.extrair_dados_fatura("fatura.pdf")

    assert dados["codigo_debito"] == "00012345678"
    assert (dados["numero_fatura"], dados["valor"], dados["vencimento"]) == ("017111222", 133.48, "26/08/2026")


def test_fatura_sem_debito_automatico_fica_sem_codigo(monkeypatch):
    _pdf_falso(monkeypatch, TEXTO_FATURA.replace("DÉBITO AUTOMÁTICO UTILIZANDO O CÓDIGO: 0001234567-8\n", ""))
    assert PdfExtractor.extrair_dados_fatura("fatura.pdf")["codigo_debito"] == ""


def _fatura(numero, codigo="00012345678", valor=133.48, uc="1.234.567.051-00"):
    return {"numero_fatura": numero, "codigo_debito": codigo, "valor": valor, "uc": uc, "vencimento": "26/08/2026"}


def test_indice_agrupa_por_codigo_e_ignora_o_que_nao_serve(tmp_path):
    for nome in ["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf", "notas.txt"]:
        (tmp_path / nome).write_text("x")
    sub = tmp_path / "2026"
    sub.mkdir()
    (sub / "f.pdf").write_text("x")
    leituras = {
        "a.pdf": _fatura("017000001"),
        "b.pdf": _fatura("017000002", codigo="00099999990", valor=250.0),
        "c.pdf": _fatura("017000003", codigo=""),        # boleto, sem débito automático
        "d.pdf": _fatura("017000001"),                   # mesma fatura baixada duas vezes
        "e.pdf": _fatura("", valor=10.0),                # sem número
        "f.pdf": _fatura("017000004", valor=140.0),
    }

    indice = montar_indice(str(tmp_path), extrair=lambda caminho: leituras[caminho.replace("\\", "/").split("/")[-1]])

    assert sorted(indice) == ["00012345678", "00099999990"]
    assert [f.numero for f in indice["00012345678"]] == ["017000001", "017000004"]
    assert indice["00099999990"][0] == FaturaEnergia("017000002", "1.234.567.051-00", 250.0, "26/08/2026",
                                                     "00099999990", str(tmp_path / "b.pdf"))


def test_pdf_ilegivel_nao_derruba_o_indice(tmp_path):
    (tmp_path / "ruim.pdf").write_text("x")
    (tmp_path / "bom.pdf").write_text("x")

    def extrair(caminho):
        if caminho.endswith("ruim.pdf"):
            raise OSError("corrompido")
        return _fatura("017000009")

    assert [f.numero for f in montar_indice(str(tmp_path), extrair=extrair)["00012345678"]] == ["017000009"]


def test_pasta_inexistente_da_indice_vazio(tmp_path):
    assert montar_indice(str(tmp_path / "nao_existe")) == {}
