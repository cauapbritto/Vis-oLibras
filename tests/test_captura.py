"""Thread da câmera: quadros, eventos e parada, com câmera e pipeline falsos."""

import time

import numpy as np

from libras import camera as modulo_camera
from libras import captura
from libras.captura import ProcessadorCamera
from libras.extrator import ResultadoExtracao
from libras.pipeline import QuadroProcessado
from libras.reconhecedor import EstadoReconhecimento


class CapturaFalsa:
    def __init__(self, aberta=True):
        self.aberta = aberta

    def isOpened(self):
        return self.aberta

    def set(self, *_):
        pass

    def get(self, *_):
        return 0

    def read(self):
        time.sleep(0.005)
        return True, np.zeros((48, 64, 3), dtype=np.uint8)

    def release(self):
        pass


class PipelineFalso:
    """A cada 10 frames confirma uma palavra."""

    limpezas = 0

    def __init__(self, *_args, **_kw):
        self.n = 0

    def processar(self, frame, agora=None):
        self.n += 1
        estado = EstadoReconhecimento("OI", 0.9, "OI" if self.n % 10 == 0 else None)
        return QuadroProcessado(frame, ResultadoExtracao(), estado, 30.0, time.perf_counter())

    def limpar(self):
        PipelineFalso.limpezas += 1

    def fechar(self):
        pass


def _coletar(processador, segundos):
    eventos, quadros = [], 0
    fim = time.time() + segundos
    while time.time() < fim:
        eventos += list(processador.eventos())
        quadros += processador.ultimo_quadro() is not None
        time.sleep(0.01)
    return eventos, quadros


def test_quadros_palavras_e_parada(monkeypatch):
    monkeypatch.setattr(modulo_camera.cv2, "VideoCapture", lambda *_: CapturaFalsa())
    monkeypatch.setattr(captura, "PipelineVisao", PipelineFalso)
    processador = ProcessadorCamera()
    processador.start()
    eventos, quadros = _coletar(processador, 0.6)
    processador.pedir_limpeza()
    time.sleep(0.05)
    processador.parar()
    processador.join(timeout=2)
    eventos += list(processador.eventos())

    assert not processador.is_alive()
    assert ("status", "ok") in eventos
    palavras = [dado for tipo, dado in eventos if tipo == "palavra"]
    assert palavras and all(p[0] == "OI" for p in palavras)   # nenhuma palavra perdida
    assert quadros > 0
    assert eventos[-1] == ("parado", None)
    assert PipelineFalso.limpezas >= 1


def test_camera_indisponivel_gera_erro_e_para(monkeypatch):
    monkeypatch.setattr(modulo_camera.cv2, "VideoCapture", lambda *_: CapturaFalsa(aberta=False))
    processador = ProcessadorCamera()
    processador.start()
    processador.join(timeout=2)
    eventos = list(processador.eventos())
    assert any(tipo == "erro" and "câmera" in dado for tipo, dado in eventos)
    assert eventos[-1] == ("parado", None)
