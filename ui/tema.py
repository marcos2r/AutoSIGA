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
AMARELO_TEXTO = "#806535"     # um tom abaixo do #8A6D3B do SIGA, que ficava com 4,43:1 no fundo da janela
VERMELHO_FUNDO = "#F2DEDE"    # .alert-danger
VERMELHO_TEXTO = "#A94442"   # também fundo de botão destrutivo: branco sobre ele tem 6,3:1
VERMELHO_HOVER = "#843534"
ROXO_MES = "#A069C3"          # chip "Mês de Trabalho"
VERDE_LOCAL = "#69AA46"       # chip "Localidade" (só borda/ícone: 2,8:1 em texto)
AMARELO_BORDA = "#FAEBCC"
LARANJA_LOGO = "#F89406"      # só o ">" decorativo do logo; nunca texto ou fundo de botão
TEXTO = "#333333"             # texto principal (12,6:1)
CINZA_TEXTO = "#666666"       # texto secundário (5,7:1); #999999 reprova
CINZA_BORDA = "#DDDDDD"
CINZA_DIVISOR = "#EEEEEE"
CINZA_HOVER = "#E6E6E6"
CINZA_HOVER_FORTE = "#D4D4D4"
FUNDO_JANELA = "#F1F5F9"
FUNDO_PAINEL = "#F8F9FA"
BRANCO = "#FFFFFF"

# Cores antigas que o robô (bot/) ainda manda para a barra de status: todas reprovavam no
# contraste. A janela troca pelo token antes de pintar.
COR_LEGADA = {
    "#F89406": AMARELO_TEXTO, "#F0AD4E": AMARELO_TEXTO,
    "#428BCA": AZUL_INFO_TEXTO, "#5BC0DE": AZUL_INFO_TEXTO,
    "#D9534F": VERMELHO_TEXTO,
    "#5CB85C": VERDE_TEXTO,
    "#999999": CINZA_TEXTO,
}

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
