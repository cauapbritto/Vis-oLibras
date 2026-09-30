"""Câmera + visão em uma thread separada, para a interface nunca travar.

    processador = ProcessadorCamera(classificador)
    processador.start()
    ...  # na thread da interface, periodicamente:
    quadro = processador.ultimo_quadro()      # só o mais recente (para desenhar)
    for evento in processador.eventos():      # nenhum se perde (palavras, erros)
        ...
    processador.parar()

Dois canais, de propósito:
- o QUADRO é "o último vale": se a interface estiver lenta, quadros antigos são
  descartados (não faz sentido mostrar imagem atrasada);
- os EVENTOS vão para uma fila: uma palavra confirmada nunca pode se perder
  junto com um quadro descartado.

Eventos: ("status", texto) | ("palavra", (palavra, confiança, momento)) |
         ("erro", texto) | ("parado", None)
"""

from __future__ import annotations

import queue
import threading
from typing import Iterator

from libras import config
from libras.camera import Camera, ErroCamera
from libras.classificador import Classificador
from libras.estabilizador import Estabilizador
from libras.extrator import ErroModelo
from libras.pipeline import PipelineVisao, QuadroProcessado


class ProcessadorCamera(threading.Thread):
    def __init__(self, classificador: Classificador | None = None,
                 indice_camera: int = config.INDICE_CAMERA,
                 estabilizador: Estabilizador | None = None) -> None:
        super().__init__(name="camera", daemon=True)
        self.classificador = classificador
        self.indice_camera = indice_camera
        self.estabilizador = estabilizador
        self._parar = threading.Event()
        self._limpar = threading.Event()
        self._trava = threading.Lock()
        self._quadro: QuadroProcessado | None = None
        self._eventos: queue.Queue = queue.Queue()
        self.pipeline: PipelineVisao | None = None  # para a interface ajustar o modo leve ao vivo

    # --- chamados pela thread da interface --------------------------------------

    def parar(self) -> None:
        """Pede para parar (não bloqueia); a thread libera a câmera e emite "parado"."""
        self._parar.set()

    def pedir_limpeza(self) -> None:
        """Pede para esquecer a janela atual e o estabilizador (ex.: ao limpar a frase)."""
        self._limpar.set()

    def ultimo_quadro(self) -> QuadroProcessado | None:
        with self._trava:
            quadro, self._quadro = self._quadro, None
        return quadro

    def eventos(self) -> Iterator[tuple[str, object]]:
        while True:
            try:
                yield self._eventos.get_nowait()
            except queue.Empty:
                return

    # --- thread da câmera ----------------------------------------------------------

    def run(self) -> None:
        pipeline = None
        camera = Camera(indice=self.indice_camera)
        try:
            self._eventos.put(("status", "Abrindo a câmera..."))
            camera.abrir()
            if camera.imagem_suspeita:
                self._eventos.put(("aviso", "A imagem da câmera parece com defeito (listras). Escolha outra "
                                            "câmera na lista ou outro modo em Configurações > Câmera."))
            self._eventos.put(("status", "Carregando o MediaPipe..."))
            pipeline = PipelineVisao(self.classificador, self.estabilizador)
            self.pipeline = pipeline
            self._eventos.put(("status", "ok"))
            while not self._parar.is_set():
                frame = camera.ler()
                if frame is None:
                    continue  # falha momentânea; camera.ler() lança ErroCamera se persistir
                if self._limpar.is_set():
                    self._limpar.clear()
                    pipeline.limpar()
                quadro = pipeline.processar(frame)
                if quadro.estado.palavra:
                    self._eventos.put(("palavra", (quadro.estado.palavra, quadro.estado.confianca,
                                                   quadro.momento)))
                with self._trava:
                    self._quadro = quadro
        except (ErroCamera, ErroModelo) as erro:
            self._eventos.put(("erro", str(erro)))
        except Exception as erro:  # nunca deixar a thread morrer em silêncio
            self._eventos.put(("erro", f"erro inesperado na câmera: {erro}"))
        finally:
            camera.liberar()
            if pipeline is not None:
                pipeline.fechar()
            self._eventos.put(("parado", None))
