from libras.metricas import ContadorFPS


def test_fps_zero_com_menos_de_dois_frames():
    contador = ContadorFPS()
    assert contador.fps == 0.0
    assert contador.atualizar(agora=0.0) == 0.0


def test_fps_constante():
    contador = ContadorFPS(janela=10)
    for i in range(20):
        fps = contador.atualizar(agora=i / 30)  # 30 frames por segundo
    assert abs(fps - 30) < 1e-6
