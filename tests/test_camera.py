import numpy as np
import pytest

from libras import camera as modulo_camera
from libras.camera import Camera, ErroCamera


class CapturaFalsa:
    """Substitui cv2.VideoCapture: entrega frames conforme a lista `leituras`."""

    def __init__(self, aberta=True, leituras=None):
        self.aberta = aberta
        self.leituras = list(leituras or [])

    def isOpened(self):
        return self.aberta

    def set(self, *_):
        pass

    def get(self, *_):
        return 0

    def read(self):
        ok = self.leituras.pop(0) if self.leituras else True
        frame = np.arange(12, dtype=np.uint8).reshape(2, 2, 3) if ok else None
        return ok, frame

    def release(self):
        pass


def _usar_captura(monkeypatch, captura):
    monkeypatch.setattr(modulo_camera.cv2, "VideoCapture", lambda *_: captura)


def test_camera_indisponivel(monkeypatch):
    _usar_captura(monkeypatch, CapturaFalsa(aberta=False))
    with pytest.raises(ErroCamera, match="Não foi possível abrir"):
        Camera(indice=7).abrir()


def test_camera_abre_mas_nao_envia_imagem(monkeypatch):
    _usar_captura(monkeypatch, CapturaFalsa(leituras=[False]))
    with pytest.raises(ErroCamera, match="não enviou nenhuma imagem"):
        Camera().abrir()


def test_falha_momentanea_devolve_none(monkeypatch):
    _usar_captura(monkeypatch, CapturaFalsa(leituras=[True, False, True]))
    with Camera(max_falhas=3) as camera:
        assert camera.ler() is None
        assert camera.ler() is not None


def test_falhas_seguidas_lancam_erro(monkeypatch):
    _usar_captura(monkeypatch, CapturaFalsa(leituras=[True] + [False] * 3))
    with Camera(max_falhas=3) as camera:
        assert camera.ler() is None
        assert camera.ler() is None
        with pytest.raises(ErroCamera, match="parou de enviar"):
            camera.ler()


def test_espelhamento(monkeypatch):
    _usar_captura(monkeypatch, CapturaFalsa())
    with Camera(espelhar=True) as camera:
        frame = camera.ler()
    original = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)
    assert (frame == original[:, ::-1]).all()


def test_ler_sem_abrir():
    with pytest.raises(ErroCamera, match="não foi aberta"):
        Camera().ler()
