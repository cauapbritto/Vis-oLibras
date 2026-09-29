"""Fluxo completo do tempo real com landmarks sintéticos (sem câmera):
linhas cruas -> buffer -> features -> modelo -> estabilizador."""

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline

from libras import config
from libras.classificador import Classificador
from libras.features import BufferJanela, janela_para_vetor
from libras.reconhecedor import Reconhecedor
from sinteticos import amostra, linha, mao

POSICOES = {"SIM": (0.70, 0.75), "OI": (0.70, 0.30)}  # peito x testa
FPS = 30


@pytest.fixture(scope="module")
def classificador():
    X, y = [], []
    for i in range(20):
        for sinal, pos in POSICOES.items():
            X.append(janela_para_vetor(amostra(pos, pos, ruido=0.02, semente=i)))
            y.append(sinal)
        X.append(janela_para_vetor(np.stack([linha(t) for t in np.linspace(0, 1.5, 45)])))
        y.append(config.CLASSE_NADA)
    modelo = Pipeline([("modelo", RandomForestClassifier(n_estimators=50, random_state=0))])
    return Classificador(modelo.fit(np.stack(X), y), {})


def _stream(roteiro):
    """roteiro: [(sinal ou None, segundos)] -> linhas cruas a 30 fps."""
    t, linhas = 0.0, []
    rng = np.random.default_rng(1)
    for sinal, segundos in roteiro:
        for _ in range(int(segundos * FPS)):
            direita = None
            if sinal:
                x, y = POSICOES[sinal]
                direita = mao((x + rng.normal(0, 0.003), y + rng.normal(0, 0.003)))
            linhas.append(linha(t, direita=direita))
            t += 1 / FPS
    return linhas


def _reconhecer(classificador, roteiro):
    reconhecedor = Reconhecedor(classificador)
    aceitas = []
    for l in _stream(roteiro):
        estado = reconhecedor.processar(l, float(l[config.COL_TIMESTAMP]))
        if estado.palavra:
            aceitas.append(estado.palavra)
    return aceitas


def test_sinal_segurado_por_varios_segundos_gera_uma_palavra(classificador):
    assert _reconhecer(classificador, [(None, 0.5), ("SIM", 5.0), (None, 1.5)]) == ["SIM"]


def test_repetir_o_sinal_depois_de_abaixar_as_maos(classificador):
    roteiro = [("SIM", 2.5), (None, 1.5), ("SIM", 2.5), (None, 1.5), ("OI", 2.5)]
    assert _reconhecer(classificador, roteiro) == ["SIM", "SIM", "OI"]


def test_sem_maos_nao_gera_palavras(classificador):
    assert _reconhecer(classificador, [(None, 5.0)]) == []


def test_limpar_zera_buffer_e_estabilizador(classificador):
    reconhecedor = Reconhecedor(classificador)
    for l in _stream([("SIM", 2.0)]):
        reconhecedor.processar(l, float(l[config.COL_TIMESTAMP]))
    reconhecedor.limpar()
    assert len(reconhecedor.buffer) == 0
    assert reconhecedor.estabilizador.ultima_palavra is None


def test_sem_ombros_gera_aviso(classificador):
    reconhecedor = Reconhecedor(classificador, passo_inferencia=1)
    estado = None
    for i in range(60):
        estado = reconhecedor.processar(linha(i / FPS, direita=mao((0.7, 0.7)), ombros=None), i / FPS)
    assert estado.aviso and "Ombros" in estado.aviso
    assert estado.palavra is None


def test_buffer_mantem_so_a_janela():
    buffer = BufferJanela(duracao=1.5, duracao_minima=1.2)
    for i in range(90):  # 3 s a 30 fps
        buffer.adicionar(linha(i / FPS, direita=mao((0.7, 0.7))))
    assert buffer.duracao_atual <= 1.5 and buffer.pronta()
    assert buffer.vetor().shape == (config.TAM_FEATURES_JANELA,)
    assert buffer.pct_com_maos() == 1.0
