import numpy as np

from libras.desenho import descrever_maos, desenhar_maos, desenhar_painel, sem_acentos
from libras.extrator import LADO_DIREITO, LADO_ESQUERDO, Mao, ResultadoExtracao


def _mao(lado):
    return Mao(lado=lado, pontos=np.full((21, 3), 0.5, dtype=np.float32), confianca=0.9)


def test_descrever_maos():
    assert descrever_maos(ResultadoExtracao()) == "Nenhuma mão detectada"
    assert descrever_maos(ResultadoExtracao([_mao(LADO_DIREITO)])) == "Mão direita"
    assert descrever_maos(ResultadoExtracao([_mao(LADO_ESQUERDO)])) == "Mão esquerda"
    ambas = ResultadoExtracao([_mao(LADO_DIREITO), _mao(LADO_ESQUERDO)])
    assert descrever_maos(ambas) == "Ambas as mãos"


def test_sem_acentos():
    assert sem_acentos("Não, mão, câmera, é") == "Nao, mao, camera, e"


def test_desenho_altera_frame_sem_erro():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    desenhar_maos(frame, ResultadoExtracao([_mao(LADO_DIREITO)]))
    desenhar_painel(frame, [("FPS: 30.0", (255, 255, 255))])
    assert frame.any()


def test_painel_maior_que_o_frame_nao_quebra():
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    desenhar_painel(frame, [("texto bem comprido " * 5, (255, 255, 255))] * 5)
