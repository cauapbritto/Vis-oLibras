"""Coleta de amostras de um sinal pela webcam (Fase 2).

Cada amostra são config.DURACAO_AMOSTRA segundos de landmarks crus (mãos +
ombros), salvos em data/raw/<SINAL>/ como .npy, sem imagens. Amostras ruins
(sem mãos, sem ombros, câmera lenta) são descartadas na hora.

Uso:
    python scripts/desenvolvimento/coletar_dados.py --sinal OI --pessoa ana
    python scripts/desenvolvimento/coletar_dados.py --label NAO --pessoa ana --meta 20
    python scripts/desenvolvimento/coletar_dados.py --sinal _NADA --pessoa ana

Teclas:
    ESPAÇO  inicia/pausa a gravação contínua (uma amostra atrás da outra)
    D       desfaz (apaga) a última amostra salva
    Q/ESC   sai
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config, dataset
from libras.camera import Camera, ErroCamera
from libras.desenho import (COR_AVISO, COR_GRAVANDO, COR_OK, COR_TEXTO, descrever_maos,
                            desenhar_barra_progresso, desenhar_borda, desenhar_maos,
                            desenhar_painel, desenhar_pose, eh_tecla_sair, janela_fechada,
                            ler_tecla)
from libras.extrator import ErroModelo, ExtratorLandmarks, para_linha_bruta
from libras.metricas import ContadorFPS

PAUSADO, PREPARANDO, GRAVANDO = "pausado", "preparando", "gravando"
TECLA_ESPACO = ord(" ")
TECLAS_DESFAZER = (ord("d"), ord("D"))


class Coletor:
    """Máquina de estados da coleta: PAUSADO -> PREPARANDO -> GRAVANDO -> PREPARANDO..."""

    def __init__(self, sinal: str, pessoa: str, meta: int) -> None:
        self.sinal = sinal
        self.pessoa = pessoa
        self.meta = meta
        self.estado = PAUSADO
        self.fim_preparo = 0.0
        self.inicio_gravacao = 0.0
        self.frames: list[np.ndarray] = []
        self.salvas_sessao: list[Path] = []
        self.descartadas = 0
        self.total_sinal = dataset.contar_amostras(sinal)
        self.mensagem = ("ESPAÇO para começar", COR_TEXTO)

    def alternar(self, agora: float) -> None:
        """ESPAÇO: inicia (com contagem regressiva) ou pausa a gravação contínua."""
        if self.estado == PAUSADO:
            if len(self.salvas_sessao) >= self.meta:
                self.meta += config.AMOSTRAS_POR_SESSAO  # continua depois de bater a meta
            self.estado = PREPARANDO
            self.fim_preparo = agora + config.CONTAGEM_REGRESSIVA
            self.mensagem = ("Faça o sinal quando a borda ficar vermelha", COR_TEXTO)
        else:
            self.estado = PAUSADO
            self.frames = []  # amostra incompleta é descartada
            self.mensagem = ("Pausado. ESPAÇO para continuar", COR_TEXTO)

    def desfazer(self) -> None:
        """D: apaga a última amostra salva nesta sessão."""
        if not self.salvas_sessao:
            self.mensagem = ("Nada para desfazer", COR_AVISO)
            return
        dataset.remover_amostra(self.salvas_sessao.pop())
        self.total_sinal -= 1
        self.mensagem = ("Última amostra apagada", COR_AVISO)

    def atualizar(self, linha: np.ndarray, agora: float) -> None:
        """Chamado a cada frame com a linha de landmarks crus."""
        if self.estado == PREPARANDO and agora >= self.fim_preparo:
            self.estado = GRAVANDO
            self.inicio_gravacao = agora
            self.frames = []

        if self.estado != GRAVANDO:
            return
        self.frames.append(linha)
        if agora - self.inicio_gravacao >= config.DURACAO_AMOSTRA:
            self._finalizar_amostra(agora)

    def _finalizar_amostra(self, agora: float) -> None:
        amostra = np.stack(self.frames)
        amostra[:, config.COL_TIMESTAMP] -= amostra[0, config.COL_TIMESTAMP]  # tempo relativo
        self.frames = []

        problemas = dataset.validar_amostra(amostra, self.sinal)
        if problemas:
            self.descartadas += 1
            self.mensagem = (f"Descartada: {problemas[0]}", COR_AVISO)
        else:
            self.salvas_sessao.append(dataset.salvar_amostra(amostra, self.sinal, self.pessoa))
            self.total_sinal += 1
            self.mensagem = (f"Amostra {len(self.salvas_sessao)} salva", COR_OK)

        if len(self.salvas_sessao) >= self.meta:
            self.estado = PAUSADO
            self.mensagem = ("Meta atingida! ESPAÇO grava mais, Q sai", COR_OK)
        else:
            self.estado = PREPARANDO
            self.fim_preparo = agora + config.INTERVALO_ENTRE_AMOSTRAS

    def linhas_painel(self, resultado, fps: float, agora: float) -> list[tuple[str, tuple]]:
        ombros = ("Ombros: OK", COR_OK) if resultado.tem_ombros else \
                 ("Ombros: não visíveis - afaste-se", COR_AVISO)
        maos_ok = resultado.tem_maos or self.sinal == config.CLASSE_NADA
        if self.estado == PREPARANDO:
            estado = (f"Prepare-se: {self.fim_preparo - agora:.1f}s", COR_AVISO)
        elif self.estado == GRAVANDO:
            estado = ("GRAVANDO", COR_GRAVANDO)
        else:
            estado = ("PAUSADO", COR_TEXTO)
        return [
            (f"Sinal: {config.rotulo_exibicao(self.sinal)}   Pessoa: {self.pessoa}", COR_TEXTO),
            (f"Sessão: {len(self.salvas_sessao)}/{self.meta}   Total: {self.total_sinal}   "
             f"Descartadas: {self.descartadas}", COR_TEXTO),
            (descrever_maos(resultado), COR_TEXTO if maos_ok else COR_AVISO),
            ombros,
            (f"FPS: {fps:.1f}", COR_TEXTO),
            estado,
            self.mensagem,
            ("ESPAÇO iniciar/pausar | D desfazer | Q sair", COR_TEXTO),
        ]


def executar(sinal: str, pessoa: str, meta: int, indice_camera: int) -> None:
    coletor = Coletor(sinal, pessoa, meta)
    fps = ContadorFPS()

    with Camera(indice=indice_camera) as camera, ExtratorLandmarks() as extrator:
        print(f"Coletando '{sinal}' (pessoa: {pessoa}). Já existem {coletor.total_sinal} amostras.")
        cv2.namedWindow(config.NOME_JANELA)

        while True:
            frame = camera.ler()
            if frame is None:
                if eh_tecla_sair(ler_tecla(10)) or janela_fechada():
                    break
                continue

            resultado = extrator.extrair(frame)
            agora = time.perf_counter()
            coletor.atualizar(para_linha_bruta(resultado, agora), agora)

            desenhar_pose(frame, resultado)
            desenhar_maos(frame, resultado)
            desenhar_painel(frame, coletor.linhas_painel(resultado, fps.atualizar(agora), agora))
            if coletor.estado == GRAVANDO:
                desenhar_borda(frame, COR_GRAVANDO)
                desenhar_barra_progresso(
                    frame, (agora - coletor.inicio_gravacao) / config.DURACAO_AMOSTRA, COR_GRAVANDO)
            cv2.imshow(config.NOME_JANELA, frame)

            tecla = ler_tecla()
            if eh_tecla_sair(tecla) or janela_fechada():
                break
            if tecla == TECLA_ESPACO:
                coletor.alternar(agora)
            elif tecla in TECLAS_DESFAZER:
                coletor.desfazer()

    print(f"Sessão encerrada: {len(coletor.salvas_sessao)} amostras salvas, "
          f"{coletor.descartadas} descartadas. Total de '{sinal}': {coletor.total_sinal}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sinal", "--label", dest="sinal", required=True,
                        help=f"sinal a gravar: {', '.join(config.CLASSES)}")
    parser.add_argument("--pessoa", required=True, help="quem está gravando (ex.: ana)")
    parser.add_argument("--meta", type=int, default=config.AMOSTRAS_POR_SESSAO,
                        help=f"amostras nesta sessão (padrão: {config.AMOSTRAS_POR_SESSAO})")
    parser.add_argument("--camera", type=int, default=config.INDICE_CAMERA,
                        help=f"índice da webcam (padrão: {config.INDICE_CAMERA})")
    args = parser.parse_args()

    sinal = config.identificador_sinal(args.sinal)
    if sinal not in config.CLASSES:
        parser.error(f"sinal '{args.sinal}' não está em config.CLASSES: {', '.join(config.CLASSES)}")
    try:
        pessoa = dataset.validar_pessoa(args.pessoa)
    except ValueError as erro:
        parser.error(str(erro))
    if args.meta < 1:
        parser.error("--meta deve ser pelo menos 1")

    try:
        executar(sinal, pessoa, args.meta, args.camera)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
