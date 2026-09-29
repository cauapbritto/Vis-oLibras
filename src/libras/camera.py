"""Captura de vídeo com OpenCV: abrir a webcam, ler e espelhar frames, liberar a câmera.

Uso típico:

    with Camera() as camera:
        while True:
            frame = camera.ler()
            if frame is None:
                continue  # falha momentânea: tenta o próximo frame
            ...
"""

from __future__ import annotations

import cv2
import numpy as np

from libras import config


class ErroCamera(RuntimeError):
    """A webcam não pôde ser aberta ou parou de enviar imagens."""


class Camera:
    """Webcam com tratamento de erros.

    - `abrir()` lança `ErroCamera` se a câmera não existir ou estiver em uso.
    - `ler()` devolve `None` em uma falha momentânea de leitura e lança
      `ErroCamera` se as falhas se repetirem (câmera desconectada).
    """

    def __init__(
        self,
        indice: int = config.INDICE_CAMERA,
        largura: int = config.LARGURA_CAMERA,
        altura: int = config.ALTURA_CAMERA,
        espelhar: bool = config.ESPELHAR_IMAGEM,
        max_falhas: int = config.MAX_FALHAS_LEITURA,
    ) -> None:
        self.indice = indice
        self.largura = largura
        self.altura = altura
        self.espelhar = espelhar
        self.max_falhas = max_falhas
        self._captura: cv2.VideoCapture | None = None
        self._falhas_seguidas = 0

    def abrir(self) -> None:
        captura = cv2.VideoCapture(self.indice)
        if not captura.isOpened():
            captura.release()
            raise ErroCamera(
                f"Não foi possível abrir a câmera {self.indice}. Verifique se ela está "
                "conectada, se outro programa (Zoom, Teams, navegador) não a está "
                "usando e se o sistema deu permissão de acesso à câmera. "
                "Para usar outra câmera: --camera 1 ou LIBRAS_CAMERA=1."
            )
        captura.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)

        # Algumas câmeras "abrem" mas não entregam imagem; testamos um frame.
        ok, _ = captura.read()
        if not ok:
            captura.release()
            raise ErroCamera(
                f"A câmera {self.indice} foi aberta, mas não enviou nenhuma imagem. "
                "Tente outro índice de câmera ou reconecte o dispositivo."
            )
        self._captura = captura
        self._falhas_seguidas = 0

    def ler(self) -> np.ndarray | None:
        """Lê um frame BGR (já espelhado, se configurado) ou `None` em falha momentânea."""
        if self._captura is None:
            raise ErroCamera("A câmera não foi aberta. Chame abrir() antes de ler().")

        ok, frame = self._captura.read()
        if not ok or frame is None:
            self._falhas_seguidas += 1
            if self._falhas_seguidas >= self.max_falhas:
                raise ErroCamera(
                    f"A câmera parou de enviar imagens ({self._falhas_seguidas} falhas "
                    "seguidas). Ela pode ter sido desconectada."
                )
            return None

        self._falhas_seguidas = 0
        if self.espelhar:
            frame = cv2.flip(frame, 1)
        return frame

    def resolucao(self) -> tuple[int, int]:
        """Resolução real entregue pela câmera (pode diferir da solicitada)."""
        if self._captura is None:
            return (0, 0)
        return (
            int(self._captura.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self._captura.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    def liberar(self) -> None:
        if self._captura is not None:
            self._captura.release()
            self._captura = None

    def __enter__(self) -> Camera:
        self.abrir()
        return self

    def __exit__(self, *_exc) -> None:
        self.liberar()
