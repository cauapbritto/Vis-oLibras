"""Aplicação em tempo real (Fase 4): câmera -> reconhecimento -> texto.
(A voz entra na Fase 6.)

Webcam -> OpenCV -> MediaPipe -> landmarks -> mesmo pré-processamento do treino
-> modelo treinado -> estabilizador (anti-repetição) -> sequência de palavras.

Uso:
    python scripts/executar.py
    python scripts/executar.py --limiar 0.6 --consecutivas 4 --cooldown 1.5

Teclas:
    C          limpa a sequência atual
    BACKSPACE  apaga a última palavra
    ESPAÇO     encerra a frase agora
    Q/ESC      sai
"""

import argparse
import sys
import time

import cv2

from libras import config
from libras.camera import Camera, ErroCamera
from libras.classificador import ErroClassificador, carregar_classificador
from libras.desenho import (COR_AVISO, COR_OK, COR_TEXTO, descrever_maos, desenhar_barra,
                            desenhar_legenda, desenhar_maos, desenhar_painel, desenhar_pose,
                            escrever, eh_tecla_sair, janela_fechada, ler_tecla)
from libras.estabilizador import Estabilizador
from libras.extrator import ErroModelo, ExtratorLandmarks, para_linha_bruta
from libras.frase import Frase
from libras.metricas import ContadorFPS
from libras.reconhecedor import Reconhecedor

COR_CINZA = (170, 170, 170)
SEGUNDOS_DESTAQUE = 1.5  # quanto tempo "Aceito: NOME" fica em destaque


def linhas_painel(resultado, estado, estabilizador, fps, agora, aceita):
    if estado.sinal in (None, config.CLASSE_NADA):
        previsto = ("Previsto: - (nenhum sinal)", COR_CINZA)
    else:
        cor = COR_OK if estado.confianca >= estabilizador.limiar else COR_AVISO
        previsto = (f"Previsto: {config.rotulo_exibicao(estado.sinal)} ({estado.confianca:.0%})", cor)

    if estabilizador.em_cooldown(agora):
        estabilidade = ("Aguardando (cooldown)", COR_CINZA)
    elif estabilizador.candidato:
        estabilidade = (f"Estabilizando: {estabilizador.contagem}/{estabilizador.n_consecutivas}", COR_TEXTO)
    else:
        estabilidade = ("Pronto para um sinal", COR_TEXTO)

    linhas = [
        previsto,
        estabilidade,
        (descrever_maos(resultado), COR_TEXTO if resultado.tem_maos else COR_CINZA),
        (f"FPS: {fps:.1f}   Modelo: {estado.tempo_inferencia_ms:.0f} ms", COR_TEXTO),
    ]
    if aceita and agora - aceita[1] < SEGUNDOS_DESTAQUE:
        linhas.append((f"Aceito: {config.rotulo_exibicao(aceita[0])}", COR_OK))
    if estado.aviso:
        linhas.append((estado.aviso, COR_AVISO))
    linhas.append(("C limpar | BACKSPACE apagar | ESPAÇO encerrar | Q sair", COR_CINZA))
    return linhas


def desenhar_barras(frame, topo_legenda: int, confianca: float, estabilizador: Estabilizador) -> None:
    """Barras de confiança e de estabilidade logo acima da legenda."""
    cor = COR_OK if confianca >= estabilizador.limiar else COR_AVISO
    for i, (rotulo, fracao, cor_barra) in enumerate((("Estabilidade", estabilizador.progresso, COR_TEXTO),
                                                     ("Confiança", confianca, cor))):
        y = topo_legenda - 22 - i * 22
        escrever(frame, rotulo, (12, y + 12), COR_TEXTO, escala=0.5)
        desenhar_barra(frame, (130, y), (180, 12), fracao, cor_barra)


