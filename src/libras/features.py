"""Pré-processamento: landmarks crus -> vetor de características de tamanho fixo.

A MESMA função `janela_para_vetor()` é usada na análise do dataset, no treino e
no reconhecimento em tempo real. Mudou algo aqui? Incremente
config.VERSAO_FEATURES e retreine o modelo.

Normalização (para cada mão presente em cada frame):

1. **Forma** (63 valores): pontos relativos ao punho, divididos pelo tamanho da
   palma (punho -> base do dedo médio). Não depende de onde a mão está na
   imagem, da distância até a câmera nem do tamanho da mão da pessoa.
2. **Posição** (2 valores): punho relativo ao centro dos ombros, dividido pela
   largura dos ombros. Não é a posição na câmera, e sim *onde o sinal é feito
   em relação ao corpo* (peito, boca, testa), que em Libras faz parte do sinal
   (ex.: EU x MEU). Não depende de onde a pessoa está na imagem nem da distância.

Mão ausente = zeros com flag 0 (o vetor tem sempre o mesmo tamanho).
"""

from __future__ import annotations

import numpy as np

from libras import config

_COL_FLAG = {  # coluna da flag de presença de cada mão na linha crua
    "direita": config.COL_FLAGS.start,
    "esquerda": config.COL_FLAGS.start + 1,
}
_MAOS = (("direita", config.COL_MAO_DIREITA), ("esquerda", config.COL_MAO_ESQUERDA))


class ErroJanela(ValueError):
    """A janela não pode ser convertida em vetor (ex.: ombros nunca visíveis)."""


# -----------------------------------------------------------------------------
# Um frame
# -----------------------------------------------------------------------------

def referencia_corpo(linha: np.ndarray) -> tuple[np.ndarray, float] | None:
    """(centro dos ombros (x, y), largura dos ombros) ou None se a pose não está visível."""
    pose = linha[config.COL_POSE].reshape(config.N_PONTOS_POSE, config.N_COORDS)
    if not pose.any():
        return None
    ombro_e = pose[config.POSE_OMBRO_ESQUERDO, :2]
    ombro_d = pose[config.POSE_OMBRO_DIREITO, :2]
    largura = float(np.linalg.norm(ombro_e - ombro_d))
    if largura < config.MIN_LARGURA_OMBROS:
        return None
    return (ombro_e + ombro_d) / 2, largura


def forma_mao(pontos: np.ndarray) -> np.ndarray:
    """(21, 3) -> 63 valores: relativos ao punho e divididos pelo tamanho da palma."""
    relativos = pontos - pontos[config.MAO_PUNHO]
    tamanho = float(np.linalg.norm(relativos[config.MAO_BASE_DEDO_MEDIO]))
    if tamanho < config.MIN_TAMANHO_PALMA:
        return np.zeros(config.TAM_FORMA_MAO, dtype=np.float32)
    return (relativos / tamanho).ravel().astype(np.float32)


def posicao_mao(pontos: np.ndarray, centro: np.ndarray, largura_ombros: float) -> np.ndarray:
    """Punho relativo ao centro dos ombros, em larguras de ombro (2 valores)."""
    return ((pontos[config.MAO_PUNHO, :2] - centro) / largura_ombros).astype(np.float32)


def normalizar_frame(linha: np.ndarray, referencia: tuple[np.ndarray, float]) -> np.ndarray:
    """Linha crua + referência do corpo -> config.TAM_FEATURES_FRAME valores."""
    centro, largura = referencia
    partes = []
    for nome, colunas in _MAOS:
        if linha[_COL_FLAG[nome]] > 0.5:
            pontos = linha[colunas].reshape(config.N_PONTOS_MAO, config.N_COORDS)
            partes += [forma_mao(pontos), posicao_mao(pontos, centro, largura)]
        else:
            partes += [np.zeros(config.TAM_FORMA_MAO, np.float32),
                       np.zeros(config.TAM_POSICAO_MAO, np.float32)]
    partes.append(linha[config.COL_FLAGS].astype(np.float32))
    return np.concatenate(partes)


# -----------------------------------------------------------------------------
# Uma janela (amostra gravada ou buffer do tempo real)
# -----------------------------------------------------------------------------

def preencher_lacunas_maos(frames: np.ndarray, max_lacuna: int = config.MAX_LACUNA_MAO) -> np.ndarray:
    """Interpola falhas curtas de detecção (a mão "some" por 1 a `max_lacuna` frames
    entre dois frames em que aparece). Lacunas maiores continuam como ausência."""
    frames = frames.copy()
    tempos = frames[:, config.COL_TIMESTAMP]
    for nome, colunas in _MAOS:
        col_flag = _COL_FLAG[nome]
        presentes = np.flatnonzero(frames[:, col_flag] > 0.5)
        for a, b in zip(presentes[:-1], presentes[1:]):
            if not 0 < b - a - 1 <= max_lacuna:
                continue
            duracao = tempos[b] - tempos[a]
            for k in range(a + 1, b):
                peso = (tempos[k] - tempos[a]) / duracao if duracao > 0 else 0.5
                frames[k, colunas] = (1 - peso) * frames[a, colunas] + peso * frames[b, colunas]
                frames[k, col_flag] = 1.0
    return frames


def indices_reamostragem(tempos: np.ndarray, t_frames: int = config.T_FRAMES) -> np.ndarray:
    """Índices de `t_frames` frames igualmente espaçados no tempo (o mais próximo de
    cada instante). Torna o vetor independente do FPS da câmera."""
    alvos = np.linspace(tempos[0], tempos[-1], t_frames)
    return np.abs(tempos[None, :] - alvos[:, None]).argmin(axis=1)


def janela_para_vetor(frames: np.ndarray) -> np.ndarray:
    """(F, config.TAM_FRAME_BRUTO) landmarks crus -> config.TAM_FEATURES_JANELA valores.

    Lança ErroJanela se a janela não tem frames suficientes ou se os ombros não
    aparecem em nenhum frame.
    """
    frames = np.asarray(frames, dtype=np.float32)
    if frames.ndim != 2 or frames.shape[1] != config.TAM_FRAME_BRUTO:
        raise ErroJanela(f"formato inválido {frames.shape}; esperado (F, {config.TAM_FRAME_BRUTO})")
    if len(frames) < 2:
        raise ErroJanela("a janela precisa de pelo menos 2 frames")

    referencias = [referencia_corpo(linha) for linha in frames]
    if all(ref is None for ref in referencias):
        raise ErroJanela("ombros não visíveis em nenhum frame")
    # Frames sem pose usam a referência do frame mais próximo que tem.
    validos = [i for i, ref in enumerate(referencias) if ref is not None]
    for i, ref in enumerate(referencias):
        if ref is None:
            referencias[i] = referencias[min(validos, key=lambda v: abs(v - i))]

    frames = preencher_lacunas_maos(frames)
    indices = indices_reamostragem(frames[:, config.COL_TIMESTAMP])
    vetor = np.concatenate([normalizar_frame(frames[i], referencias[i]) for i in indices])
    if not np.isfinite(vetor).all():
        raise ErroJanela("o vetor contém valores inválidos (NaN/infinito)")
    return vetor
