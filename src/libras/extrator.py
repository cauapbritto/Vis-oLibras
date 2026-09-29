"""Extração de landmarks com MediaPipe Tasks (HandLandmarker):
frame BGR -> mãos detectadas, cada uma com 21 pontos (x, y, z) e o lado.

A pose (PoseLandmarker) e a conversão para a linha de landmarks crus do
config.py serão adicionadas na Fase 2 (coleta de dados).

Uso típico:

    with ExtratorLandmarks() as extrator:
        resultado = extrator.extrair(frame)
        if resultado.tem_maos: ...
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from libras import config

# Conexões entre os 21 pontos da mão, como pares (início, fim).
CONEXOES_MAO: list[tuple[int, int]] = [
    (c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS
]

LADO_DIREITO = "Right"
LADO_ESQUERDO = "Left"
_LADO_OPOSTO = {LADO_DIREITO: LADO_ESQUERDO, LADO_ESQUERDO: LADO_DIREITO}


class ErroModelo(RuntimeError):
    """O arquivo de modelo do MediaPipe não existe e não pôde ser baixado."""


@dataclass
class Mao:
    """Uma mão detectada."""

    lado: str             # LADO_DIREITO ou LADO_ESQUERDO
    pontos: np.ndarray    # (21, 3): x, y normalizados em [0, 1] na imagem; z relativo
    confianca: float      # confiança da classificação do lado


@dataclass
class ResultadoExtracao:
    """Resultado de um frame. Nenhuma mão detectada = lista vazia (não é erro)."""

    maos: list[Mao] = field(default_factory=list)

    @property
    def tem_maos(self) -> bool:
        return bool(self.maos)

    @property
    def lados(self) -> set[str]:
        return {mao.lado for mao in self.maos}

    def mao(self, lado: str) -> Mao | None:
        """A mão do lado pedido (a de maior confiança, se houver duas iguais)."""
        candidatas = [m for m in self.maos if m.lado == lado]
        return max(candidatas, key=lambda m: m.confianca) if candidatas else None


def garantir_modelo(caminho: Path, url: str) -> Path:
    """Baixa o modelo do MediaPipe para `caminho` se ele ainda não existir."""
    if caminho.is_file():
        return caminho

    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".download")
    print(f"Baixando modelo do MediaPipe: {caminho.name} ...")
    try:
        urllib.request.urlretrieve(url, temporario)
    except (urllib.error.URLError, OSError) as erro:
        temporario.unlink(missing_ok=True)
        raise ErroModelo(
            f"Não foi possível baixar {caminho.name} ({erro}). Verifique a internet "
            f"ou baixe manualmente de:\n  {url}\ne salve em:\n  {caminho}"
        ) from erro
    temporario.replace(caminho)
    return caminho


class ExtratorLandmarks:
    """Detecta até `num_maos` mãos por frame usando o modo VIDEO do MediaPipe
    (que aproveita o rastreamento entre frames seguidos)."""

    def __init__(
        self,
        num_maos: int = config.NUM_MAOS,
        caminho_modelo: Path = config.ARQ_HAND_LANDMARKER,
    ) -> None:
        garantir_modelo(caminho_modelo, config.URL_HAND_LANDMARKER)
        opcoes = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(caminho_modelo)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_maos,
            min_hand_detection_confidence=config.CONFIANCA_DETECCAO_MAO,
            min_hand_presence_confidence=config.CONFIANCA_PRESENCA_MAO,
            min_tracking_confidence=config.CONFIANCA_RASTREAMENTO_MAO,
        )
        try:
            self._detector = vision.HandLandmarker.create_from_options(opcoes)
        except OSError as erro:
            # No Linux, o MediaPipe depende de bibliotecas gráficas do sistema.
            raise ErroModelo(
                f"O MediaPipe não conseguiu carregar uma biblioteca do sistema ({erro}). "
                "No Linux (Ubuntu/Debian), instale com: sudo apt install libegl1 libgles2"
            ) from erro
        except (RuntimeError, ValueError) as erro:
            raise ErroModelo(
                f"Falha ao carregar {caminho_modelo.name}: {erro}. Apague o arquivo "
                "para que ele seja baixado novamente."
            ) from erro
        self._ultimo_timestamp_ms = -1

    def extrair(self, frame_bgr: np.ndarray) -> ResultadoExtracao:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        imagem = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # O modo VIDEO exige timestamps estritamente crescentes.
        timestamp_ms = max(int(time.perf_counter() * 1000), self._ultimo_timestamp_ms + 1)
        self._ultimo_timestamp_ms = timestamp_ms

        bruto = self._detector.detect_for_video(imagem, timestamp_ms)

        maos = []
        for pontos, lateralidade in zip(bruto.hand_landmarks, bruto.handedness):
            categoria = lateralidade[0]
            lado = categoria.category_name
            if config.TROCAR_LADOS:
                lado = _LADO_OPOSTO.get(lado, lado)
            maos.append(Mao(
                lado=lado,
                pontos=np.array([(p.x, p.y, p.z) for p in pontos], dtype=np.float32),
                confianca=float(categoria.score),
            ))
        return ResultadoExtracao(maos=maos)

    def fechar(self) -> None:
        self._detector.close()

    def __enter__(self) -> ExtratorLandmarks:
        return self

    def __exit__(self, *_exc) -> None:
        self.fechar()
