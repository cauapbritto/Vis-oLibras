"""Extração de landmarks com MediaPipe Tasks (HandLandmarker + PoseLandmarker):
frame BGR -> mãos (21 pontos cada, com o lado) + pose (ombros e nariz).

`para_linha_bruta()` converte o resultado de um frame na linha padronizada de
landmarks crus (layout em config.py). É a MESMA função na coleta e no tempo
real; o pré-processamento (features.py) parte sempre dessa linha.

Uso típico:

    with ExtratorLandmarks() as extrator:
        resultado = extrator.extrair(frame)
        linha = para_linha_bruta(resultado, timestamp)
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


def lado_da_pessoa(lado: str) -> str:
    """Converte o rótulo gravado no lado real da pessoa (e vice-versa: a troca é
    simétrica). O MediaPipe entrega os rótulos invertidos com a imagem espelhada;
    ver config.NOMES_MAOS_INVERTIDOS. Use nos NOMES e cores mostrados, nunca nos dados."""
    return _LADO_OPOSTO.get(lado, lado) if config.NOMES_MAOS_INVERTIDOS else lado


class ErroModelo(RuntimeError):
    """O arquivo de modelo do MediaPipe não existe, não pôde ser baixado ou carregado."""


@dataclass
class Mao:
    """Uma mão detectada."""

    lado: str             # LADO_DIREITO ou LADO_ESQUERDO
    pontos: np.ndarray    # (21, 3): x, y normalizados em [0, 1] na imagem; z relativo ao punho
    confianca: float      # confiança da classificação do lado


@dataclass
class ResultadoExtracao:
    """Resultado de um frame. Nenhuma mão detectada = lista vazia (não é erro)."""

    maos: list[Mao] = field(default_factory=list)
    pose: np.ndarray | None = None  # (33, 3) ou None se os ombros não estão visíveis
    largura: int = 1                # tamanho do frame, para corrigir a proporção
    altura: int = 1

    @property
    def tem_maos(self) -> bool:
        return bool(self.maos)

    @property
    def tem_ombros(self) -> bool:
        return self.pose is not None

    @property
    def lados(self) -> set[str]:
        return set(self.maos_por_lado())

    def maos_por_lado(self) -> dict[str, Mao]:
        """No máximo uma mão por lado.

        Às vezes o MediaPipe classifica as duas mãos com o mesmo lado. Nesse caso,
        decidimos pela posição na imagem: com a imagem espelhada, a mão direita
        da pessoa aparece à direita da imagem. Ela recebe o MESMO rótulo que o
        MediaPipe daria à mão direita (lado_da_pessoa), para os dados seguirem
        sempre a mesma convenção.
        """
        if len(self.maos) == 2 and self.maos[0].lado == self.maos[1].lado:
            esq_imagem, dir_imagem = sorted(self.maos, key=lambda m: m.pontos[0, 0])
            direita, esquerda = (dir_imagem, esq_imagem) if config.ESPELHAR_IMAGEM else (esq_imagem, dir_imagem)
            return {lado_da_pessoa(LADO_DIREITO): direita, lado_da_pessoa(LADO_ESQUERDO): esquerda}

        por_lado: dict[str, Mao] = {}
        for mao in sorted(self.maos, key=lambda m: m.confianca):
            por_lado[mao.lado] = mao  # a de maior confiança fica por último
        return por_lado

    def mao(self, lado: str) -> Mao | None:
        return self.maos_por_lado().get(lado)


_origem_tempo: float | None = None


def _tempo_relativo(timestamp: float) -> float:
    """Segundos desde o primeiro frame deste processo. A linha é float32 (~7 dígitos):
    o time.perf_counter() do Windows conta desde que o computador ligou e, depois de
    alguns dias ligado (ex.: 1243918,89 s), o float32 arredonda de 0,125 em 0,125 s -
    frames seguidos ficavam com o mesmo tempo ("timestamps fora de ordem")."""
    global _origem_tempo
    if _origem_tempo is None:
        _origem_tempo = timestamp
    return timestamp - _origem_tempo


def para_linha_bruta(resultado: ResultadoExtracao, timestamp: float) -> np.ndarray:
    """Linha de landmarks crus de um frame, sempre com config.TAM_FRAME_BRUTO valores.

    [timestamp | mão direita (63) | mão esquerda (63) | flags (2) | pose (99)]
    Mão ausente = zeros com flag 0. Pose ausente = zeros. O timestamp é guardado relativo
    ao primeiro frame do processo (só as diferenças entre frames importam).
    """
    linha = np.zeros(config.TAM_FRAME_BRUTO, dtype=np.float32)
    linha[config.COL_TIMESTAMP] = _tempo_relativo(timestamp)

    # x e z em "unidades da altura da imagem" (ver config.py)
    proporcao = np.array([resultado.largura / resultado.altura, 1.0, resultado.largura / resultado.altura],
                         dtype=np.float32)
    flags = np.zeros(2, dtype=np.float32)
    maos = resultado.maos_por_lado()
    for i, (lado, colunas) in enumerate(((LADO_DIREITO, config.COL_MAO_DIREITA),
                                         (LADO_ESQUERDO, config.COL_MAO_ESQUERDA))):
        if lado in maos:
            linha[colunas] = (maos[lado].pontos * proporcao).ravel()
            flags[i] = 1.0
    linha[config.COL_FLAGS] = flags

    if resultado.pose is not None:
        linha[config.COL_POSE] = (resultado.pose * proporcao).ravel()
    return linha


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


def _criar_detector(criar, opcoes, caminho_modelo: Path):
    """Cria um detector do MediaPipe convertendo falhas em ErroModelo."""
    try:
        return criar(opcoes)
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


class ExtratorLandmarks:
    """Detecta até `num_maos` mãos e a pose por frame, usando o modo VIDEO do
    MediaPipe (que aproveita o rastreamento entre frames seguidos)."""

    def __init__(self, num_maos: int = config.NUM_MAOS, usar_pose: bool = True) -> None:
        garantir_modelo(config.ARQ_HAND_LANDMARKER, config.URL_HAND_LANDMARKER)
        opcoes_maos = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(config.ARQ_HAND_LANDMARKER)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_maos,
            min_hand_detection_confidence=config.CONFIANCA_DETECCAO_MAO,
            min_hand_presence_confidence=config.CONFIANCA_PRESENCA_MAO,
            min_tracking_confidence=config.CONFIANCA_RASTREAMENTO_MAO,
        )
        self._maos = _criar_detector(vision.HandLandmarker.create_from_options,
                                     opcoes_maos, config.ARQ_HAND_LANDMARKER)
        self._pose = None
        if usar_pose:
            try:
                garantir_modelo(config.ARQ_POSE_LANDMARKER, config.URL_POSE_LANDMARKER)
                opcoes_pose = vision.PoseLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(config.ARQ_POSE_LANDMARKER)),
                    running_mode=vision.RunningMode.VIDEO,
                    num_poses=1,
                    min_pose_detection_confidence=config.CONFIANCA_DETECCAO_POSE,
                )
                self._pose = _criar_detector(vision.PoseLandmarker.create_from_options,
                                             opcoes_pose, config.ARQ_POSE_LANDMARKER)
            except ErroModelo:
                self._maos.close()
                raise
        self._ultimo_timestamp_ms = -1
        self._ultima_pose: np.ndarray | None = None
        self._momento_ultima_pose_ms = 0
        self.leve = False           # modo leve (ver config.MODO_LEVE)
        self._quadros = 0

    def extrair(self, frame_bgr: np.ndarray) -> ResultadoExtracao:
        altura, largura = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if self.leve and config.LEVE_ESCALA < 1:
            # os pontos saem normalizados (0 a 1): reduzir a imagem não muda as coordenadas
            rgb = cv2.resize(rgb, (int(largura * config.LEVE_ESCALA), int(altura * config.LEVE_ESCALA)),
                             interpolation=cv2.INTER_AREA)
        imagem = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._quadros += 1

        # O modo VIDEO exige timestamps estritamente crescentes.
        timestamp_ms = max(int(time.perf_counter() * 1000), self._ultimo_timestamp_ms + 1)
        self._ultimo_timestamp_ms = timestamp_ms

        bruto = self._maos.detect_for_video(imagem, timestamp_ms)
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

        return ResultadoExtracao(maos=maos, pose=self._extrair_pose(imagem, timestamp_ms),
                                 largura=largura, altura=altura)

    def _extrair_pose(self, imagem: mp.Image, timestamp_ms: int) -> np.ndarray | None:
        """Pose do frame. O rastreamento do MediaPipe às vezes perde a pose por um
        frame; como os ombros quase não se movem, reaproveitamos a última pose
        detectada por até config.MAX_IDADE_POSE_S segundos."""
        if self._pose is None:
            return None
        if (self.leve and self._quadros % max(1, config.LEVE_POSE_A_CADA) and self._ultima_pose is not None
                and timestamp_ms - self._momento_ultima_pose_ms <= config.MAX_IDADE_POSE_S * 1000):
            return self._ultima_pose  # modo leve: reaproveita os ombros entre as detecções
        pose = self._detectar_pose(imagem, timestamp_ms)
        if pose is not None:
            self._ultima_pose, self._momento_ultima_pose_ms = pose, timestamp_ms
            return pose
        if (self._ultima_pose is not None
                and timestamp_ms - self._momento_ultima_pose_ms <= config.MAX_IDADE_POSE_S * 1000):
            return self._ultima_pose
        return None

    def _detectar_pose(self, imagem: mp.Image, timestamp_ms: int) -> np.ndarray | None:
        bruto = self._pose.detect_for_video(imagem, timestamp_ms)
        if not bruto.pose_landmarks:
            return None
        pontos = bruto.pose_landmarks[0]
        ombros = (pontos[config.POSE_OMBRO_ESQUERDO], pontos[config.POSE_OMBRO_DIREITO])
        if min(o.visibility or 0.0 for o in ombros) < config.MIN_VISIBILIDADE_OMBROS:
            return None  # ombros fora da imagem: posição "inventada" pelo modelo
        return np.array([(p.x, p.y, p.z) for p in pontos], dtype=np.float32)

    def fechar(self) -> None:
        self._maos.close()
        if self._pose is not None:
            self._pose.close()

    def __enter__(self) -> ExtratorLandmarks:
        return self

    def __exit__(self, *_exc) -> None:
        self.fechar()
