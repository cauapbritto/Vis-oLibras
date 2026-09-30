"""Configuração central do projeto Librahin.

TODAS as constantes do sistema ficam aqui: nenhum "número mágico" deve aparecer
espalhado pelos outros módulos. Os caminhos são calculados a partir da pasta
raiz do projeto, então o projeto funciona em qualquer computador, independente
de onde foi clonado ou de qual pasta o script é executado.

Para conferir a configuração atual:

    python -m libras.config
"""

import os
import unicodedata
from pathlib import Path

# =============================================================================
# Caminhos (sempre relativos à raiz do projeto)
# =============================================================================

# src/libras/config.py -> parents[0]=libras, [1]=src, [2]=raiz do projeto
RAIZ_PROJETO = Path(__file__).resolve().parents[2]

# Pasta do dataset. Pode ser trocada pela variável de ambiente LIBRAS_DATA
# (ex.: um drive compartilhado pelo grupo); por padrão, data/ do projeto.
DIR_DATA = Path(os.environ.get("LIBRAS_DATA", RAIZ_PROJETO / "data"))
DIR_RAW = DIR_DATA / "raw"                  # uma pasta por sinal, um .npy por amostra
DIR_PROCESSED = DIR_DATA / "processed"
ARQ_METADATA = DIR_DATA / "metadata.csv"    # índice de todas as amostras gravadas
ARQ_DATASET = DIR_PROCESSED / "dataset.npz"  # X, y, pessoa (gerado)

DIR_MODELOS = RAIZ_PROJETO / "models"
ARQ_MODELO = DIR_MODELOS / "classificador.joblib"
ARQ_MODELO_INFO = DIR_MODELOS / "classificador_info.json"
ARQ_CLASSES = DIR_MODELOS / "classes.json"  # rótulos na ordem das saídas do modelo
ARQ_HAND_LANDMARKER = DIR_MODELOS / "hand_landmarker.task"
ARQ_POSE_LANDMARKER = DIR_MODELOS / "pose_landmarker_lite.task"

# Tabela de frases (sinais -> português), editável no Bloco de Notas.
ARQ_FRASES = RAIZ_PROJETO / "frases.txt"

# Ícone do aplicativo (gerado por scripts/desenvolvimento/gerar_icone.py)
DIR_RECURSOS = Path(__file__).resolve().parent / "recursos"
ARQ_ICONE_PNG = DIR_RECURSOS / "icone.png"
ARQ_ICONE_ICO = DIR_RECURSOS / "icone.ico"

DIR_REPORTS = RAIZ_PROJETO / "reports"
DIR_TESTES = DIR_REPORTS / "testes"  # CSVs dos testes controlados (teste_controlado.py)

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
# Alfabeto manual (datilologia), para soletrar nomes e palavras fora do
# vocabulário. As letras são OPCIONAIS: entram no modelo só as que forem
# gravadas, e letras seguidas viram uma palavra soletrada ("C A U A" -> "Caua").
# "Ç" é gravado na pasta C_CEDILHA (nomes de pasta sem acento).
LETRAS = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + ["C_CEDILHA"]

CLASSES = SINAIS + LETRAS + [CLASSE_NADA]          # tudo o que pode ser gravado e treinado
CLASSES_OBRIGATORIAS = SINAIS + [CLASSE_NADA]      # o que o modelo precisa ter (sem avisos pelas letras)

# Como cada identificador aparece na tela (glosa). Sinais ausentes aqui são
# exibidos com o próprio identificador.
ROTULOS_EXIBICAO = {
    "NAO": "NÃO",
    "C_CEDILHA": "Ç",
}

# =============================================================================
# Câmera
# =============================================================================

# Índice da webcam (0 = câmera padrão). Pode ser trocado sem editar este
# arquivo, com a variável de ambiente LIBRAS_CAMERA (ex.: LIBRAS_CAMERA=1).
def _indice_camera_do_ambiente() -> int:
    valor = os.environ.get("LIBRAS_CAMERA", "0")
    try:
        return int(valor)
    except ValueError:
        print(f"[AVISO] LIBRAS_CAMERA='{valor}' não é um número; usando a câmera 0.")
        return 0


