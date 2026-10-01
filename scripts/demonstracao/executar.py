"""Aplicação em tempo real em janela do OpenCV: câmera -> reconhecimento -> texto -> voz.
(Versão simples; a interface gráfica de demonstração é o scripts/demonstracao/app.py.)

Webcam -> OpenCV -> MediaPipe -> landmarks -> mesmo pré-processamento do treino
-> modelo treinado -> estabilizador (anti-repetição) -> sequência de palavras.

Uso:
    python scripts/demonstracao/executar.py
    python scripts/demonstracao/executar.py --limiar 0.6 --consecutivas 4 --cooldown 1.5

Teclas:
    C          limpa a sequência atual
    BACKSPACE  apaga a última palavra
    ESPAÇO     encerra a frase agora (e fala)
    Q/ESC      sai
"""

import argparse
import sys
import time

import cv2

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config, preferencias
from libras.camera import Camera, ErroCamera
from libras.classificador import ErroClassificador, carregar_classificador
from libras.desenho import (COR_AVISO, COR_OK, COR_TEXTO, descrever_maos, desenhar_barra,
                            desenhar_legenda, desenhar_painel, escrever, eh_tecla_sair,
                            janela_fechada, ler_tecla)
from libras.estabilizador import Estabilizador
from libras.extrator import ErroModelo
from libras.frase import GerenciadorSentenca
from libras.pipeline import PipelineVisao
from libras.traducao import carregar_tabela_padrao
from libras.voz import Voz

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
    voz = None if args.sem_voz else Voz(ao_erro=lambda m: print(f"  [voz] {m}"))

    def ao_finalizar(frase: str) -> None:
        glosa = sentenca.glosa_final
        print(f"  frase: {frase}" + (f"   (sinais: {glosa})" if glosa != frase else ""))
        if voz is not None and config.FALAR_AO_FINALIZAR:
            voz.falar(GerenciadorSentenca.texto_para_fala(frase))

    tabela = carregar_tabela_padrao()
    if tabela is not None:
        print(f"Tabela de frases: {len(tabela)} frases ({config.ARQ_FRASES.name})")
        for aviso in tabela.avisos:
            print(f"  [AVISO] {aviso}")
    sentenca = GerenciadorSentenca(ao_finalizar=ao_finalizar, tabela=tabela, pausa_s=config.PAUSA_FRASE_S)
    aceita = None  # (palavra, momento) para o destaque na tela

    print(f"Modelo: {classificador.info.get('descricao')} | classes: {', '.join(classificador.classes)}")
    print(f"Estabilizador: limiar={estabilizador.limiar} consecutivas={estabilizador.n_consecutivas} "
          f"cooldown={estabilizador.cooldown_s}s mesmo_sinal={estabilizador.cooldown_mesmo_sinal_s}s "
          f"liberacao={estabilizador.exigir_liberacao} passo={args.passo}")
    if voz is not None:
        print(f"Voz: {voz.nome_voz}" if voz.disponivel else f"Voz indisponível: {voz.erro}")

    pipeline = PipelineVisao(classificador, estabilizador, passo_inferencia=args.passo)
    try:
        with Camera(indice=args.camera) as camera:
            cv2.namedWindow(config.NOME_JANELA)
            while True:
                frame = camera.ler()
                if frame is None:
                    if eh_tecla_sair(ler_tecla(10)) or janela_fechada():
                        break
                    continue

                quadro = pipeline.processar(frame)
                estado, agora = quadro.estado, quadro.momento
                sentenca.atualizar_deteccao(estado.sinal, estado.confianca, estado.em_movimento, agora)
                if estado.palavra and sentenca.adicionar(estado.palavra, agora):
                    aceita = (estado.palavra, agora)
                    print(f"[{time.strftime('%H:%M:%S')}] palavra: {config.rotulo_exibicao(estado.palavra)} "
                          f"({estado.confianca:.0%})")
                if config.FINALIZAR_POR_PAUSA:
                    sentenca.verificar_pausa(agora)

                # Tela (landmarks já desenhados pelo pipeline)
                imagem = quadro.imagem
                desenhar_painel(imagem, linhas_painel(quadro.resultado, estado, estabilizador,
                                                      quadro.fps, agora, aceita))
                topo_legenda = desenhar_legenda(imagem, [
                    ("  ·  ".join(sentenca.sequencia), COR_TEXTO, 22),
                    (f"Frase final: {sentenca.frase_final}" if sentenca.frase_final
                     else ("" if sentenca.palavras else "Faça um sinal para começar"), (0, 220, 255), 20),
                ])
                if estado.sinal not in (None, config.CLASSE_NADA):
                    desenhar_barras(imagem, topo_legenda, estado.confianca, estabilizador)
                cv2.imshow(config.NOME_JANELA, imagem)

                tecla = ler_tecla()
                if eh_tecla_sair(tecla) or janela_fechada():
                    break
                caractere = chr(tecla) if tecla != -1 else ""
                if caractere in config.TECLAS_LIMPAR:
                    sentenca.limpar()
                    pipeline.limpar()
                    aceita = None
                    print("  (sequência limpa)")
                elif caractere in config.TECLAS_APAGAR_ULTIMA:
                    sentenca.remover_ultima()
                elif caractere in config.TECLAS_FINALIZAR:
                    sentenca.finalizar()
    finally:
        pipeline.fechar()
        if voz is not None:
            voz.encerrar()


def main() -> int:
    for aviso in preferencias.carregar():   # as mesmas configurações da janela (preferencias.json)
        print(f"[AVISO] preferências: {aviso}")
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
    parser.add_argument("--sem-voz", action="store_true", help="não fala as frases")
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
