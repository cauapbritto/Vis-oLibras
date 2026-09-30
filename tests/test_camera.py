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
    monkeypatch.setattr(modulo_camera.time, "sleep", lambda _s: None)
    # nunca manda imagem, em nenhum modo (uma falha só é tolerada: a câmera pode estar "acordando")
    _usar_captura(monkeypatch, CapturaFalsa(leituras=[False] * 100))
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


def test_listar_cameras_so_devolve_as_que_entregam_imagem(monkeypatch):
    from libras import camera as modulo

    class CapturaFalsa:
        def __init__(self, indice, *_backend):
            self.indice = indice

        def isOpened(self):
            return self.indice in (0, 2)

        def set(self, *_):
            pass

        def read(self):
            if self.indice == 0:
                return True, np.zeros((4, 4, 3), dtype=np.uint8)
            return False, None   # a 2 abre mas não manda imagem

        def release(self):
            pass

    monkeypatch.setattr(modulo.cv2, "VideoCapture", CapturaFalsa)
    monkeypatch.setattr(modulo.time, "sleep", lambda _s: None)
    assert modulo.listar_cameras(4) == [0]


def _listrado(altura=48, largura=64):
    """Imagem com defeito de formato de cor: colunas alternando roxo e verde."""
    frame = np.zeros((altura, largura, 3), dtype=np.uint8)
    frame[:, ::2] = (200, 60, 180)
    frame[:, 1::2] = (40, 200, 60)
    return frame


def _natural(altura=48, largura=64):
    y, x = np.mgrid[0:altura, 0:largura]
    return np.dstack([(x * 3) % 256, (y * 4) % 256, ((x + y) * 2) % 256]).astype(np.uint8)


def test_imagem_listrada_e_detectada():
    assert modulo_camera.imagem_corrompida(_listrado())
    assert not modulo_camera.imagem_corrompida(_natural())
    assert not modulo_camera.imagem_corrompida(np.full((48, 64, 3), 128, dtype=np.uint8))


class _CapturaPorModo:
    """VideoCapture falso: cada backend entrega um tipo de imagem."""
    abertas = []

    def __init__(self, indice, backend=None, imagens=None):
        self.backend = backend
        self.imagens = imagens

    def isOpened(self):
        return True

    def set(self, *_):
        pass

    def read(self):
        frame = self.imagens.get(self.backend)
        return (frame is not None, frame)

    def release(self):
        pass


def _fabrica(imagens):
    def criar(indice, backend=None):
        _CapturaPorModo.abertas.append(backend)
        return _CapturaPorModo(indice, backend, imagens)
    return criar


def test_modo_com_imagem_listrada_e_trocado(monkeypatch):
    monkeypatch.setattr(modulo_camera.platform, "system", lambda: "Windows")
    monkeypatch.setattr(modulo_camera.time, "sleep", lambda _s: None)
    imagens = {modulo_camera.cv2.CAP_DSHOW: _listrado(), modulo_camera.cv2.CAP_MSMF: _natural()}
    monkeypatch.setattr(modulo_camera.cv2, "VideoCapture", _fabrica(imagens))
    camera = Camera(indice=0, modo="auto")
    camera.abrir()
    assert camera.modo_usado == "msmf" and not camera.imagem_suspeita


def test_so_imagem_com_defeito_usa_a_primeira_e_avisa(monkeypatch):
    monkeypatch.setattr(modulo_camera.platform, "system", lambda: "Windows")
    monkeypatch.setattr(modulo_camera.time, "sleep", lambda _s: None)
    imagens = {modulo_camera.cv2.CAP_DSHOW: _listrado(), modulo_camera.cv2.CAP_MSMF: _listrado()}
    monkeypatch.setattr(modulo_camera.cv2, "VideoCapture", _fabrica(imagens))
    camera = Camera(indice=0, modo="auto")
    camera.abrir()
    assert camera.modo_usado == "dshow_mjpg" and camera.imagem_suspeita


def test_listar_cameras_espera_a_camera_acordar(monkeypatch):
    monkeypatch.setattr(modulo_camera.time, "sleep", lambda _s: None)
    leituras = {0: [False, False, True]}

    class Preguicosa(_CapturaPorModo):
        def __init__(self, indice, *_):
            self.indice = indice

        def isOpened(self):
            return self.indice == 0

        def read(self):
            ok = leituras[0].pop(0) if leituras[0] else True
            return ok, (_natural() if ok else None)

    monkeypatch.setattr(modulo_camera.cv2, "VideoCapture", Preguicosa)
    assert modulo_camera.listar_cameras(3) == [0]
