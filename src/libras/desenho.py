"""Desenho na tela com OpenCV: landmarks das mãos e dos ombros, painel de
informações (FPS, mãos detectadas, estado da coleta...) e leitura do teclado.

Observação: `cv2.putText` não desenha acentos (apareceriam como "??"), então
o texto do painel passa por `sem_acentos()`. A legenda com a frase, que precisa
dos acentos ("Não", "é"), é desenhada com o Pillow em `desenhar_legenda()`,
usando uma fonte do próprio sistema (sem depender de bibliotecas de treino).
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

import cv2
import numpy as np

from libras import config
from libras.extrator import CONEXOES_MAO, LADO_DIREITO, LADO_ESQUERDO, ResultadoExtracao

# Cores em BGR
COR_DIREITA = (80, 200, 80)     # verde
COR_ESQUERDA = (240, 150, 40)   # azul
COR_TEXTO = (255, 255, 255)
COR_AVISO = (0, 200, 255)       # amarelo/laranja
COR_OK = (80, 200, 80)          # verde
COR_GRAVANDO = (60, 60, 230)    # vermelho
COR_POSE = (200, 200, 200)      # cinza claro
COR_FUNDO_PAINEL = (0, 0, 0)

NOMES_LADO = {LADO_DIREITO: "Direita", LADO_ESQUERDO: "Esquerda"}
CORES_LADO = {LADO_DIREITO: COR_DIREITA, LADO_ESQUERDO: COR_ESQUERDA}

FONTE = cv2.FONT_HERSHEY_SIMPLEX


def sem_acentos(texto: str) -> str:
    """'Mão direita' -> 'Mao direita' (o OpenCV só desenha ASCII)."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return decomposto.encode("ascii", "ignore").decode("ascii")


def desenhar_barra(frame: np.ndarray, origem: tuple[int, int], tamanho: tuple[int, int],
                   fracao: float, cor: tuple[int, int, int]) -> None:
    """Barra horizontal pequena (ex.: confiança), com moldura."""
    (x, y), (largura, altura) = origem, tamanho
    fracao = min(max(fracao, 0.0), 1.0)
    cv2.rectangle(frame, (x, y), (x + largura, y + altura), (60, 60, 60), -1)
    cv2.rectangle(frame, (x, y), (x + int(largura * fracao), y + altura), cor, -1)
    cv2.rectangle(frame, (x, y), (x + largura, y + altura), COR_TEXTO, 1)


# Fontes com acentos, na ordem de preferência. Nomes sem pasta são procurados
# pelo Pillow nas pastas de fontes do sistema (Windows e Linux).
FONTES_SISTEMA = (
    "segoeui.ttf", "arial.ttf",                                   # Windows
    "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",                                 # Linux
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",  # macOS
)

FONTES_SISTEMA_NEGRITO = (
    "seguisb.ttf", "segoeuib.ttf", "arialbd.ttf",                 # Windows (Segoe UI Semibold)
    "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",                                    # Linux
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",  # macOS
)


