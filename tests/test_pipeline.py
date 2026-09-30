"""Modo leve automático do pipeline (sem câmera nem MediaPipe)."""

import numpy as np

from libras import config
from libras.extrator import ResultadoExtracao
from libras.pipeline import PipelineVisao


class _ExtratorFalso:
    leve = False

    def extrair(self, frame):
        return ResultadoExtracao(largura=frame.shape[1], altura=frame.shape[0])

    def fechar(self):
        pass


def _rodar(pipeline, fps, segundos, inicio=100.0):
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    quadro = None
    for i in range(int(fps * segundos)):
        quadro = pipeline.processar(frame, agora=inicio + i / fps)
    return quadro


def test_fps_baixo_por_tempo_seguido_liga_o_modo_leve(monkeypatch):
    monkeypatch.setattr(config, "MODO_LEVE", "auto")
    pipeline = PipelineVisao(extrator=_ExtratorFalso())
    assert not _rodar(pipeline, fps=10, segundos=2).leve          # ainda não deu o tempo
    assert _rodar(pipeline, fps=10, segundos=3, inicio=102.0).leve  # 10 fps por mais de 3 s


def test_fps_bom_ou_modo_desligado_nao_liga(monkeypatch):
    monkeypatch.setattr(config, "MODO_LEVE", "auto")
    assert not _rodar(PipelineVisao(extrator=_ExtratorFalso()), fps=30, segundos=6).leve
    monkeypatch.setattr(config, "MODO_LEVE", "desligado")
    assert not _rodar(PipelineVisao(extrator=_ExtratorFalso()), fps=10, segundos=6).leve
    monkeypatch.setattr(config, "MODO_LEVE", "ligado")
    assert _rodar(PipelineVisao(extrator=_ExtratorFalso()), fps=30, segundos=1).leve
