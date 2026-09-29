"""Testes com o MediaPipe real (precisam do modelo em models/, baixado se faltar)."""

import urllib.request
from pathlib import Path

import cv2
import numpy as np
import pytest

from libras import config
from libras.extrator import (ErroModelo, ExtratorLandmarks, Mao, ResultadoExtracao, garantir_modelo,
                            para_linha_bruta)

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


def _mao_falsa(lado, x_punho, confianca=0.9):
    pontos = np.full((21, 3), 0.5, dtype=np.float32)
    pontos[:, 0] = x_punho
    return Mao(lado=lado, pontos=pontos, confianca=confianca)


def test_duas_maos_com_o_mesmo_lado_sao_separadas_pela_posicao():
    resultado = ResultadoExtracao([_mao_falsa("Right", 0.3), _mao_falsa("Right", 0.7)])
    por_lado = resultado.maos_por_lado()
    # imagem espelhada: a mão direita da pessoa aparece à direita da imagem
    assert por_lado["Right"].pontos[0, 0] == pytest.approx(0.7)
    assert por_lado["Left"].pontos[0, 0] == pytest.approx(0.3)


def test_linha_bruta_tem_layout_fixo():
    resultado = ResultadoExtracao([_mao_falsa("Left", 0.4)], pose=None, largura=640, altura=480)
    l = para_linha_bruta(resultado, 1.25)
    assert l.shape == (config.TAM_FRAME_BRUTO,)
    assert l[config.COL_TIMESTAMP] == pytest.approx(1.25)
    assert not l[config.COL_MAO_DIREITA].any()
    assert list(l[config.COL_FLAGS]) == [0.0, 1.0]
    esquerda = l[config.COL_MAO_ESQUERDA].reshape(21, 3)
    assert esquerda[0, 0] == pytest.approx(0.4 * 640 / 480)  # x corrigido pela proporção
    assert esquerda[0, 1] == pytest.approx(0.5)              # y inalterado
    assert not l[config.COL_POSE].any()


def test_extrai_pose_da_imagem_real(extrator, imagem_duas_maos):
    resultado = extrator.extrair(imagem_duas_maos)
    assert resultado.tem_ombros
    linha = para_linha_bruta(resultado, 0.0)
    assert linha[config.COL_POSE].any()
    assert list(linha[config.COL_FLAGS]) == [1.0, 1.0]
