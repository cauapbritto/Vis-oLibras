import numpy as np

from libras import config, desenho
from libras.desenho import descrever_maos, desenhar_maos, desenhar_painel, sem_acentos
from libras.extrator import LADO_DIREITO, LADO_ESQUERDO, Mao, ResultadoExtracao


def _mao(lado):
    return Mao(lado=lado, pontos=np.full((21, 3), 0.5, dtype=np.float32), confianca=0.9)


def test_descrever_maos(monkeypatch):
    monkeypatch.setattr(config, "NOMES_MAOS_INVERTIDOS", False)
    assert descrever_maos(ResultadoExtracao()) == "Nenhuma mão detectada"
    assert descrever_maos(ResultadoExtracao([_mao(LADO_DIREITO)])) == "Mão direita"
    assert descrever_maos(ResultadoExtracao([_mao(LADO_ESQUERDO)])) == "Mão esquerda"
    # o MediaPipe entrega a mão direita da pessoa como "Left": a tela corrige o nome
    monkeypatch.setattr(config, "NOMES_MAOS_INVERTIDOS", True)
    assert descrever_maos(ResultadoExtracao([_mao(LADO_ESQUERDO)])) == "Mão direita"
    assert descrever_maos(ResultadoExtracao([_mao(LADO_DIREITO)])) == "Mão esquerda"
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


def test_icone_mao_com_e_sem_fundo():
    com_fundo = desenho.icone_mao(64, "#ffffff", "#256abf")
    assert com_fundo.size == (64, 64) and com_fundo.mode == "RGBA"
    assert com_fundo.getpixel((0, 0))[3] == 0            # canto arredondado: transparente
    assert com_fundo.getpixel((4, 32))[:3] == (0x25, 0x6a, 0xbf)  # fundo azul na borda
    assert com_fundo.getpixel((32, 50))[:3] == (255, 255, 255)    # palma branca
    sem_fundo = desenho.icone_mao(32, "#808080")
    assert sem_fundo.getpixel((2, 2))[3] == 0 and sem_fundo.getpixel((16, 25))[3] > 240  # mão opaca


def test_fonte_negrito_com_acentos():
    assert desenho.fonte_com_acentos(20, negrito=True) is not None


def test_icones_do_aplicativo_existem():
    from PIL import Image
    from libras import config
    assert Image.open(config.ARQ_ICONE_PNG).size == (256, 256)
    tamanhos = Image.open(config.ARQ_ICONE_ICO).info["sizes"]
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(tamanhos)
