"""Camada temporal: sequência recente de landmarks e características de movimento."""

import numpy as np
import pytest

from libras import config
from libras.features import janela_para_vetor, sequencia_normalizada
from libras.temporal import SequenciaTemporal, caracteristicas_movimento
from sinteticos import MAO_BASE, aceno, amostra, linha, mao, transformar

N = config.T_FRAMES
# Posições das partes no vetor de movimento de uma mão (ver temporal.py)
VEL = slice(0, 2 * (N - 1))
DESLOC = slice(2 * (N - 1), 2 * (N - 1) + 2)
COMPRIMENTO = 2 * (N - 1) + 2
AMPLITUDE = slice(COMPRIMENTO + 1, COMPRIMENTO + 3)
MUDANCAS = slice(COMPRIMENTO + 3, COMPRIMENTO + 5)
ABERTURA = slice(COMPRIMENTO + 5, COMPRIMENTO + 5 + N)
VAR_ABERTURA = COMPRIMENTO + 5 + N


def _movimento(frames):
    return caracteristicas_movimento(sequencia_normalizada(frames))


def _direita(mov):
    return mov[:config.TAM_MOVIMENTO_MAO]


def _aceno(ciclos=2):
    return aceno(ciclos=ciclos)


def test_tamanho():
    assert _movimento(amostra()).shape == (config.TAM_MOVIMENTO,)


def test_sinal_parado_tem_movimento_zero():
    d = _direita(_movimento(amostra((0.7, 0.6), (0.7, 0.6))))
    assert np.allclose(d[VEL], 0) and d[COMPRIMENTO] == pytest.approx(0)
    assert np.allclose(d[DESLOC], 0) and np.allclose(d[MUDANCAS], 0)


def test_sobe_e_desce_tem_deslocamentos_opostos():
    sobe = _direita(_movimento(amostra((0.7, 0.75), (0.7, 0.45))))
    desce = _direita(_movimento(amostra((0.7, 0.45), (0.7, 0.75))))
    assert sobe[DESLOC][1] < -0.5 and desce[DESLOC][1] > 0.5  # y cresce para baixo
    assert sobe[COMPRIMENTO] == pytest.approx(desce[COMPRIMENTO], rel=1e-3)


def test_aceno_tem_mudancas_de_direcao_em_x():
    d = _direita(_movimento(_aceno(ciclos=2)))
    assert d[MUDANCAS][0] >= 3          # vai-volta-vai-volta
    assert d[MUDANCAS][1] == 0          # nada em y
    assert d[AMPLITUDE][0] > 0.2


def test_tremor_pequeno_nao_conta_como_mudanca_de_direcao():
    rng = np.random.default_rng(0)
    frames = np.stack([linha(t, direita=mao((0.7 + rng.normal(0, 0.001), 0.6)))
                       for t in np.linspace(0, 1.5, 45)])
    assert np.allclose(_direita(_movimento(frames))[MUDANCAS], 0)


def test_abrir_a_mao_aparece_na_abertura():
    fechada = MAO_BASE * np.array([0.4, 0.4, 1.0], dtype=np.float32)
    fechada[config.MAO_BASE_DEDO_MEDIO] = MAO_BASE[config.MAO_BASE_DEDO_MEDIO]
    frames = []
    for k, t in enumerate(np.linspace(0, 1.5, 45)):
        a = k / 44
        frames.append(linha(t, direita=mao((0.7, 0.6), forma=(1 - a) * fechada + a * MAO_BASE)))
    d = _direita(_movimento(np.stack(frames)))
    assert d[VAR_ABERTURA] > 0.2
    assert d[ABERTURA][-1] > d[ABERTURA][0]


def test_distancia_entre_as_maos():
    mov = _movimento(amostra(esquerda=True))
    distancia = mov[-N:]
    assert (distancia > 0).all()
    assert not _movimento(amostra(esquerda=False))[-N:].any()


def test_movimento_invariante_a_posicao_e_distancia():
    base = _aceno()
    np.testing.assert_allclose(_movimento(base), _movimento(transformar(base, (-0.2, 0.1), 0.6)), atol=1e-4)


def test_mao_ausente_nao_gera_movimento_falso():
    frames = amostra()
    frames[10:25, config.COL_MAO_DIREITA] = 0  # lacuna longa: não é interpolada
    frames[10:25, config.COL_FLAGS.start] = 0
    d = _direita(_movimento(frames))
    assert np.isfinite(d).all()
    assert d[COMPRIMENTO] < 1.0  # sem "saltos" para a origem


def test_sequencia_temporal_por_tempo_e_por_frames():
    seq = SequenciaTemporal(duracao=1.0, duracao_minima=0.5, max_frames=10)
    for i in range(60):
        seq.adicionar(linha(i / 30, direita=mao((0.7, 0.6))))
    assert len(seq) == 10                       # limite de frames
    seq = SequenciaTemporal(duracao=1.0, duracao_minima=0.5)
    for i in range(60):
        seq.adicionar(linha(i / 30, direita=mao((0.7, 0.6))))
    assert seq.duracao_atual <= 1.0 and seq.pronta()
    array = seq.como_array()
    assert array[0, config.COL_TIMESTAMP] == 0.0
    assert janela_para_vetor(array).shape == (config.TAM_FEATURES_JANELA,)
