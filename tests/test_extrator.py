"""Testes com o MediaPipe real (precisam do modelo em models/, baixado se faltar)."""

import urllib.request
from pathlib import Path

import cv2
import numpy as np
import pytest

from libras import config
from libras.extrator import ErroModelo, ExtratorLandmarks, garantir_modelo

URL_IMAGEM_MAOS = "https://storage.googleapis.com/mediapipe-tasks/hand_landmarker/woman_hands.jpg"
CACHE = Path(__file__).parent / ".cache"


@pytest.fixture(scope="module")
def extrator():
    try:
        ext = ExtratorLandmarks()
    except ErroModelo as erro:
        pytest.skip(f"MediaPipe indisponível: {erro}")
    yield ext
    ext.fechar()


@pytest.fixture(scope="module")
def imagem_duas_maos():
    caminho = CACHE / "duas_maos.jpg"
    if not caminho.is_file():
        CACHE.mkdir(exist_ok=True)
        try:
            urllib.request.urlretrieve(URL_IMAGEM_MAOS, caminho)
        except OSError as erro:
            pytest.skip(f"Sem internet para baixar a imagem de teste: {erro}")
    return cv2.imread(str(caminho))


def test_imagem_sem_maos(extrator):
    resultado = extrator.extrair(np.zeros((480, 640, 3), dtype=np.uint8))
    assert not resultado.tem_maos
    assert resultado.maos == []


def test_detecta_duas_maos(extrator, imagem_duas_maos):
    resultado = extrator.extrair(imagem_duas_maos)
    assert len(resultado.maos) == 2
    assert resultado.lados == {"Right", "Left"}
    for mao in resultado.maos:
        assert mao.pontos.shape == (config.N_PONTOS_MAO, config.N_COORDS)
        assert 0.0 <= mao.confianca <= 1.0


def test_modelo_ausente_sem_internet(tmp_path):
    with pytest.raises(ErroModelo, match="baixe manualmente"):
        garantir_modelo(tmp_path / "x.task", "http://127.0.0.1:9/inexistente.task")
    assert not (tmp_path / "x.task.download").exists()