def executar(args) -> None:
    classificador = carregar_classificador()
    estabilizador = Estabilizador(limiar=args.limiar, n_consecutivas=args.consecutivas,
                                  cooldown_s=args.cooldown, cooldown_mesmo_sinal_s=args.cooldown_mesmo,
                                  exigir_liberacao=not args.sem_liberacao)
    reconhecedor = Reconhecedor(classificador, estabilizador, passo_inferencia=args.passo)
    frase = Frase()
    fps = ContadorFPS()
    aceita = None  # (palavra, momento) para o destaque na tela

    print(f"Modelo: {classificador.info.get('descricao')} | classes: {', '.join(classificador.classes)}")
    print(f"Estabilizador: limiar={estabilizador.limiar} consecutivas={estabilizador.n_consecutivas} "
          f"cooldown={estabilizador.cooldown_s}s mesmo_sinal={estabilizador.cooldown_mesmo_sinal_s}s "
          f"liberacao={estabilizador.exigir_liberacao} passo={reconhecedor.passo_inferencia}")

    with Camera(indice=args.camera) as camera, ExtratorLandmarks() as extrator:
        cv2.namedWindow(config.NOME_JANELA)
        while True:
            frame = camera.ler()
            if frame is None:
                if eh_tecla_sair(ler_tecla(10)) or janela_fechada():
                    break
                continue

            resultado = extrator.extrair(frame)
            agora = time.perf_counter()
            estado = reconhecedor.processar(para_linha_bruta(resultado, agora), agora)

            if estado.palavra:
                aceita = (estado.palavra, agora)
                print(f"[{time.strftime('%H:%M:%S')}] palavra: {config.rotulo_exibicao(estado.palavra)} "
                      f"({estado.confianca:.0%})")
                encerrada = frase.adicionar(estado.palavra, agora)
                if encerrada:
                    print(f"  frase: {encerrada}")
            if frase.pausa_detectada(agora):
                print(f"  frase: {frase.finalizar()}")

            # Tela
            desenhar_pose(frame, resultado)
            desenhar_maos(frame, resultado)
            desenhar_painel(frame, linhas_painel(resultado, estado, estabilizador,
                                                 fps.atualizar(agora), agora, aceita))
            topo_legenda = desenhar_legenda(frame, [
                (frase.glosa(), COR_TEXTO, 20),
                (frase.texto() if frase.palavras else "", (0, 220, 255), 28),
                ("" if frase.palavras else (f"Última frase: {frase.ultima_frase}" if frase.ultima_frase
                                            else "Faça um sinal para começar"), COR_CINZA, 18),
            ])
            if estado.sinal not in (None, config.CLASSE_NADA):
                desenhar_barras(frame, topo_legenda, estado.confianca, estabilizador)
            cv2.imshow(config.NOME_JANELA, frame)

            tecla = ler_tecla()
            if eh_tecla_sair(tecla) or janela_fechada():
                break
            caractere = chr(tecla) if tecla != -1 else ""
            if caractere in config.TECLAS_LIMPAR:
                frase.limpar()
                reconhecedor.limpar()
                aceita = None
                print("  (sequência limpa)")
            elif caractere in config.TECLAS_APAGAR_ULTIMA:
                frase.remover_ultima()
            elif caractere in config.TECLAS_FINALIZAR:
                texto = frase.finalizar()
                if texto:
                    print(f"  frase: {texto}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=config.INDICE_CAMERA, help="índice da webcam")
    grupo = parser.add_argument_group("estabilização (padrões do config.py)")
    grupo.add_argument("--limiar", type=float, default=config.LIMIAR_CONFIANCA,
                       help=f"confiança mínima de 0 a 1 (padrão {config.LIMIAR_CONFIANCA})")
    grupo.add_argument("--consecutivas", type=int, default=config.N_CONSECUTIVAS,
                       help=f"previsões iguais seguidas (padrão {config.N_CONSECUTIVAS})")
    grupo.add_argument("--cooldown", type=float, default=config.COOLDOWN_S,
                       help=f"segundos após qualquer palavra (padrão {config.COOLDOWN_S})")
    grupo.add_argument("--cooldown-mesmo", type=float, default=config.COOLDOWN_MESMO_SINAL_S,
                       help=f"segundos antes de repetir a mesma palavra (padrão {config.COOLDOWN_MESMO_SINAL_S})")
    grupo.add_argument("--sem-liberacao", action="store_true",
                       help="permite repetir a mesma palavra sem abaixar as mãos entre elas")
    grupo.add_argument("--passo", type=int, default=config.PASSO_INFERENCIA,
                       help=f"classifica a cada N frames (padrão {config.PASSO_INFERENCIA})")
    args = parser.parse_args()
    if not 0 < args.limiar <= 1:
        parser.error("--limiar deve estar entre 0 e 1")

    try:
        executar(args)
    except ErroClassificador as erro:
        print(f"[ERRO DE MODELO] {erro}", file=sys.stderr)
        return 1
    except ErroCamera as erro:
        print(f"[ERRO DE CÂMERA] {erro}", file=sys.stderr)
        return 1
    except ErroModelo as erro:
        print(f"[ERRO DO MEDIAPIPE] {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompido pelo usuário.")
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