@lru_cache(maxsize=16)
def fonte_com_acentos(tamanho: int, negrito: bool = False):
    """Fonte com acentos para o Pillow, ou None se o Pillow não estiver disponível."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for nome in (FONTES_SISTEMA_NEGRITO if negrito else ()) + FONTES_SISTEMA:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tamanho)  # Pillow >= 10.1: fonte embutida
    except TypeError:
        return None


def _capsula(desenho, p1, p2, raio: float, cor) -> None:
    """Retângulo de pontas redondas entre p1 e p2, em qualquer ângulo (Pillow)."""
    import math
    (x1, y1), (x2, y2) = p1, p2
    angulo = math.atan2(y2 - y1, x2 - x1)
    nx, ny = -math.sin(angulo) * raio, math.cos(angulo) * raio
    desenho.polygon([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)], fill=cor)
    for x, y in (p1, p2):
        desenho.ellipse([x - raio, y - raio, x + raio, y + raio], fill=cor)


def icone_mao(tamanho: int, cor_mao="#ffffff", cor_fundo=None):
    """Ícone do Librahin: mão aberta estilizada, como imagem RGBA do Pillow.
    Com `cor_fundo`, a mão fica dentro de um quadrado de cantos arredondados.
    Desenhado 4x maior e reduzido, para as bordas ficarem suaves."""
    from PIL import Image, ImageDraw
    lado = tamanho * 4
    imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagem)
    if cor_fundo is not None:
        d.rounded_rectangle([0, 0, lado - 1, lado - 1], radius=int(lado * 0.22), fill=cor_fundo)
    y = lambda v: v * lado            # noqa: E731
    x = lambda v: (v + 0.045) * lado  # noqa: E731  (desloca para centralizar a mão com o polegar)
    d.rounded_rectangle([x(0.30), y(0.44), x(0.71), y(0.84)], radius=y(0.13), fill=cor_mao)  # palma
    for centro, topo, largura in ((0.345, 0.23, 0.092), (0.455, 0.155, 0.092),
                                  (0.565, 0.19, 0.092), (0.665, 0.29, 0.09)):              # dedos
        d.rounded_rectangle([x(centro - largura / 2), y(topo), x(centro + largura / 2), y(0.58)],
                            radius=y(largura / 2), fill=cor_mao)
    _capsula(d, (x(0.36), y(0.70)), (x(0.185), y(0.495)), y(0.05), cor_mao)                # polegar
    return imagem.resize((tamanho, tamanho), Image.LANCZOS)


def desenhar_legenda(frame: np.ndarray, linhas: list[tuple[str, tuple[int, int, int], int]]) -> int:
    """Faixa na parte de baixo da imagem com texto COM acentos.
    Cada linha é (texto, cor BGR, tamanho da fonte em px). Devolve o y do topo da faixa."""
    linhas = [l for l in linhas if l[0]]
    if not linhas:
        return frame.shape[0]
    altura_img, largura_img = frame.shape[:2]
    altura = sum(int(t * 1.35) for _, _, t in linhas) + 16
    y0 = altura_img - altura
    regiao = frame[y0:, :]
    frame[y0:, :] = cv2.addWeighted(regiao, 0.35, np.zeros_like(regiao), 0.65, 0)

    if fonte_com_acentos(linhas[0][2]) is None:  # sem Pillow: cai para o OpenCV, sem acentos
        y = y0 + 8
        for texto, cor, tamanho in linhas:
            y += int(tamanho * 1.35)
            escrever(frame, texto, (12, y - 6), cor, escala=tamanho / 32)
        return y0

    from PIL import Image, ImageDraw
    faixa = Image.fromarray(cv2.cvtColor(frame[y0:, :], cv2.COLOR_BGR2RGB))
    desenho = ImageDraw.Draw(faixa)
    y = 8
    for texto, cor, tamanho in linhas:
        fonte = fonte_com_acentos(tamanho)
        # Texto longo demais: mostra só o final (o mais recente)
        while len(texto) > 4 and desenho.textlength(texto, font=fonte) > largura_img - 24:
            texto = "…" + texto[2:]
        desenho.text((12, y), texto, font=fonte, fill=cor[::-1], stroke_width=2, stroke_fill=(0, 0, 0))
        y += int(tamanho * 1.35)
    frame[y0:, :] = cv2.cvtColor(np.asarray(faixa), cv2.COLOR_RGB2BGR)
    return y0


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


def desenhar_pose(frame: np.ndarray, resultado: ResultadoExtracao) -> None:
    """Desenha a linha dos ombros e o nariz (a referência usada na normalização)."""
    if resultado.pose is None:
        return
    altura, largura = frame.shape[:2]

    def pixel(indice: int) -> tuple[int, int]:
        x, y, _ = resultado.pose[indice]
        return int(x * largura), int(y * altura)

    ombro_e, ombro_d = pixel(config.POSE_OMBRO_ESQUERDO), pixel(config.POSE_OMBRO_DIREITO)
    cv2.line(frame, ombro_e, ombro_d, COR_POSE, 2, cv2.LINE_AA)
    for ponto in (ombro_e, ombro_d, pixel(config.POSE_NARIZ)):
        cv2.circle(frame, ponto, 6, COR_POSE, -1, cv2.LINE_AA)


def desenhar_borda(frame: np.ndarray, cor: tuple[int, int, int], espessura: int = 8) -> None:
    altura, largura = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (largura - 1, altura - 1), cor, espessura)


def desenhar_barra_progresso(frame: np.ndarray, fracao: float, cor: tuple[int, int, int]) -> None:
    """Barra horizontal na parte de baixo da imagem (0.0 a 1.0)."""
    altura, largura = frame.shape[:2]
    fracao = min(max(fracao, 0.0), 1.0)
    cv2.rectangle(frame, (0, altura - 14), (largura, altura), (40, 40, 40), -1)
    cv2.rectangle(frame, (0, altura - 14), (int(largura * fracao), altura), cor, -1)


def ler_tecla(espera_ms: int = 1) -> int:
    """Processa os eventos da janela e devolve a tecla pressionada (-1 se nenhuma)."""
    tecla = cv2.waitKey(espera_ms)
    return -1 if tecla == -1 else tecla & 0xFF


def eh_tecla_sair(tecla: int) -> bool:
    return tecla != -1 and chr(tecla) in config.TECLAS_SAIR


def janela_fechada(nome: str = config.NOME_JANELA) -> bool:
    """True se o usuário fechou a janela pelo botão X."""
    try:
        return cv2.getWindowProperty(nome, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


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
    """Painel semitransparente no canto com uma linha de texto por item (texto, cor).
    A fonte diminui automaticamente se o texto mais longo não couber no frame."""
    if not linhas:
        return
    x, y = origem
    largura_texto = max(cv2.getTextSize(sem_acentos(t), FONTE, 0.7, 2)[0][0] for t, _ in linhas)
    escala = min(0.7, 0.7 * (frame.shape[1] - x - 30) / max(largura_texto, 1))
    altura_linha = int(40 * escala)
    largura = int(largura_texto * escala / 0.7) + 20
    altura = altura_linha * len(linhas) + 12

    y2, x2 = min(y + altura, frame.shape[0]), min(x + largura, frame.shape[1])
    regiao = frame[y:y2, x:x2]
    fundo = np.full_like(regiao, COR_FUNDO_PAINEL)
    frame[y:y2, x:x2] = cv2.addWeighted(regiao, 0.45, fundo, 0.55, 0)

    for i, (texto, cor) in enumerate(linhas):
        escrever(frame, texto, (x + 10, y + altura_linha + i * altura_linha), cor, escala)
