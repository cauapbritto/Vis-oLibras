"""Um frame da câmera -> landmarks -> reconhecimento -> imagem com landmarks.

Usado pelas duas interfaces (janela OpenCV do executar.py e a interface gráfica
do app.py), para que a lógica de visão exista em um só lugar. Não abre a
câmera, não mostra nada e não conhece a frase nem a voz.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from libras.classificador import Classificador
from libras.desenho import desenhar_maos, desenhar_pose
from libras.estabilizador import Estabilizador
from libras.extrator import ExtratorLandmarks, ResultadoExtracao, para_linha_bruta
from libras.metricas import ContadorFPS
from libras.reconhecedor import EstadoReconhecimento, Reconhecedor


@dataclass
class QuadroProcessado:
    imagem: np.ndarray                 # frame BGR com mãos e ombros desenhados
    resultado: ResultadoExtracao       # mãos/pose detectadas neste frame
    estado: EstadoReconhecimento = field(default_factory=EstadoReconhecimento)
    fps: float = 0.0
    momento: float = 0.0               # time.perf_counter() do frame


class PipelineVisao:
    """Sem classificador, só detecta e desenha (útil para testar a câmera)."""

    def __init__(self, classificador: Classificador | None = None,
                 estabilizador: Estabilizador | None = None,
                 passo_inferencia: int | None = None,
                 extrator: ExtratorLandmarks | None = None) -> None:
        self.extrator = extrator or ExtratorLandmarks()
        self.reconhecedor = None
        if classificador is not None:
            argumentos = {} if passo_inferencia is None else {"passo_inferencia": passo_inferencia}
            self.reconhecedor = Reconhecedor(classificador, estabilizador, **argumentos)
        self._fps = ContadorFPS()

    def processar(self, frame: np.ndarray, agora: float | None = None) -> QuadroProcessado:
        agora = time.perf_counter() if agora is None else agora
        resultado = self.extrator.extrair(frame)
        estado = EstadoReconhecimento()
        if self.reconhecedor is not None:
            estado = self.reconhecedor.processar(para_linha_bruta(resultado, agora), agora)
        desenhar_pose(frame, resultado)
        desenhar_maos(frame, resultado)
        return QuadroProcessado(frame, resultado, estado, self._fps.atualizar(agora), agora)

    def reiniciar_estabilizador(self) -> None:
        """Esquece a última palavra aceita (e o cooldown), mas mantém a janela de
        frames - como acontece no uso normal, em que a janela nunca começa vazia."""
        if self.reconhecedor is not None:
            self.reconhecedor.estabilizador.reiniciar()

    def limpar(self) -> None:
        """Esquece a janela atual e o histórico do estabilizador."""
        if self.reconhecedor is not None:
            self.reconhecedor.limpar()

    def fechar(self) -> None:
        self.extrator.fechar()
