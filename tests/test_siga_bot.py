from bot.siga_bot import SigaBot


class PaginaFalsa:
    """Registra as chamadas de evaluate sem abrir um navegador."""

    def __init__(self):
        self.chamadas = []

    def evaluate(self, script, arg=None):
        self.chamadas.append((script, arg))


def test_preencher_campos_envia_valores_como_argumento():
    pagina = PaginaFalsa()
    texto = 'RESGATE - PIX "Fulano" \ fim\'; alert(1); //'

    SigaBot._preencher_campos(pagina, {"f_complemento": texto, "f_documento": "OFX"})

    script, arg = pagina.chamadas[0]
    # O texto do extrato nunca é concatenado no código JavaScript
    assert texto not in script
    assert arg == {"f_complemento": texto, "f_documento": "OFX"}
