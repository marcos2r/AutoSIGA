"""Formato único e legível de durações (painel do lote, Excel e log)."""

_MINUTO = 60
_HORA = 60 * _MINUTO
_DIA = 24 * _HORA


def formatar_duracao(segundos: float | None) -> str:
    """Escreve uma duração do jeito que se lê, sem arredondar para cima.

    Args:
        segundos: duração em segundos; negativo ou `None` vira zero.

    Returns:
        Abaixo de 1 min, só os segundos ("28s", ou "3,2s" abaixo de 10 s para não perder
        etapas rápidas); abaixo de 1 h, "6m 28s"; abaixo de 24 h, "6h 52min"; acima, "1d 2h 5min".
    """
    valor = max(0.0, float(segundos or 0))
    if valor < 10:
        return f"{int(valor * 10) / 10:.1f}s".replace(".", ",").replace(",0s", "s")
    total = int(valor)
    if total < _MINUTO:
        return f"{total}s"
    if total < _HORA:
        return f"{total // _MINUTO}m {total % _MINUTO}s"
    horas, resto = divmod(total, _HORA)
    minutos = resto // _MINUTO
    if total < _DIA:
        return f"{horas}h {minutos}min"
    dias, horas = divmod(horas, 24)
    return f"{dias}d {horas}h {minutos}min"
