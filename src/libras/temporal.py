"""Camada temporal: a sequência recente de landmarks e o movimento dentro dela.

1. `SequenciaTemporal` guarda as linhas cruas dos últimos segundos (janela
   deslizante por TEMPO, e não por número de frames, para funcionar igual em
   câmeras de 15 ou 30 fps). Opcionalmente limita também o número de frames.

2. `caracteristicas_movimento()` resume COMO as mãos se moveram na janela, a
   partir da sequência já normalizada (T x config.TAM_FEATURES_FRAME):

   por mão
     - velocidade do punho entre frames seguidos     -> direção e ritmo
     - deslocamento total (fim - início)             -> "sobe" x "desce"
     - comprimento da trajetória                     -> parado x em movimento
     - amplitude em x e em y                         -> tamanho do movimento
     - mudanças de direção em x e em y               -> aceno / vai-e-vem
     - abertura da mão em cada frame e sua variação  -> abrir / fechar a mão
   entre as mãos
     - distância entre os punhos em cada frame       -> aproximar / afastar

   Tudo em unidades normalizadas (larguras de ombro e tamanhos de palma), então
   continua valendo a invariância à posição, à distância e ao tamanho da mão.
   Num sinal estático, velocidades, trajetória e mudanças de direção ficam
   perto de zero - o que também ajuda o modelo a reconhecê-lo.
"""

from __future__ import annotations

import numpy as np

from libras import config

# Posição das partes de cada mão no vetor normalizado de um frame
_BLOCO = config.TAM_FORMA_MAO + config.TAM_POSICAO_MAO
_MAOS = tuple(
    (slice(i * _BLOCO, i * _BLOCO + config.TAM_FORMA_MAO),                 # forma
     slice(i * _BLOCO + config.TAM_FORMA_MAO, (i + 1) * _BLOCO),           # posição
     2 * _BLOCO + i)                                                       # flag
    for i in range(2)  # direita, esquerda
)


class SequenciaTemporal:
    """Linhas cruas dos últimos `duracao` segundos (e, se dado, no máximo `max_frames`)."""

    def __init__(self, duracao: float = config.DURACAO_JANELA,
                 duracao_minima: float = config.DURACAO_MINIMA_JANELA,
                 max_frames: int | None = None) -> None:
        self.duracao = duracao
        self.duracao_minima = duracao_minima
        self.max_frames = max_frames
        self._linhas: list[np.ndarray] = []

    def adicionar(self, linha: np.ndarray) -> None:
        self._linhas.append(linha)
        limite = linha[config.COL_TIMESTAMP] - self.duracao
        while self._linhas and self._linhas[0][config.COL_TIMESTAMP] < limite:
            self._linhas.pop(0)
        if self.max_frames is not None:
            del self._linhas[:-self.max_frames]

    def limpar(self) -> None:
        self._linhas.clear()

    def __len__(self) -> int:
        return len(self._linhas)

    @property
    def duracao_atual(self) -> float:
        if len(self._linhas) < 2:
            return 0.0
        return float(self._linhas[-1][config.COL_TIMESTAMP] - self._linhas[0][config.COL_TIMESTAMP])

    def pronta(self) -> bool:
        """Já tem tempo suficiente para classificar?"""
        return self.duracao_atual >= self.duracao_minima

    def pct_com_maos(self) -> float:
        if not self._linhas:
            return 0.0
        flags = np.stack([l[config.COL_FLAGS] for l in self._linhas])
        return float((flags.max(axis=1) > 0.5).mean())

    def como_array(self) -> np.ndarray:
        """(F, config.TAM_FRAME_BRUTO) com timestamps relativos ao primeiro frame,
        no mesmo formato de uma amostra gravada pelo coletor."""
        frames = np.stack(self._linhas)
        frames[:, config.COL_TIMESTAMP] -= frames[0, config.COL_TIMESTAMP]
        return frames


def _suavizar(pos: np.ndarray) -> np.ndarray:
    """Média móvel de 3 frames (reduz o tremor da detecção antes de medir direção)."""
    if len(pos) < 3:
        return pos
    preenchido = np.concatenate([pos[:1], pos, pos[-1:]])
    return (preenchido[:-2] + preenchido[1:-1] + preenchido[2:]) / 3


def _mudancas_de_direcao(velocidades: np.ndarray) -> np.ndarray:
    """Quantas vezes o movimento inverte o sentido, em x e em y (ignora tremores)."""
    mudancas = np.zeros(2, dtype=np.float32)
    for eixo in range(2):
        v = velocidades[:, eixo]
        sinais = np.sign(v[np.abs(v) >= config.LIMIAR_MOVIMENTO])
        mudancas[eixo] = np.count_nonzero(sinais[1:] != sinais[:-1])
    return mudancas


def _movimento_mao(forma: np.ndarray, pos: np.ndarray, presente: np.ndarray) -> np.ndarray:
    t_frames = len(pos)
    velocidades = np.zeros((t_frames - 1, 2), dtype=np.float32)
    ambos = presente[1:] & presente[:-1]
    velocidades[ambos] = np.diff(pos, axis=0)[ambos]

    abertura = np.zeros(t_frames, dtype=np.float32)
    pontas = forma.reshape(t_frames, config.N_PONTOS_MAO, config.N_COORDS)[:, config.PONTAS_DEDOS]
    abertura[presente] = np.linalg.norm(pontas[presente], axis=2).mean(axis=1)

    indices = np.flatnonzero(presente)
    if len(indices) >= 2:
        uteis = pos[indices]
        deslocamento = uteis[-1] - uteis[0]
        amplitude = uteis.max(axis=0) - uteis.min(axis=0)
        mudancas = _mudancas_de_direcao(np.diff(_suavizar(uteis), axis=0))
        variacao_abertura = abertura[indices[-1]] - abertura[indices[0]]
    else:
        deslocamento = amplitude = mudancas = np.zeros(2, dtype=np.float32)
        variacao_abertura = 0.0
    comprimento = np.linalg.norm(velocidades, axis=1).sum()

    return np.concatenate([velocidades.ravel(), deslocamento, [comprimento], amplitude,
                           mudancas, abertura, [variacao_abertura]]).astype(np.float32)


def caracteristicas_movimento(sequencia: np.ndarray) -> np.ndarray:
    """(T, config.TAM_FEATURES_FRAME) normalizada -> config.TAM_MOVIMENTO valores."""
    partes, posicoes, presencas = [], [], []
    for forma_cols, pos_cols, col_flag in _MAOS:
        presente = sequencia[:, col_flag] > 0.5
        pos = sequencia[:, pos_cols]
        partes.append(_movimento_mao(sequencia[:, forma_cols], pos, presente))
        posicoes.append(pos)
        presencas.append(presente)

    distancia = np.zeros(len(sequencia), dtype=np.float32)
    juntas = presencas[0] & presencas[1]
    distancia[juntas] = np.linalg.norm(posicoes[0][juntas] - posicoes[1][juntas], axis=1)
    partes.append(distancia)
    return np.concatenate(partes)
