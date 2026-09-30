from controllers.fatura_energia_controller import FaturaEnergiaController
from models.config_manager import ConfigManager
from models.faturas_pendentes import FaturasPendentes


def _fatura(tmp_path, uc="890.005.051-36", referencia="07/2026", criar_pdf=True):
    caminho = tmp_path / f"{uc.replace('.', '').replace('-', '')}_{referencia.replace('/', '_')}.pdf"
    if criar_pdf:
        caminho.write_bytes(b"%PDF-1.4")
    return {
        "uc": uc, "valor": 150.75, "vencimento": "10/08/2026", "numero_fatura": "123",
        "emissao": "20/07/2026", "referencia": referencia, "consumo": "300",
        "caminho_arquivo": str(caminho), "texto": "texto bruto do PDF",
    }


def _repo(tmp_path):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    return cm, FaturasPendentes(cm)


def test_adicionar_persiste_sem_texto_bruto(tmp_path):
    _, repo = _repo(tmp_path)
    repo.adicionar(_fatura(tmp_path))

    pendentes = repo.listar()
    assert len(pendentes) == 1
    assert pendentes[0]["uc"] == "890.005.051-36"
    assert "texto" not in pendentes[0]


def test_adicionar_mesma_fatura_nao_duplica(tmp_path):
    _, repo = _repo(tmp_path)
    fat = _fatura(tmp_path)
    repo.adicionar(fat)
    fat["valor"] = 200.0
    repo.adicionar(fat)

    pendentes = repo.listar()
    assert len(pendentes) == 1
    assert pendentes[0]["valor"] == 200.0


def test_adicionar_sem_caminho_e_ignorado(tmp_path):
    _, repo = _repo(tmp_path)
    repo.adicionar({"uc": "1", "caminho_arquivo": ""})
    assert repo.listar() == []


def test_remover(tmp_path):
    _, repo = _repo(tmp_path)
    fat = _fatura(tmp_path)
    repo.adicionar(fat)

    assert repo.remover(fat) is True
    assert repo.listar() == []
    assert repo.remover(fat) is False


def test_descartar_remove_e_lembra(tmp_path):
    _, repo = _repo(tmp_path)
    fat = _fatura(tmp_path)
    repo.adicionar(fat)
    repo.descartar(fat)

    assert repo.listar() == []
    assert repo.foi_descartada(fat) is True
    assert repo.foi_descartada(_fatura(tmp_path, referencia="08/2026")) is False


def _preparar_controller(tmp_path, monkeypatch, novas):
    """Isola o controller: config em tmp_path, sem e-mail e sem ler PDFs reais."""
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.save_config_data({"email_energia": "teste@exemplo.com"})
    monkeypatch.setattr("controllers.fatura_energia_controller.ConfigManager", lambda: cm)
    monkeypatch.setattr("controllers.fatura_energia_controller.diretorio_base", lambda: str(tmp_path))
    monkeypatch.setattr(
        "controllers.fatura_energia_controller.EmailReader.baixar_faturas_email",
        lambda *a, **k: [f"temp_{i}.pdf" for i in range(len(novas))],
    )
    fila = list(novas)
    monkeypatch.setattr(
        FaturaEnergiaController, "_extrair_e_organizar",
        staticmethod(lambda *a, **k: fila.pop(0)),
    )
    return cm


def test_uc_nao_mapeada_fica_gravada_como_pendente(tmp_path, monkeypatch):
    fat = _fatura(tmp_path)
    cm = _preparar_controller(tmp_path, monkeypatch, [fat])

    validas, pendentes = FaturaEnergiaController.processar_lote_energia()

    assert validas == []
    assert [p["uc"] for p in pendentes] == [fat["uc"]]
    assert len(FaturasPendentes(cm).listar()) == 1


def test_pendente_anterior_volta_e_e_lancada_apos_mapeamento(tmp_path, monkeypatch):
    fat = _fatura(tmp_path)
    cm = _preparar_controller(tmp_path, monkeypatch, [])
    FaturasPendentes(cm).adicionar(fat)
    cm.salvar_localidade_energia("BR 10-0516", "ADM DOURADOS")
    cm.salvar_mapeamento_uc(fat["uc"], "BR 10-0516")

    validas, pendentes = FaturaEnergiaController.processar_lote_energia()

    assert pendentes == []
    assert len(validas) == 1
    assert validas[0]["localidade_codigo"] == "BR 10-0516"
    assert FaturasPendentes(cm).listar() == []


def test_fatura_descartada_nao_volta(tmp_path, monkeypatch):
    fat = _fatura(tmp_path)
    cm = _preparar_controller(tmp_path, monkeypatch, [fat])
    FaturasPendentes(cm).descartar(fat)

    validas, pendentes = FaturaEnergiaController.processar_lote_energia()

    assert validas == [] and pendentes == []


def test_pendente_sem_pdf_e_removida(tmp_path, monkeypatch):
    fat = _fatura(tmp_path, criar_pdf=False)
    cm = _preparar_controller(tmp_path, monkeypatch, [])
    FaturasPendentes(cm).adicionar(fat)

    validas, pendentes = FaturaEnergiaController.processar_lote_energia()

    assert validas == [] and pendentes == []
    assert FaturasPendentes(cm).listar() == []