INDICE_CAMERA = _indice_camera_do_ambiente()
LARGURA_CAMERA = 640
ALTURA_CAMERA = 480
ESPELHAR_IMAGEM = True  # mostra a imagem como um espelho (mais natural)
MAX_FALHAS_LEITURA = 50  # falhas seguidas (~10 ms entre elas) antes de considerar a câmera perdida

# =============================================================================
# MediaPipe
# =============================================================================

NUM_MAOS = 2
CONFIANCA_DETECCAO_MAO = 0.5
CONFIANCA_PRESENCA_MAO = 0.5
CONFIANCA_RASTREAMENTO_MAO = 0.5
CONFIANCA_DETECCAO_POSE = 0.5
MIN_VISIBILIDADE_OMBROS = 0.5  # abaixo disso a pose é descartada (ombros fora da imagem)
MAX_IDADE_POSE_S = 0.5  # reaproveita a última pose se a detecção falhar por até este tempo

# Convenção de lateralidade. Com a imagem espelhada, o MediaPipe (API Tasks)
# entrega os rótulos "Right"/"Left" INVERTIDOS: a mão direita da pessoa vem como
# "Left". As gravações e o modelo usam os rótulos como o MediaPipe entrega (coleta
# e tempo real passam pelo mesmo extrator, então a convenção é sempre a mesma e o
# reconhecimento não é afetado); só os NOMES e as cores mostrados na tela são
# corrigidos (extrator.lado_da_pessoa).
#
# Validação: levante só a mão DIREITA diante da câmera; a tela deve mostrar
# "Mão direita" (em verde). Se num computador aparecer "Mão esquerda", mude para False.
NOMES_MAOS_INVERTIDOS = True

# Troca os rótulos JÁ NA EXTRAÇÃO, ou seja, muda o que é GRAVADO. Não altere com
# a coleta em andamento: as gravações antigas e as novas ficariam incompatíveis.
# (Se usar True, use também NOMES_MAOS_INVERTIDOS = False.)
TROCAR_LADOS = False

# =============================================================================
# Interface
# =============================================================================

NOME_JANELA = "Librahin"
TECLAS_SAIR = ("q", "Q", "\x1b")  # Q ou ESC
JANELA_FPS = 30                    # nº de frames usados na média do FPS
SEGUNDOS_SEM_MAO_DICA = 3.0        # tempo sem mãos até mostrar dicas na tela

# =============================================================================
# Layout dos landmarks crus (formato de cada linha dos arquivos .npy)
# =============================================================================
#
# Coordenadas em "unidades da altura da imagem": y vai de 0 a 1 e x e z são
# multiplicados por largura/altura. Assim as distâncias não ficam distorcidas
# em câmeras com proporções diferentes (4:3, 16:9). Mão ausente = zeros com
# flag 0; pose ausente (ombros não visíveis) = zeros.

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

DURACAO_AMOSTRA = 1.5            # segundos gravados por amostra
CONTAGEM_REGRESSIVA = 3          # segundos antes da primeira gravação
INTERVALO_ENTRE_AMOSTRAS = 1.0   # pausa entre amostras na gravação contínua
AMOSTRAS_POR_SESSAO = 40         # meta de amostras por execução do coletor

# Critérios de amostra válida (usados na coleta e na análise do dataset)
MIN_FRAMES_AMOSTRA = 15          # ~10 fps no mínimo
MIN_PCT_FRAMES_COM_MAO = 0.7     # mãos em pelo menos 70% dos frames (exceto _NADA)
MIN_PCT_FRAMES_COM_OMBROS = 0.7  # ombros visíveis em pelo menos 70% dos frames

# Análise do dataset
MIN_AMOSTRAS_POR_CLASSE = 30     # abaixo disso a classe é marcada como "poucas amostras"
MIN_PESSOAS_POR_CLASSE = 2       # recomendado para o modelo generalizar
MAX_DESBALANCEAMENTO = 3.0       # razão máxima entre a maior e a menor classe
LIMIAR_OUTLIER = 3.5             # desvios (MAD) acima da mediana da classe

# =============================================================================
# Pré-processamento (features)
# =============================================================================

T_FRAMES = 20  # quantidade de frames após a reamostragem de cada janela

# Versão das features. Incrementar sempre que o pré-processamento mudar.
#   1: janela posicional (forma + posição de cada mão em cada um dos T frames)
#   2: versão 1 + características de movimento (velocidade, trajetória,
#      direção, abertura da mão, distância entre as mãos) - ver temporal.py
# Modelos treinados na versão 1 continuam funcionando: o tempo real usa a
# versão gravada no modelo, não a daqui.
VERSAO_FEATURES = 2

