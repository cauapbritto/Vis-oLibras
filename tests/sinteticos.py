"""Geradores de landmarks sintéticos para os testes (sem câmera nem MediaPipe)."""

import numpy as np

from libras import config

# Mão "aberta" em unidades de palma: punho na origem, base do dedo médio a 1 unidade acima.
_angulos = np.linspace(-0.6, 0.6, 5)
MAO_BASE = np.zeros((21, 3), dtype=np.float32)
for dedo, ang in enumerate(_angulos):
    for junta in range(4):
        r = 1.0 + 0.35 * junta
        MAO_BASE[1 + dedo * 4 + junta] = (np.sin(ang) * r, -np.cos(ang) * r, -0.02 * junta)
MAO_BASE -= MAO_BASE[0]
MAO_BASE /= np.linalg.norm(MAO_BASE[config.MAO_BASE_DEDO_MEDIO])

OMBRO_E, OMBRO_D = (0.85, 0.60), (0.55, 0.60)  # imagem espelhada: ombro esquerdo à direita
NARIZ = (0.70, 0.40)


def mao(punho: tuple[float, float], tamanho: float = 0.08, forma: np.ndarray = MAO_BASE) -> np.ndarray:
    """(21, 3) em unidades da altura da imagem."""
    return forma * tamanho + np.array([punho[0], punho[1], 0.0], dtype=np.float32)


def linha(t: float, direita=None, esquerda=None, ombros=(OMBRO_E, OMBRO_D), nariz=NARIZ) -> np.ndarray:
    """Linha crua (config.TAM_FRAME_BRUTO) de um frame."""
    l = np.zeros(config.TAM_FRAME_BRUTO, dtype=np.float32)
    l[config.COL_TIMESTAMP] = t
    for i, (pts, col) in enumerate(((direita, config.COL_MAO_DIREITA), (esquerda, config.COL_MAO_ESQUERDA))):
        if pts is not None:
            l[col] = np.asarray(pts, dtype=np.float32).ravel()
            l[config.COL_FLAGS.start + i] = 1.0
    if ombros is not None:
        pose = np.zeros((config.N_PONTOS_POSE, 3), dtype=np.float32)
        pose[config.POSE_OMBRO_ESQUERDO, :2] = ombros[0]
        pose[config.POSE_OMBRO_DIREITO, :2] = ombros[1]
        pose[config.POSE_NARIZ, :2] = nariz
        l[config.COL_POSE] = pose.ravel()
    return l


def amostra(inicio=(0.60, 0.70), fim=(0.60, 0.45), n_frames=45, duracao=1.5,
            esquerda=False, tamanho=0.08, ruido=0.0, semente=0) -> np.ndarray:
    """Amostra (F, 228): a mão direita vai de `inicio` a `fim` (e a esquerda espelhada)."""
    rng = np.random.default_rng(semente)
    frames = []
    for k, t in enumerate(np.linspace(0, duracao, n_frames)):
        a = k / (n_frames - 1)
        punho = (inicio[0] + a * (fim[0] - inicio[0]), inicio[1] + a * (fim[1] - inicio[1]))
        forma = MAO_BASE + rng.normal(0, ruido, MAO_BASE.shape).astype(np.float32)
        d = mao(punho, tamanho, forma)
        e = mao((1.40 - punho[0], punho[1]), tamanho, forma) if esquerda else None
        frames.append(linha(t, direita=d, esquerda=e))
    return np.stack(frames)


def transformar(frames: np.ndarray, deslocamento=(0.0, 0.0), escala=1.0) -> np.ndarray:
    """Simula a pessoa em outro lugar da imagem / a outra distância da câmera:
    aplica escala e deslocamento em todos os pontos (mãos e pose) presentes."""
    frames = frames.copy()
    desl = np.array([*deslocamento, 0.0], dtype=np.float32)
    for col in (config.COL_MAO_DIREITA, config.COL_MAO_ESQUERDA, config.COL_POSE):
        pts = frames[:, col].reshape(len(frames), -1, 3)
        presente = np.abs(pts).sum(axis=2, keepdims=True) > 0
        frames[:, col] = np.where(presente, pts * escala + desl, 0).reshape(len(frames), -1)
    return frames
