import os
import pytest
from models.ofx_reader import OfxReader

def test_parse_ofx_sucesso():
    # Caminho para a fixture sample.ofx
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample.ofx")
    
    dados = OfxReader.parse_file(fixture_path)
    
    assert dados["conta_id"] == "12345-6"
    assert dados["moeda"].upper() == "BRL"
    assert dados["saldo_atual"] == 10450.75
    assert dados["data_inicial"] == "01/07/2026"
    assert dados["data_final"] == "10/07/2026"
    
    assert len(dados["transacoes"]) == 3
    
    # Valida uma das transações
    tx_resgate = dados["transacoes"][2]
    assert tx_resgate["valor"] == 50.25
    assert tx_resgate["descricao"] == "RESGATE AUTOMATICO"
    # Sem tag NAME (padrão Sicredi), o histórico é igual ao MEMO
    assert tx_resgate["historico"] == "RESGATE AUTOMATICO"
    assert tx_resgate["data"] == "04/07/2026"

def test_parse_ofx_inexistente():
    with pytest.raises(ValueError) as excinfo:
        OfxReader.parse_file("caminho_inexistente_qualquer.ofx")
    assert "não é um extrato OFX válido ou está corrompido" in str(excinfo.value)

def test_parse_ofx_invalido(tmp_path):
    arquivo_invalido = tmp_path / "invalido.ofx"
    arquivo_invalido.write_text("SOU UM OFX TOTALMENTE INVALIDO", encoding="utf-8")
    
    with pytest.raises(ValueError) as excinfo:
        OfxReader.parse_file(str(arquivo_invalido))
    assert "não é um extrato OFX válido ou está corrompido" in str(excinfo.value)

# OFX fictício no layout do Sicoob (banco 756): MEMO genérico, pagador na tag NAME
# (truncada e com espaços à direita), datas com fuso e arquivo em cp1252.
OFX_SICOOB = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX>
<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
<DTSERVER>20260831120000[-3:BRT]</DTSERVER><LANGUAGE>POR</LANGUAGE></SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1</TRNUID><STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
<STMTRS><CURDEF>BRL</CURDEF>
<BANKACCTFROM><BANKID>756</BANKID><BRANCHID>0001-9</BRANCHID><ACCTID>000000-1</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260801120000[-3:BRT]</DTSTART><DTEND>20260831120000[-3:BRT]</DTEND>
<STMTTRN><TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>20260803120000[-3:BRT]</DTPOSTED><TRNAMT>100.00</TRNAMT><FITID>1</FITID><CHECKNUM>0</CHECKNUM><REFNUM>Pix</REFNUM><MEMO>PIX RECEBIDO - OUTRA IF</MEMO><NAME>Recebimento Pix Fulano de Tal   </NAME></STMTTRN>
<STMTTRN><TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>20260804120000[-3:BRT]</DTPOSTED><TRNAMT>350.00</TRNAMT><FITID>2</FITID><CHECKNUM>0</CHECKNUM><REFNUM>2</REFNUM><MEMO>CRÉD.TED-STR</MEMO><NAME>JOÃO DA SILVA</NAME></STMTTRN>
<STMTTRN><TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>20260805120000[-3:BRT]</DTPOSTED><TRNAMT>80.00</TRNAMT><FITID>3</FITID><CHECKNUM>0</CHECKNUM><REFNUM>3</REFNUM><MEMO>DEPOSITO EM DINHEIRO AG</MEMO></STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>530.00</BALAMT><DTASOF>20260831120000[-3:BRT]</DTASOF></LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

def test_parse_ofx_sicoob_nome_no_historico(tmp_path):
    arquivo = tmp_path / "sicoob.ofx"
    arquivo.write_bytes(OFX_SICOOB.encode("cp1252"))

    dados = OfxReader.parse_file(str(arquivo))

    assert dados["banco"] == "756"
    assert dados["conta_id"] == "000000-1"
    assert dados["saldo_atual"] == 530.00
    assert dados["data_inicial"] == "01/08/2026"

    pix, ted, deposito = dados["transacoes"]
    # O fuso [-3:BRT] não pode deslocar a data do lançamento
    assert pix["data"] == "03/08/2026"
    # MEMO continua isolado para os filtros; o nome do pagador só entra no histórico
    assert pix["descricao"] == "PIX RECEBIDO - OUTRA IF"
    assert pix["historico"] == "PIX RECEBIDO - OUTRA IF - Recebimento Pix Fulano de Tal"
    # Acentos em cp1252 são preservados
    assert ted["historico"] == "CRÉD.TED-STR - JOÃO DA SILVA"
    # Transação sem NAME mantém só o MEMO
    assert deposito["historico"] == "DEPOSITO EM DINHEIRO AG"

def test_montar_historico_ignora_nome_repetido():
    assert OfxReader._montar_historico("OFERTA", "") == "OFERTA"
    assert OfxReader._montar_historico("PIX RECEBIDO FULANO", "Fulano") == "PIX RECEBIDO FULANO"
    assert OfxReader._montar_historico("PIX", "Fulano") == "PIX - Fulano"
