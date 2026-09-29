"""Fase 1: valida o caminho Webcam -> OpenCV -> MediaPipe.

Abre a webcam, detecta até duas mãos, desenha landmarks e conexões e mostra o
FPS e quais mãos foram detectadas. Não reconhece sinais.

Uso:
    python scripts/testar_deteccao.py
    python scripts/testar_deteccao.py --camera 1

Teclas: Q ou ESC para sair.
"""

import argparse
import sys
import time

import cv2

from libras import config
from libras.camera import Camera, ErroCamera
from libras.desenho import (COR_AVISO, COR_TEXTO, descrever_maos, desenhar_maos, desenhar_painel,
                            desenhar_pose, eh_tecla_sair, janela_fechada, ler_tecla)
from libras.extrator import ErroModelo, ExtratorLandmarks
from libras.metricas import ContadorFPS


def deve_sair(espera_ms: int = 1) -> bool:
    """True se o usuário apertou Q/ESC ou fechou a janela."""
    return eh_tecla_sair(ler_tecla(espera_ms)) or janela_fechada()


def executar(indice_camera: int) -> None:
    fps = ContadorFPS()
    ultimo_momento_com_mao = time.perf_counter()

    with Camera(indice=indice_camera) as camera, ExtratorLandmarks() as extrator:
        largura, altura = camera.resolucao()
        print(f"Câmera {indice_camera} aberta ({largura}x{altura}). Pressione Q ou ESC para sair.")
        cv2.namedWindow(config.NOME_JANELA)

        while True:
            frame = camera.ler()
            if frame is None:
                # Falha momentânea: Camera.ler() lança ErroCamera se persistir.
                if deve_sair(10):
                    break
                continue

            resultado = extrator.extrair(frame)
            agora = time.perf_counter()
            if resultado.tem_maos:
                ultimo_momento_com_mao = agora

            desenhar_pose(frame, resultado)
            desenhar_maos(frame, resultado)
            linhas = [
                (f"FPS: {fps.atualizar(agora):.1f}", COR_TEXTO),
                (descrever_maos(resultado), COR_TEXTO if resultado.tem_maos else COR_AVISO),
            ]
            if agora - ultimo_momento_com_mao > config.SEGUNDOS_SEM_MAO_DICA:
                linhas += [
                    ("Dica: mostre as mãos para a câmera,", COR_AVISO),
                    ("melhore a iluminação ou se afaste um pouco.", COR_AVISO),
                ]
            linhas.append(("Q/ESC: sair", COR_TEXTO))
            desenhar_painel(frame, linhas)

            cv2.imshow(config.NOME_JANELA, frame)
            if deve_sair():
                break


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=config.INDICE_CAMERA,
                        help=f"índice da webcam (padrão: {config.INDICE_CAMERA})")
    args = parser.parse_args()

    try:
        executar(args.camera)
    except ErroCamera as erro:
        print(f"[ERRO DE CÂMERA] {erro}", file=sys.stderr)
        return 1
    except ErroModelo as erro:
        print(f"[ERRO DE MODELO] {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompido pelo usuário.")
    finally:
        cv2.destroyAllWindows()
    print("Encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
