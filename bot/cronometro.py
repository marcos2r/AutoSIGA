"""
Tempo gasto em cada etapa do lote, para saber onde o robô demora.

O total por etapa vai para o log no fim do lote e para a aba "Tempos por Etapa" do Excel.
Só mede; não muda nenhuma decisão do robô.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager


class Cronometro:
    """Soma a duração e a quantidade de execuções de cada etapa."""

    def __init__(self) -> None:
        self._etapas: dict[str, list[float]] = {}

    @contextmanager
    def medir(self, etapa: str) -> Iterator[None]:
        """Conta o tempo do bloco `with` na etapa, mesmo se ele terminar com erro."""
        inicio = time.perf_counter()
        try:
            yield
        finally:
            vezes_total = self._etapas.setdefault(etapa, [0, 0.0])
            vezes_total[0] += 1
            vezes_total[1] += time.perf_counter() - inicio

    def resumo(self) -> list[tuple[str, int, float]]:
        """(etapa, vezes, segundos no total), da etapa mais demorada para a mais rápida."""
        itens = [(etapa, int(v), round(t, 1)) for etapa, (v, t) in self._etapas.items()]
        return sorted(itens, key=lambda item: item[2], reverse=True)

    def registrar_no_log(self) -> None:
        """Uma linha de log por etapa, com o total e a média."""
        for etapa, vezes, total in self.resumo():
            logging.info(f"[Tempo] {etapa}: {total:.1f} s em {vezes} vez(es) (média {total / vezes:.1f} s)")


class CronometroMixin:
    """Dá ao bot um cronômetro por lote (`_medir`), criado na primeira medição."""

    def _medir(self, etapa: str):
        """Context manager que soma a duração do bloco na etapa."""
        if not isinstance(getattr(self, "_cronometro", None), Cronometro):
            self._cronometro = Cronometro()
        return self._cronometro.medir(etapa)

    def _reiniciar_cronometro(self) -> Cronometro:
        """Zera as medições no começo do lote e devolve o cronômetro novo."""
        self._cronometro = Cronometro()
        return self._cronometro