# Vetor por frame, para cada mão (direita, depois esquerda):
#   forma (63): pontos relativos ao punho, divididos pelo tamanho da palma
#               -> não depende da posição, da distância nem do tamanho da mão
#   posição (2): punho relativo ao centro dos ombros, dividido pela largura dos
#               ombros -> onde o sinal é feito em relação ao corpo
# e, no final, as flags de presença (2).
TAM_FORMA_MAO = TAM_MAO   # 63
TAM_POSICAO_MAO = 2       # x, y
TAM_FEATURES_FRAME = 2 * (TAM_FORMA_MAO + TAM_POSICAO_MAO) + 2  # 132
TAM_FEATURES_POSICIONAIS = T_FRAMES * TAM_FEATURES_FRAME         # 2640 (versão 1)

# Características de movimento (versão 2), por mão:
#   velocidade do punho entre frames (2 x (T-1)), deslocamento total (2),
#   comprimento da trajetória (1), amplitude x/y (2), mudanças de direção x/y (2),
#   abertura da mão em cada frame (T) e sua variação (1)  -> 3T + 6
# e a distância entre os punhos em cada frame (T).
TAM_MOVIMENTO_MAO = 3 * T_FRAMES + 6                   # 66
TAM_MOVIMENTO = 2 * TAM_MOVIMENTO_MAO + T_FRAMES       # 152
TAM_FEATURES_JANELA = TAM_FEATURES_POSICIONAIS + TAM_MOVIMENTO  # 2792 (versão atual)

LIMIAR_MOVIMENTO = 0.02  # velocidade mínima (larguras de ombro por frame) para contar direção
PONTAS_DEDOS = (4, 8, 12, 16, 20)  # polegar, indicador, médio, anelar, mínimo

# Pontos da mão usados como referência de tamanho (punho -> base do dedo médio)
MAO_PUNHO = 0
MAO_BASE_DEDO_MEDIO = 9

MIN_LARGURA_OMBROS = 0.05  # evita divisão por quase zero (pose mal detectada)
MIN_TAMANHO_PALMA = 1e-4
MAX_LACUNA_MAO = 3         # frames seguidos sem uma mão que são interpolados

# =============================================================================
# Treinamento
# =============================================================================

SEMENTE = 42          # random_state: mesmos dados + mesma semente = mesmo resultado
FRACAO_TESTE = 0.25   # fração das amostras separada para teste (estratificada por sinal)
N_FOLDS_CV = 5        # validação cruzada no treino para escolher o algoritmo
N_ARVORES = 300       # Random Forest

# =============================================================================
# Reconhecimento em tempo real
# =============================================================================

DURACAO_JANELA = DURACAO_AMOSTRA  # janela deslizante igual à duração da amostra
DURACAO_MINIMA_JANELA = 1.2       # só classifica com pelo menos isso no buffer
PASSO_INFERENCIA = 5              # classifica a cada N frames
MIN_PCT_MAOS_JANELA = 0.5         # abaixo disso a janela é tratada como _NADA

# Estabilizador (anti-repetição). Uma palavra só é aceita quando:
#   1. a confiança da previsão é >= LIMIAR_CONFIANCA;
#   2. o mesmo sinal aparece em N_CONSECUTIVAS previsões seguidas;
#   3. já passou COOLDOWN_S desde a última palavra aceita (qualquer uma);
#   4. se for a MESMA palavra da anterior: já passou COOLDOWN_MESMO_SINAL_S e,
#      com EXIGIR_LIBERACAO, a pessoa "soltou" o sinal (_NADA ou mãos fora da
#      imagem) entre as duas. Assim, segurar NOME por 10 s gera um único NOME.
# Com PASSO_INFERENCIA = 5 a ~25 fps, são ~5 previsões por segundo: 3 seguidas
# significam o sinal estável por ~0,6 s.
LIMIAR_CONFIANCA = 0.75
N_CONSECUTIVAS = 3
COOLDOWN_S = 1.0
COOLDOWN_MESMO_SINAL_S = 2.0
EXIGIR_LIBERACAO = True

# =============================================================================
# Formação de frases
# =============================================================================

