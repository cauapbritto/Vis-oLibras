"""Configuração central do projeto Vis-oLibras.

TODAS as constantes do sistema ficam aqui: nenhum "número mágico" deve aparecer
espalhado pelos outros módulos. Os caminhos são calculados a partir da pasta
raiz do projeto, então o projeto funciona em qualquer computador, independente
de onde foi clonado ou de qual pasta o script é executado.

Para conferir a configuração atual:

    python -m libras.config
"""

import os
from pathlib import Path

# =============================================================================
# Caminhos (sempre relativos à raiz do projeto)
# =============================================================================

# src/libras/config.py -> parents[0]=libras, [1]=src, [2]=raiz do projeto
RAIZ_PROJETO = Path(__file__).resolve().parents[2]

DIR_DATA = RAIZ_PROJETO / "data"
DIR_RAW = DIR_DATA / "raw"                  # uma pasta por sinal, um .npy por amostra
DIR_PROCESSED = DIR_DATA / "processed"
ARQ_METADATA = DIR_DATA / "metadata.csv"    # índice de todas as amostras gravadas
ARQ_DATASET = DIR_PROCESSED / "dataset.npz"  # X, y, pessoa (gerado)

DIR_MODELOS = RAIZ_PROJETO / "models"
ARQ_MODELO = DIR_MODELOS / "classificador.joblib"
ARQ_MODELO_INFO = DIR_MODELOS / "classificador_info.json"
ARQ_HAND_LANDMARKER = DIR_MODELOS / "hand_landmarker.task"
ARQ_POSE_LANDMARKER = DIR_MODELOS / "pose_landmarker_lite.task"

DIR_CONFIG = RAIZ_PROJETO / "config"
ARQ_FRASES = DIR_CONFIG / "frases.json"

DIR_REPORTS = RAIZ_PROJETO / "reports"

# Links oficiais dos modelos do MediaPipe (baixados para a pasta models/)
URL_HAND_LANDMARKER = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
URL_POSE_LANDMARKER = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)

# =============================================================================
# Vocabulário
# =============================================================================

# Identificadores dos sinais. Usamos apenas letras sem acento (ex.: "NAO") porque
# esses nomes também são nomes de pastas em data/raw/, e acentos em nomes de
# arquivos causam problemas entre Windows, Linux e macOS.
SINAIS = [
    "OI",
    "EU",
    "MEU",
    "NOME",
    "BOM",
    "DIA",
    "OBRIGADO",
    "SIM",
    "NAO",
    "AJUDA",
]

# Classe especial "nenhum sinal" (mãos paradas, gestos aleatórios).
CLASSE_NADA = "_NADA"

# Todas as classes que o modelo aprende.
CLASSES = SINAIS + [CLASSE_NADA]

# Como cada identificador aparece na tela (glosa). Sinais ausentes aqui são
# exibidos com o próprio identificador.
ROTULOS_EXIBICAO = {
    "NAO": "NÃO",
}

# =============================================================================
# Câmera
# =============================================================================

# Índice da webcam (0 = câmera padrão). Pode ser trocado sem editar este
# arquivo, com a variável de ambiente LIBRAS_CAMERA (ex.: LIBRAS_CAMERA=1).
INDICE_CAMERA = int(os.environ.get("LIBRAS_CAMERA", "0"))
LARGURA_CAMERA = 640
ALTURA_CAMERA = 480
ESPELHAR_IMAGEM = True  # mostra a imagem como um espelho (mais natural)
MAX_FALHAS_LEITURA = 30  # falhas seguidas de leitura antes de considerar a câmera perdida

# =============================================================================
# MediaPipe
# =============================================================================

NUM_MAOS = 2
CONFIANCA_DETECCAO_MAO = 0.5
CONFIANCA_PRESENCA_MAO = 0.5
CONFIANCA_RASTREAMENTO_MAO = 0.5
CONFIANCA_DETECCAO_POSE = 0.5

# Convenção de lateralidade: o MediaPipe classifica "Right"/"Left" supondo que a
# imagem está espelhada (como uma selfie). Como espelhamos a imagem
# (ESPELHAR_IMAGEM = True), "Right" corresponde à mão direita real da pessoa.
# Coleta e tempo real passam pelo mesmo extrator, então a convenção é sempre a
# mesma nos dois modos.
#
# Validação (Fase 1): levante só a mão DIREITA diante da câmera; a tela deve
# mostrar "Mão direita". Se mostrar "Mão esquerda", mude para True.
TROCAR_LADOS = False

# =============================================================================
# Interface
# =============================================================================

NOME_JANELA = "Vis-oLibras"
TECLAS_SAIR = ("q", "Q", "\x1b")  # Q ou ESC
JANELA_FPS = 30                    # nº de frames usados na média do FPS
SEGUNDOS_SEM_MAO_DICA = 3.0        # tempo sem mãos até mostrar dicas na tela

# =============================================================================
# Layout dos landmarks crus (formato de cada linha dos arquivos .npy)
# =============================================================================

N_PONTOS_MAO = 21
N_PONTOS_POSE = 33
N_COORDS = 3  # x, y, z

