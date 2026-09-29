"""Medição de desempenho: FPS (e, na Fase 7, cronômetro por etapa e log CSV de latência)."""

from __future__ import annotations

import time
from collections import deque

from libras import config


class ContadorFPS:
    """FPS médio dos últimos `janela` frames. Chame `atualizar()` uma vez por frame."""

    def __init__(self, janela: int = config.JANELA_FPS) -> None:
        self._tempos: deque[float] = deque(maxlen=janela)

    def atualizar(self, agora: float | None = None) -> float:
        self._tempos.append(time.perf_counter() if agora is None else agora)
        return self.fps

    @property
    def fps(self) -> float:
        if len(self._tempos) < 2:
            return 0.0
        duracao = self._tempos[-1] - self._tempos[0]
        return (len(self._tempos) - 1) / duracao if duracao > 0 else 0.0
