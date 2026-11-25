"""Formato legível das durações do lote."""

import pytest

from controllers.duracao import formatar_duracao


@pytest.mark.parametrize("segundos, esperado", [
    (None, "0s"), (-5, "0s"), (0, "0s"), (0.44, "0,4s"), (3.25, "3,2s"), (9.99, "9,9s"), (28.9, "28s"),
    (60, "1m 0s"), (388, "6m 28s"), (3599, "59m 59s"),
    (3600, "1h 0min"), (412 * 60, "6h 52min"), (405 * 60 + 31, "6h 45min"), (86399, "23h 59min"),
    (86400, "1d 0h 0min"), (93900, "1d 2h 5min"), (3 * 86400 + 59, "3d 0h 0min"),
])
def test_formatar_duracao(segundos, esperado):
    assert formatar_duracao(segundos) == esperado