PAUSA_FRASE_S = 2.5        # segundos sem novas palavras para encerrar a frase
FINALIZAR_POR_PAUSA = True # False: a frase só é encerrada pelo botão/tecla
MAX_PALAVRAS = 8           # limite de palavras por frase
JANELA_REPETICAO_S = 1.5   # mesma palavra de novo em menos que isso = repetição involuntária

# Tabela de frases (frases.txt): converte sequências cadastradas pelo grupo em
# português ("EU NOME" -> "Meu nome é"). O que não estiver na tabela continua
# como glosa (a sequência de sinais). Ver src/libras/traducao.py.
USAR_TABELA_FRASES = True  # False: volta ao modo só glosa
MOSTRAR_GLOSA = True       # mostra a sequência de sinais em letra pequena, embaixo do português

# =============================================================================
# Créditos (janela "Sobre" da aplicação)
# =============================================================================

TITULO_TRABALHO = ("Tradução de Libras para Texto e Voz utilizando "
                   "Visão Computacional e Inteligência Artificial")
EQUIPE = (
    "Cauã Pedrozo Brito",
    "Adryel da Assunção Rocha",
    "Alber Alberguini Cabral",
    "João Francisco da Silva Malaquias",
)
ORIENTADOR = "Éder Lemes"
CURSO = "Tecnologia em Análise e Desenvolvimento de Sistemas"

# =============================================================================
# Teclas da aplicação em tempo real (além de Q/ESC para sair)
# =============================================================================

TECLAS_LIMPAR = ("c", "C")        # limpa a sequência atual
TECLAS_APAGAR_ULTIMA = ("\x08", "\x7f")  # BACKSPACE (Windows/Linux e macOS)
TECLAS_FINALIZAR = (" ",)         # ESPAÇO: encerra a frase agora

# =============================================================================
# Testes controlados (scripts/desenvolvimento/teste_controlado.py)
# =============================================================================

TESTE_REPETICOES = 10     # vezes que cada participante faz cada sinal
TESTE_CONTAGEM_S = 2.0    # contagem regressiva antes de cada tentativa
TESTE_JANELA_S = 5.0      # tempo máximo para o sinal ser reconhecido
TESTE_RESULTADO_S = 1.5   # tempo mostrando o resultado (D descarta nesse intervalo)

# =============================================================================
# Voz (Text-to-Speech)
# =============================================================================

# Voz offline e gratuita. Windows: vozes do sistema (System.Speech, pelo
# PowerShell), com o pyttsx3 como alternativa; Linux: pyttsx3 (eSpeak);
# macOS: o comando "say" (o pyttsx3 trava fora da thread principal no Mac).
MOTOR_VOZ = "auto"           # "auto", "windows", "pyttsx3" ou "comando" (say/espeak-ng)
IDIOMAS_VOZ = ("pt-br", "pt_br", "brazil", "pt")  # preferência, do mais específico
TAXA_FALA = 170              # velocidade da fala (palavras por minuto, aprox.)
FALAR_AO_FINALIZAR = True    # fala a frase quando ela é encerrada
FALAR_CADA_PALAVRA = False   # True: fala também cada palavra ao ser confirmada
POLITICA_VOZ = "ignorar"     # fala pedida durante outra: "ignorar" ou "enfileirar"


# =============================================================================
# Funções auxiliares
# =============================================================================

def identificador_sinal(texto: str) -> str:
    """Converte o que o usuário digitou em identificador: 'não' -> 'NAO', 'ç' -> 'C_CEDILHA'."""
    if texto.strip().upper() == "Ç":
        return "C_CEDILHA"
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().upper()


def eh_letra(sinal: str | None) -> bool:
    """True para as letras do alfabeto manual (A..Z e C_CEDILHA)."""
    return sinal in _LETRAS


_LETRAS = frozenset(LETRAS)


def rotulo_exibicao(sinal: str) -> str:
    """Retorna o texto usado na tela para um identificador de sinal."""
    return ROTULOS_EXIBICAO.get(sinal, sinal)


def garantir_diretorios() -> None:
    """Cria as pastas de dados, modelos e relatórios, caso não existam."""
    for pasta in (DIR_RAW, DIR_PROCESSED, DIR_MODELOS, DIR_REPORTS):
        pasta.mkdir(parents=True, exist_ok=True)
    for classe in CLASSES_OBRIGATORIAS:  # as pastas das letras são criadas na primeira gravação
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
