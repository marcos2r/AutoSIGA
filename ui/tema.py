"""
Tokens de cor e fonte da interface, tirados do tema Ace (Bootstrap 3) do próprio SIGA.

Use estes nomes em vez de hex soltos: a tela fica com a cara do SIGA, que o usuário já
conhece. Os pares FUNDO/TEXTO vêm dos alertas do SIGA e passam no contraste WCAG AA
(4,5:1); o verde (#87B87F) e o laranja (#FFB752) dos botões do SIGA não passam com
texto branco e por isso não entram aqui.
"""

from controllers import estado_card

FONTE = "Open Sans"

AZUL_TITULO = "#3D71A8"       # título de seção (widget-header do SIGA)
AZUL_NAVBAR = "#2C6AA0"       # ação primária; texto branco 5,7:1
AZUL_NAVBAR_HOVER = "#245A8A"
AZUL_INFO_FUNDO = "#D9EDF7"   # .alert-info
AZUL_INFO_TEXTO = "#31708F"
VERDE_FUNDO = "#DFF0D8"       # .alert-success
VERDE_TEXTO = "#3C763D"
AMARELO_FUNDO = "#FCF8E3"     # .alert-warning
AMARELO_TEXTO = "#8A6D3B"
VERMELHO_FUNDO = "#F2DEDE"    # .alert-danger
VERMELHO_TEXTO = "#A94442"
ROXO_MES = "#A069C3"          # chip "Mês de Trabalho"
VERDE_LOCAL = "#69AA46"       # chip "Localidade" (só borda/ícone: 2,8:1 em texto)
CINZA_TEXTO = "#666666"       # texto secundário (5,7:1); #999999 reprova
CINZA_BORDA = "#DDDDDD"
CINZA_HOVER = "#E6E6E6"
BRANCO = "#FFFFFF"

# Selo de cada estado do card: (fundo, texto)
SELO = {
    estado_card.CONFIRMADO: (VERDE_FUNDO, VERDE_TEXTO),
    estado_card.SUGERIDO: (AZUL_INFO_FUNDO, AZUL_INFO_TEXTO),
    estado_card.EDITADO: (AZUL_INFO_FUNDO, AZUL_INFO_TEXTO),
    estado_card.ESCOLHA: (AMARELO_FUNDO, AMARELO_TEXTO),
    estado_card.REVISAR: (AMARELO_FUNDO, AMARELO_TEXTO),
    estado_card.NAO_ENCONTRADO: (VERMELHO_FUNDO, VERMELHO_TEXTO),
    estado_card.PENDENTE: (VERMELHO_FUNDO, VERMELHO_TEXTO),
}
