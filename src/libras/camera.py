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

import platform
import time
from dataclasses import dataclass

import cv2
import numpy as np

from libras import config


class ErroCamera(RuntimeError):
    """A webcam não pôde ser aberta ou parou de enviar imagens."""


# Modos de abrir a câmera. "auto" tenta, no Windows: DirectShow pedindo MJPG (rápido e
# com cores certas na maioria das webcams), Media Foundation e DirectShow simples, e
# fica com o primeiro que entrega uma imagem sem defeito.
MODOS_CAMERA = ("auto", "dshow_mjpg", "dshow", "msmf", "padrao")
NOMES_MODOS = {"dshow_mjpg": "DirectShow MJPG", "dshow": "DirectShow", "msmf": "Media Foundation",
               "padrao": "Padrão do OpenCV"}


def modos_do_sistema() -> list[str]:
    return ["dshow_mjpg", "msmf", "dshow"] if platform.system() == "Windows" else ["padrao"]


def _candidatos(modo: str) -> list[str]:
    return modos_do_sistema() if modo == "auto" else [modo]


def _abrir_modo(indice: int, modo: str, largura: int, altura: int):
    """VideoCapture aberto no modo pedido, ou None se não abriu."""
    if modo.startswith("dshow"):
        captura = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
    elif modo == "msmf":
        captura = cv2.VideoCapture(indice, cv2.CAP_MSMF)
    else:
        captura = cv2.VideoCapture(indice)
    if not captura.isOpened():
        captura.release()
        return None
    if modo == "dshow_mjpg":
        captura.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    captura.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
    captura.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
    return captura


def _primeiro_quadro(captura, tentativas: int = 10) -> np.ndarray | None:
    """Algumas câmeras demoram alguns quadros para "acordar": tenta algumas vezes."""
    for _ in range(tentativas):
        ok, frame = captura.read()
        if ok and frame is not None:
            return frame
        time.sleep(0.05)
    return None


def _quadro_para_avaliar(captura, espera_s: float = 2.0) -> np.ndarray | None:
    """Primeiro quadro; se vier preto, lê mais um pouco (algumas webcams começam pretas
    enquanto ajustam a exposição) antes de concluir que a imagem é preta mesmo."""
    frame = _primeiro_quadro(captura)
    limite = time.perf_counter() + espera_s
    while frame is not None and defeito_imagem(frame) == "preta" and time.perf_counter() < limite:
        ok, novo = captura.read()
        if ok and novo is not None:
            frame = novo
    return frame


def defeito_imagem(frame: np.ndarray) -> str | None:
    """Por que a imagem parece com defeito ("preta", "listras" ou "ruído"), ou None.

    - preta: escura e sem detalhe (tampa de privacidade fechada ou acesso bloqueado
      pelo Windows: a câmera "abre", mas manda quadros pretos);

    - listras: vizinhos na horizontal mudam muito mais que na vertical (formato de
      cor trocado: listras verticais roxas e verdes);
    - ruído: vizinhos quase não se parecem (numa imagem real, pixels vizinhos são
      parecidos; num quadro decodificado errado, parecem sorteados)."""
    if frame is None or frame.ndim < 2 or frame.shape[0] < 8 or frame.shape[1] < 8:
        return None
    cinza = frame.astype(np.float32).mean(axis=2) if frame.ndim == 3 else frame.astype(np.float32)
    if cinza.mean() < 12 and cinza.std() < 6:
        return "preta"
    horizontal = float(np.abs(np.diff(cinza[::4, :], axis=1)).mean())
    vertical = float(np.abs(np.diff(cinza[:, ::4], axis=0)).mean())
    if horizontal > 20 and horizontal > 4 * max(vertical, 1.0):
        return "listras"
    desvio = float(cinza.std())
    if desvio > 12 and (horizontal + vertical) / 2 > 0.6 * desvio:
        return "ruído"
    return None


