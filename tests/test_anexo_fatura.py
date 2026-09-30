import os

from controllers.anexo_fatura import nome_anexo, preparar_anexo


def test_nome_com_conta_e_centro_de_custo():
    assert nome_anexo("BR 10-0516", "ADM DOURADOS") == "3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf"


def test_nome_remove_acentos_e_caracteres_invalidos():
    assert nome_anexo("br 10-0244", "São João / Vila*Nova") == "3006 - ENERGIA ELETRICA - BR 10-0244 - SAO JOAO VILA NOVA.pdf"


def test_nome_sem_nome_de_localidade_ou_repetido():
    assert nome_anexo("BR 10-0516", "") == "3006 - ENERGIA ELETRICA - BR 10-0516.pdf"
    assert nome_anexo("CENTRAL", "CENTRAL") == "3006 - ENERGIA ELETRICA - CENTRAL.pdf"


def test_preparar_anexo_copia_sem_alterar_original(tmp_path):
    original = tmp_path / "89000505136_07_2026.pdf"
    original.write_bytes(b"%PDF-1.4 conteudo")

    copia = preparar_anexo(str(original), "BR 10-0516", "ADM DOURADOS", str(tmp_path / "anexos"))

    assert os.path.basename(copia) == "3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf"
    assert open(copia, "rb").read() == b"%PDF-1.4 conteudo"
    assert original.exists()
