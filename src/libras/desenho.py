"""Desenho na tela com OpenCV: landmarks das mãos e painel de informações
(FPS, mãos detectadas e, nas próximas fases, sinal, confiança e frase).

Observação: `cv2.putText` não desenha acentos (apareceriam como "??"), então
todo texto passa por `sem_acentos()` antes de ir para a tela.
"""

from __future__ import annotations

import unicodedata

import cv2
import numpy as np

from libras.extrator import CONEXOES_MAO, LADO_DIREITO, LADO_ESQUERDO, ResultadoExtracao

# Cores em BGR
COR_DIREITA = (80, 200, 80)     # verde
COR_ESQUERDA = (240, 150, 40)   # azul
COR_TEXTO = (255, 255, 255)
COR_AVISO = (0, 200, 255)       # amarelo/laranja
COR_FUNDO_PAINEL = (0, 0, 0)

NOMES_LADO = {LADO_DIREITO: "Direita", LADO_ESQUERDO: "Esquerda"}
CORES_LADO = {LADO_DIREITO: COR_DIREITA, LADO_ESQUERDO: COR_ESQUERDA}

FONTE = cv2.FONT_HERSHEY_SIMPLEX


def sem_acentos(texto: str) -> str:
    """'Mão direita' -> 'Mao direita' (o OpenCV só desenha ASCII)."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return decomposto.encode("ascii", "ignore").decode("ascii")


def descrever_maos(resultado: ResultadoExtracao) -> str:
    """Texto com as mãos detectadas: nenhuma, direita, esquerda ou ambas."""
    lados = resultado.lados
    if {LADO_DIREITO, LADO_ESQUERDO} <= lados:
        return "Ambas as mãos"
    if LADO_DIREITO in lados:
        return "Mão direita"
    if LADO_ESQUERDO in lados:
        return "Mão esquerda"
    return "Nenhuma mão detectada"


def desenhar_maos(frame: np.ndarray, resultado: ResultadoExtracao) -> None:
    """Desenha conexões, pontos e o rótulo do lado de cada mão (altera `frame`)."""
    altura, largura = frame.shape[:2]
    for mao in resultado.maos:
        cor = CORES_LADO.get(mao.lado, COR_TEXTO)
        # Coordenadas normalizadas [0, 1] -> pixels
        pixels = [(int(x * largura), int(y * altura)) for x, y, _ in mao.pontos]

        for inicio, fim in CONEXOES_MAO:
            cv2.line(frame, pixels[inicio], pixels[fim], cor, 2, cv2.LINE_AA)
        for ponto in pixels:
            cv2.circle(frame, ponto, 4, COR_TEXTO, -1, cv2.LINE_AA)
            cv2.circle(frame, ponto, 4, cor, 1, cv2.LINE_AA)

        # Rótulo perto do punho (ponto 0)
        x, y = pixels[0]
        rotulo = f"{NOMES_LADO.get(mao.lado, mao.lado)} {mao.confianca:.2f}"
        escrever(frame, rotulo, (x - 40, y + 25), cor, escala=0.6)


def escrever(
    frame: np.ndarray,
    texto: str,
    origem: tuple[int, int],
    cor: tuple[int, int, int] = COR_TEXTO,
    escala: float = 0.7,
) -> None:
    """Texto com contorno preto, legível sobre qualquer fundo."""
    texto = sem_acentos(texto)
    cv2.putText(frame, texto, origem, FONTE, escala, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, texto, origem, FONTE, escala, cor, 2, cv2.LINE_AA)


def desenhar_painel(
    frame: np.ndarray,
    linhas: list[tuple[str, tuple[int, int, int]]],
    origem: tuple[int, int] = (10, 10),
) -> None:
    """Painel semitransparente no canto com uma linha de texto por item (texto, cor)."""
    if not linhas:
        return
    altura_linha = 28
    x, y = origem
    largura = max(cv2.getTextSize(sem_acentos(t), FONTE, 0.7, 2)[0][0] for t, _ in linhas) + 20
    altura = altura_linha * len(linhas) + 12

    y2, x2 = min(y + altura, frame.shape[0]), min(x + largura, frame.shape[1])
    regiao = frame[y:y2, x:x2]
    fundo = np.full_like(regiao, COR_FUNDO_PAINEL)
    frame[y:y2, x:x2] = cv2.addWeighted(regiao, 0.45, fundo, 0.55, 0)

    for i, (texto, cor) in enumerate(linhas):
        escrever(frame, texto, (x + 10, y + 28 + i * altura_linha), cor)