TAM_MAO = N_PONTOS_MAO * N_COORDS    # 63
TAM_POSE = N_PONTOS_POSE * N_COORDS  # 99

# Índices das colunas de cada linha (um frame):
# [timestamp | mão direita (63) | mão esquerda (63) | flags (2) | pose (99)]
COL_TIMESTAMP = 0
COL_MAO_DIREITA = slice(1, 1 + TAM_MAO)                       # 1..63
COL_MAO_ESQUERDA = slice(1 + TAM_MAO, 1 + 2 * TAM_MAO)        # 64..126
COL_FLAGS = slice(1 + 2 * TAM_MAO, 3 + 2 * TAM_MAO)           # 127..128
COL_POSE = slice(3 + 2 * TAM_MAO, 3 + 2 * TAM_MAO + TAM_POSE)  # 129..227
TAM_FRAME_BRUTO = 3 + 2 * TAM_MAO + TAM_POSE                  # 228

# Pontos da pose usados na normalização (numeração oficial do MediaPipe Pose)
POSE_NARIZ = 0
POSE_OMBRO_ESQUERDO = 11
POSE_OMBRO_DIREITO = 12

# =============================================================================
# Coleta de dados
# =============================================================================

DURACAO_AMOSTRA = 1.5          # segundos gravados por amostra
CONTAGEM_REGRESSIVA = 3        # segundos antes de começar a gravar
AMOSTRAS_POR_SESSAO = 40       # meta exibida na tela durante a coleta
MIN_PCT_FRAMES_COM_MAO = 0.7   # descarta amostra com mãos em menos de 70% dos frames

# =============================================================================
# Pré-processamento (features)
# =============================================================================

T_FRAMES = 20        # quantidade de frames após a reamostragem de cada janela
VERSAO_FEATURES = 1  # incrementar sempre que o pré-processamento mudar

# Vetor por frame: mão direita (63) + mão esquerda (63) + flags (2) + nariz (3)
TAM_FEATURES_FRAME = 2 * TAM_MAO + 2 + N_COORDS    # 131
TAM_FEATURES_JANELA = T_FRAMES * TAM_FEATURES_FRAME  # 2620

# =============================================================================
# Treinamento
# =============================================================================

SEMENTE = 42                   # reprodutibilidade
FRACAO_PESSOAS_TESTE = 0.25    # fração de pessoas separadas só para teste
N_ARVORES = 300                # RandomForest (modelo padrão do MVP)

# =============================================================================
# Reconhecimento em tempo real
# =============================================================================

DURACAO_JANELA = DURACAO_AMOSTRA  # janela deslizante igual à duração da amostra
DURACAO_MINIMA_JANELA = 1.2       # só classifica com pelo menos isso no buffer
PASSO_INFERENCIA = 5              # classifica a cada N frames
MIN_PCT_MAOS_JANELA = 0.5         # abaixo disso a janela é tratada como _NADA

# Estabilizador (anti-repetição)
LIMIAR_CONFIANCA = 0.75  # confiança mínima para aceitar uma previsão
N_CONSECUTIVAS = 3       # mesmo sinal em N previsões seguidas
COOLDOWN_S = 1.0         # tempo ignorando previsões após emitir uma palavra

# =============================================================================
# Formação de frases
# =============================================================================

PAUSA_FRASE_S = 2.5  # segundos sem novas palavras para encerrar a frase
MAX_PALAVRAS = 8     # limite de palavras por frase

# =============================================================================
# Voz (Text-to-Speech)
# =============================================================================

IDIOMA_VOZ = "pt"           # escolhe uma voz do sistema cujo idioma contenha isto
TAXA_FALA = 170             # velocidade da fala (palavras por minuto, aprox.)
FALAR_CADA_PALAVRA = False  # True: fala também cada palavra ao ser reconhecida


# =============================================================================
# Funções auxiliares
# =============================================================================

def rotulo_exibicao(sinal: str) -> str:
    """Retorna o texto usado na tela para um identificador de sinal."""
    return ROTULOS_EXIBICAO.get(sinal, sinal)


def garantir_diretorios() -> None:
    """Cria as pastas de dados, modelos e relatórios, caso não existam."""
    for pasta in (DIR_RAW, DIR_PROCESSED, DIR_MODELOS, DIR_REPORTS):
        pasta.mkdir(parents=True, exist_ok=True)
    for classe in CLASSES:
        (DIR_RAW / classe).mkdir(parents=True, exist_ok=True)


def _resumo() -> str:
    linhas = [
        f"Raiz do projeto : {RAIZ_PROJETO}",
        f"Dataset (raw)   : {DIR_RAW}",
        f"Dataset final   : {ARQ_DATASET}",
        f"Modelo          : {ARQ_MODELO}",
        f"Câmera          : {INDICE_CAMERA} ({LARGURA_CAMERA}x{ALTURA_CAMERA})",
        f"Frames/janela   : {T_FRAMES} (janela de {DURACAO_JANELA}s)",
        f"Confiança mín.  : {LIMIAR_CONFIANCA}",
        f"Classes ({len(CLASSES)})    : {', '.join(CLASSES)}",
    ]
    return "\n".join(linhas)


if __name__ == "__main__":
    garantir_diretorios()
    print(_resumo())