def imagem_corrompida(frame: np.ndarray) -> bool:
    return defeito_imagem(frame) is not None


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
        modo: str | None = None,
    ) -> None:
        self.indice = indice
        self.modo = config.MODO_CAMERA if modo is None else modo   # lido agora: muda nas Configurações
        self.modo_usado: str | None = None      # o modo que funcionou (para diagnóstico)
        self.imagem_suspeita = False            # nenhum modo deu imagem sem defeito
        self.defeito: str | None = None         # defeito da imagem, quando suspeita
        self.largura = largura
        self.altura = altura
        self.espelhar = espelhar
        self.max_falhas = max_falhas
        self._captura: cv2.VideoCapture | None = None
        self._falhas_seguidas = 0

    def abrir(self) -> None:
        """Abre a câmera tentando os modos de _candidatos() até ter uma imagem boa."""
        abriu = False
        reserva = None   # (modo, defeito) do primeiro modo que mandou imagem, mesmo com defeito
        for modo in _candidatos(self.modo):
            captura = _abrir_modo(self.indice, modo, self.largura, self.altura)
            if captura is None:
                continue
            abriu = True
            frame = _quadro_para_avaliar(captura)
            defeito = defeito_imagem(frame) if frame is not None else None
            if frame is not None and defeito is None:
                self._usar(captura, modo, None)
                return
            captura.release()   # o Windows não deixa abrir a mesma câmera em dois modos ao mesmo tempo
            if frame is not None and reserva is None:
                reserva = (modo, defeito)
        if reserva is not None:   # só imagens com defeito: usa a primeira e avisa
            captura = _abrir_modo(self.indice, reserva[0], self.largura, self.altura)
            if captura is not None and _primeiro_quadro(captura) is not None:
                self._usar(captura, reserva[0], reserva[1])
                return
        if not abriu:
            raise ErroCamera(
                f"Não foi possível abrir a câmera {self.indice + 1}. Verifique se ela está "
                "conectada, se outro programa (Zoom, Teams, navegador) não a está "
                "usando e se o sistema deu permissão de acesso à câmera. Se houver mais "
                "de uma câmera, escolha outra na lista ao lado do botão (ou --camera 1)."
            )
        raise ErroCamera(
            f"A câmera {self.indice + 1} foi aberta, mas não enviou nenhuma imagem. "
            "Escolha outra câmera na lista ou reconecte o dispositivo."
        )

    def _usar(self, captura, modo: str, defeito: str | None) -> None:
        self._captura = captura
        self.modo_usado = modo
        self.defeito = defeito
        self.imagem_suspeita = defeito is not None
        self._falhas_seguidas = 0

    def ler(self) -> np.ndarray | None:
        """Lê um frame BGR (já espelhado, se configurado) ou `None` em falha momentânea."""
        if self._captura is None:
            raise ErroCamera("A câmera não foi aberta. Chame abrir() antes de ler().")

        ok, frame = self._captura.read()
        if not ok or frame is None:
            self._falhas_seguidas += 1
            time.sleep(0.01)  # evita esgotar as tentativas em milissegundos num soluço do USB
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


def listar_cameras(maximo: int = config.MAX_CAMERAS_PROCURAR) -> list[int]:
    """Índices das câmeras que abrem e entregam alguma imagem (0, 1, ...). Não chame
    com a câmera em uso por este programa. No Windows, tenta primeiro o DirectShow,
    que responde rápido quando o índice não existe; se ele abrir mas não mandar
    imagem, tenta o Media Foundation."""
    modos = ["dshow", "msmf"] if platform.system() == "Windows" else ["padrao"]
    encontradas = []
    for indice in range(maximo):
        for modo in modos:
            captura = _abrir_modo(indice, modo, config.LARGURA_CAMERA, config.ALTURA_CAMERA)
            if captura is None:
                break   # nem abriu: não existe câmera nesse índice
            try:
                if _primeiro_quadro(captura) is not None:
                    encontradas.append(indice)
                    break
            finally:
                captura.release()
    return encontradas


FPS_MINIMO = 5   # abaixo disso o reconhecimento não acompanha os sinais


@dataclass
class TesteCamera:
    indice: int
    modo: str
    abriu: bool = False
    frame: np.ndarray | None = None
    fps: float = 0.0
    defeito: str | None = None

    @property
    def lenta(self) -> bool:
        return self.frame is not None and self.fps < FPS_MINIMO

    @property
    def bom(self) -> bool:
        return self.frame is not None and self.defeito is None and not self.lenta

    @property
    def descricao(self) -> str:
        if not self.abriu:
            return "não abriu"
        if self.frame is None:
            return "abriu, sem imagem"
        altura, largura = self.frame.shape[:2]
        if self.defeito is not None:
            estado = f"com defeito ({self.defeito})"
        elif self.lenta:
            estado = "lenta demais"
        else:
            estado = "imagem boa"
        return f"{largura}x{altura}, {self.fps:.0f} fps, {estado}"


def diagnosticar(maximo: int = config.MAX_CAMERAS_PROCURAR, quadros: int = 15) -> list[TesteCamera]:
    """Testa cada câmera em cada modo e mede a imagem e o FPS (para escolher a melhor
    combinação quando o automático erra). Índices que nem abrem no primeiro modo são pulados."""
    resultados = []
    for indice in range(maximo):
        for n, modo in enumerate(modos_do_sistema()):
            teste = TesteCamera(indice, modo)
            captura = _abrir_modo(indice, modo, config.LARGURA_CAMERA, config.ALTURA_CAMERA)
            if captura is None:
                resultados.append(teste)
                if n == 0:
                    break   # nem abre: não existe câmera nesse índice
                continue
            teste.abriu = True
            try:
                frame = _quadro_para_avaliar(captura)
                if frame is not None:
                    inicio, lidos = time.perf_counter(), 0
                    for _ in range(quadros):
                        ok, novo = captura.read()
                        if ok and novo is not None:
                            frame, lidos = novo, lidos + 1
                    duracao = time.perf_counter() - inicio
                    teste.fps = lidos / duracao if duracao > 0 else 0.0
                    teste.frame = frame
                    teste.defeito = defeito_imagem(frame)
            finally:
                captura.release()
            resultados.append(teste)
    return resultados


def melhor_combinacao(resultados: list[TesteCamera]) -> TesteCamera | None:
    """A combinação com imagem boa e o maior FPS (ou None se nenhuma deu imagem boa)."""
    boas = [r for r in resultados if r.bom]
    return max(boas, key=lambda r: r.fps) if boas else None
