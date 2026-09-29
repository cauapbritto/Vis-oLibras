# Plano Técnico — Tradução de Libras para Texto e Voz

> **Projeto:** Tradução de Libras para Texto e Voz utilizando Visão Computacional e Inteligência Artificial
> **Versão do documento:** 1.0 (MVP)
> **Status:** planejamento — nenhum código implementado ainda

---

## 0. Resumo das decisões

| Tema | Decisão para o MVP | Por quê |
|---|---|---|
| Linguagem | Python 3.11 | Compatível com MediaPipe, OpenCV e scikit-learn |
| Captura de vídeo | OpenCV (`cv2.VideoCapture`) | Padrão de mercado, simples |
| Landmarks | MediaPipe **Tasks** (`HandLandmarker` + `PoseLandmarker`) | Mãos (forma) + ombros/rosto (posição do sinal em relação ao corpo) |
| Unidade de reconhecimento | **Janela de ~1,5 s** de vídeo (não um frame isolado) | OI, OBRIGADO, AJUDA, NÃO etc. têm **movimento** |
| Modelo | **scikit-learn** (RandomForest como base; SVM/MLP para comparar) | Treina em segundos, funciona com poucos dados, fácil de explicar |
| Evolução do modelo | Keras (LSTM/GRU) na fase 2, se necessário | Só vale a pena com mais dados/vocabulário |
| Anti-repetição | Filtro de confiança + estabilidade + *cooldown* + "soltar" o sinal | Evita "OI OI OI OI…" |
| Frases | Lista de palavras + pausa encerra a frase + dicionário de frases prontas | Simples e previsível |
| Voz | `pyttsx3` (offline) em *thread* separada | Gratuito, local, não trava o vídeo |
| Armazenamento | `.npy` por amostra (dados brutos) + `metadata.csv` | Fácil de ler, reprocessar e versionar |
| Configuração | Um único `config.py` | Sem YAML, sem dependências extras |

---

## 1. Arquitetura geral

O sistema é dividido em **dois modos de uso** que compartilham os mesmos módulos:

1. **Modo offline (preparação):** coletar dados → montar dataset → treinar → avaliar.
2. **Modo tempo real (uso):** câmera → reconhecimento → texto → voz.

### 1.1 Fluxo em tempo real

```
┌──────────┐   frame BGR   ┌────────────────┐  landmarks   ┌──────────────────┐
│  Webcam  │ ────────────► │ OpenCV         │ ───────────► │ MediaPipe        │
│          │               │ (camera.py)    │   (RGB)      │ Hands + Pose     │
└──────────┘               └────────────────┘              │ (extrator.py)    │
                                                           └────────┬─────────┘
                                                                    │ vetor de 1 frame
                                                                    ▼
                                                  ┌─────────────────────────────────┐
                                                  │ Buffer temporal (últimos 1,5 s) │
                                                  │ (features.py)                   │
                                                  └────────────────┬────────────────┘
                                                                   │ a cada ~5 frames
                                                                   ▼
                                  ┌───────────────────────────────────────────────────┐
                                  │ Pré-processamento: normalizar + reamostrar p/ T=20 │
                                  │ (features.py)                                      │
                                  └────────────────────────┬──────────────────────────┘
                                                           ▼
                                        ┌───────────────────────────────────┐
                                        │ Classificador (scikit-learn)       │
                                        │ predict_proba → (sinal, confiança) │
                                        │ (classificador.py)                 │
                                        └──────────────────┬────────────────┘
                                                           ▼
                                        ┌───────────────────────────────────┐
                                        │ Estabilizador (anti-repetição)     │
                                        │ (estabilizador.py)                 │
                                        └──────────────────┬────────────────┘
                                                           │ palavra confirmada
                                                           ▼
                                        ┌───────────────────────────────────┐
                                        │ Montador de frase                  │
                                        │ (frase.py)                         │
                                        └───────┬───────────────────┬───────┘
                                                │ texto             │ frase pronta
                                                ▼                   ▼
                                      ┌──────────────────┐  ┌──────────────────┐
                                      │ Tela (OpenCV)    │  │ Voz (pyttsx3)    │
                                      │ (desenho.py)     │  │ thread separada  │
                                      └──────────────────┘  │ (voz.py)         │
                                                            └──────────────────┘
```

### 1.2 Fluxo offline

```
coletar_dados.py ──► data/raw/<SINAL>/*.npy + data/metadata.csv
                              │
construir_dataset.py ─────────┘──► data/processed/dataset.npz  (X, y, pessoa)
                                              │
treinar_modelo.py ────────────────────────────┘──► models/classificador.joblib
                                                             │
avaliar_modelo.py ───────────────────────────────────────────┘──► reports/ (métricas, matriz de confusão)
```

### 1.3 Princípio de projeto

Cada módulo tem **uma responsabilidade** e conversa com os outros por dados simples
(arrays NumPy, strings, listas). Assim é possível trocar uma peça (ex.: o modelo ou o motor
de voz) sem mexer no resto.

---

## 2. Estrutura de diretórios

```
Vis-oLibras/
├── README.md                    # como instalar e rodar
├── requirements.txt             # dependências com versões fixadas
├── pyproject.toml               # permite `pip install -e .` (importar `libras` de qualquer pasta)
├── .gitignore                   # ignora venv/, data/raw (opcional), models/*.joblib grandes
│
├── docs/
│   ├── ARQUITETURA.md           # este documento
│   └── SINAIS.md                # descrição/foto/link de referência de cada sinal escolhido
│
├── src/
│   └── libras/                  # pacote principal (módulos pequenos e planos)
│       ├── __init__.py
│       ├── config.py            # TODAS as constantes: sinais, limiares, caminhos, T, fps...
│       ├── camera.py            # abrir webcam, ler frame, espelhar, liberar
│       ├── extrator.py          # MediaPipe: frame → landmarks crus (mãos + pose)
│       ├── features.py          # normalização, vetor por frame, buffer, reamostragem
│       ├── classificador.py     # carregar modelo, prever (sinal, confiança)
│       ├── estabilizador.py     # regras anti-repetição (máquina de estados)
│       ├── frase.py             # acumular palavras, formar frase, dicionário de frases
│       ├── voz.py               # TTS em thread com fila
│       ├── desenho.py           # desenhar landmarks, texto, FPS, barra de confiança
│       └── metricas.py          # cronômetro por etapa, FPS, log CSV de latência
│
├── scripts/                     # pontos de entrada (o aluno roda estes)
│   ├── testar_deteccao.py       # Fase 1: valida webcam → OpenCV → MediaPipe (sem reconhecimento)
│   ├── coletar_dados.py         # grava amostras de um sinal
│   ├── visualizar_amostra.py    # reproduz uma amostra gravada (conferência de qualidade)
│   ├── construir_dataset.py     # data/raw → data/processed/dataset.npz
│   ├── treinar_modelo.py        # treina e salva o modelo
│   ├── avaliar_modelo.py        # relatório de precisão + matriz de confusão
│   └── executar.py              # aplicação em tempo real
│
├── config/
│   └── frases.json              # combinações de palavras → frase em português
│
├── data/
│   ├── raw/                     # uma pasta por sinal, um .npy por amostra
│   │   ├── OI/
│   │   ├── EU/
│   │   ├── ...
│   │   ├── NAO/                 # identificadores sem acento (exibido como "NÃO")
│   │   └── _NADA/               # classe "nenhum sinal" (muito importante!)
│   ├── processed/
│   │   └── dataset.npz
│   └── metadata.csv             # índice de todas as amostras
│
├── models/
│   ├── hand_landmarker.task     # modelo do MediaPipe (baixado)
│   ├── pose_landmarker_lite.task
│   ├── classificador.joblib     # modelo treinado
│   └── classificador_info.json  # classes, data, acurácia, parâmetros de features
│
├── reports/                     # saídas de avaliação (gerado)
│   ├── classification_report.txt
│   ├── matriz_confusao.png
│   └── latencia_<data>.csv
│
└── tests/                       # testes da lógica pura (sem câmera)
    ├── test_features.py
    ├── test_estabilizador.py
    └── test_frase.py
```

**Regra simples:** `src/libras/` contém *lógica reutilizável*; `scripts/` contém *programas
que o usuário executa* e apenas "cola" os módulos.

---

## 3. Tecnologias utilizadas

| Camada | Tecnologia | Papel |
|---|---|---|
| Linguagem | **Python 3.11** | Tudo |
| Captura / UI | **OpenCV** | Ler webcam, desenhar na tela, capturar teclado |
| Visão computacional | **MediaPipe Tasks** | 21 landmarks por mão + landmarks de pose |
| Cálculo | **NumPy** | Vetores, normalização, reamostragem |
| Aprendizado de máquina | **scikit-learn** | Classificador, validação, métricas |
| Persistência do modelo | **joblib** | Salvar/carregar o modelo treinado |
| Voz | **pyttsx3** | Text-to-Speech offline |
| Gráficos (avaliação) | **matplotlib** | Matriz de confusão |
| Testes | **pytest** | Testes de unidade |

### 3.1 Por que scikit-learn e não TensorFlow/Keras no MVP?

| Critério | scikit-learn (RandomForest/SVM) | Keras (LSTM) |
|---|---|---|
| Dados necessários | ~40 amostras/sinal já funcionam | Normalmente precisa de mais |
| Tempo de treino | segundos (CPU) | minutos, ajuste de épocas |
| Instalação | leve | pesada (~500 MB), conflitos de versão |
| Curva de aprendizado | baixa | média/alta |
| Explicabilidade p/ banca | alta | média |

Como o vocabulário é pequeno (10 sinais + "nada") e as janelas têm tamanho fixo, um
classificador clássico sobre a janela "achatada" resolve bem. A arquitetura deixa a porta
aberta para trocar por Keras depois (ver seção 13).

### 3.2 Por que MediaPipe Tasks (e não `mp.solutions`)?

A API antiga `mediapipe.solutions` (Hands/Holistic) foi **removida** (não existe no
MediaPipe 1.x). A API
**Tasks** (`mediapipe.tasks.python.vision.HandLandmarker` e `PoseLandmarker`) é a
suportada. Ela exige baixar arquivos `.task` (modelos) para a pasta `models/` — o README
terá os links oficiais.

### 3.3 Por que usar a pose e não só as mãos?

Vários sinais do vocabulário diferenciam-se pela **posição da mão em relação ao corpo**:

- **EU** × **MEU**: apontar para o peito × mão aberta no peito
- **OBRIGADO**: começa próximo à testa/rosto
- **BOM**: próximo à boca

Com os ombros e o nariz (da pose), conseguimos expressar a posição da mão *relativa ao
corpo*, o que também torna o sistema independente da distância até a câmera.

---

## 4. Bibliotecas necessárias

`requirements.txt` (versões serão **fixadas** com `pip freeze` após a primeira instalação
que funcionar em todas as máquinas do grupo):

```
opencv-python
mediapipe
numpy
scikit-learn
joblib
pyttsx3
matplotlib
pytest
```

Observações de instalação:

- Usar **ambiente virtual** (`python -m venv .venv`).
- **Windows:** `pyttsx3` usa as vozes SAPI5. Para voz em português, instalar o pacote de
  idioma "Português (Brasil)" com recurso de fala (voz "Maria"/"Daniel").
- **Linux:** `pyttsx3` usa eSpeak: `sudo apt install espeak-ng` (voz robótica, mas funciona).
- **Linux:** o MediaPipe 1.x precisa de bibliotecas gráficas: `sudo apt install libegl1 libgles2`.
- **macOS:** usa a voz nativa do sistema (ex.: "Luciana").

---

## 5. Coleta de dados

### 5.1 Padronização dos sinais (antes de gravar!)

> **Identificadores:** os nomes das classes (e das pastas) não têm acento — `NAO` é
> exibido na tela como "NÃO" (`ROTULOS_EXIBICAO` no `config.py`). Acentos em nomes de
> pastas causam problemas entre Windows, Linux e macOS.

Libras tem **variações regionais**. Antes da coleta, o grupo escolhe **uma variante** de
cada sinal e documenta em `docs/SINAIS.md` (descrição + link de referência, ex.: Dicionário
de Libras do INES). Todos que gravarem devem fazer o sinal do mesmo jeito.

> Sinais que em Libras usam expressão facial/cabeça (ex.: SIM/NÃO com aceno) devem usar a
> variante **manual**, já que o MVP analisa mãos e posição, não o rosto.

### 5.2 Classe especial `_NADA`

Além dos 10 sinais, gravar a classe **`_NADA`**: mãos paradas, mãos descendo, coçar o rosto,
ajustar o óculos, gesticular aleatoriamente. Sem ela, o modelo **sempre** escolhe algum
sinal, mesmo quando a pessoa não está sinalizando — é a maior fonte de falsos positivos.

### 5.3 Script `coletar_dados.py`

Uso: `python scripts/coletar_dados.py --sinal OI --pessoa ana`

Funcionamento:

1. Abre a câmera e mostra a imagem com os landmarks desenhados.
2. Usuário aperta **ESPAÇO** → contagem regressiva de 3 s na tela.
3. Grava **1,5 s** (`DURACAO_AMOSTRA` no config) de landmarks crus, com timestamp de cada frame.
4. Mostra "Amostra 12/40 salva" e volta ao passo 2. **Q** sai; **D** descarta a última.
5. Amostras em que as mãos não foram detectadas em mais de 30 % dos frames são descartadas
   automaticamente com aviso.

### 5.4 Quantidade e diversidade

| Item | Meta mínima |
|---|---|
| Amostras por sinal por pessoa | 30–40 |
| Pessoas diferentes | 3 ou mais (ideal: todo o grupo) |
| Amostras de `_NADA` | o dobro de um sinal comum |
| Variações | iluminação, roupa, fundo, distância (0,8–1,5 m), leve rotação |

Total estimado: 11 classes × 40 × 3 pessoas ≈ **1.300 amostras** → ~1 h de gravação
dividida entre o grupo.

`visualizar_amostra.py` permite reproduzir amostras como "esqueleto" para conferir e
apagar gravações ruins.

---

## 6. Armazenamento dos landmarks

### 6.1 Guardar o **bruto**, processar depois

Salvamos os landmarks **sem normalização**. Assim, se mudarmos a forma de
pré-processar, não é preciso regravar nada — basta rodar `construir_dataset.py` de novo.

### 6.2 Formato de cada amostra (`.npy`)

Arquivo: `data/raw/OI/ana_20260929_153012_007.npy` — um array `float32` de forma
**`(F, 1 + 126 + 2 + 99)`** onde `F` = número de frames gravados (~45 a 30 fps):

| Colunas | Conteúdo |
|---|---|
| 0 | timestamp em segundos (relativo ao início) |
| 1–63 | mão **direita**: 21 pontos × (x, y, z) |
| 64–126 | mão **esquerda**: 21 pontos × (x, y, z) |
| 127–128 | flags de presença (mão direita, mão esquerda) = 0/1 |
| 129–227 | pose: 33 pontos × (x, y, z) (usaremos só alguns, mas guardamos todos) |

Mão não detectada → zeros + flag 0.

> **Atenção à lateralidade:** com a imagem espelhada, o MediaPipe pode inverter
> "Left/Right". Definir em `config.py` a convenção e **usar a mesma na coleta e no tempo
> real** (ambos passam pelo mesmo `extrator.py`, então isso fica garantido).

### 6.3 `data/metadata.csv`

```
arquivo,sinal,pessoa,data_hora,num_frames,fps_medio,pct_frames_com_mao
raw/OI/ana_20260929_153012_007.npy,OI,ana,2026-09-29T15:30:12,46,30.4,0.96
```

Serve para contar amostras por classe/pessoa, filtrar gravações ruins e dividir
treino/teste **por pessoa**.

### 6.4 Dataset processado

`data/processed/dataset.npz` contém `X` (n_amostras × n_features), `y` (rótulos) e
`pessoa` (para validação). É gerado — pode ser apagado e recriado.

---

## 7. Treinamento do modelo

### 7.1 Pré-processamento (`features.py`) — idêntico no treino e no tempo real

Para **cada frame**:

1. **Origem no corpo:** subtrair de cada ponto das mãos o ponto médio entre os ombros.
2. **Escala:** dividir pela distância entre os ombros (invariante à distância da câmera).
3. Montar o vetor do frame: mão direita (63) + mão esquerda (63) + flags (2) +
   posição do nariz relativa (3) = **131 valores**.

Para **cada amostra/janela**:

4. **Reamostragem temporal** para **T = 20 frames** uniformemente espaçados no tempo
   (interpolação linear usando os timestamps). Isso torna o sistema independente do FPS
   da máquina (a câmera de um aluno pode rodar a 15 fps e a de outro a 30 fps).
5. **Achatar** → vetor de 20 × 131 = **2.620 features**.

Função única: `features.janela_para_vetor(frames_brutos) -> np.ndarray`. **Treino e tempo
real chamam exatamente a mesma função** — isso evita o erro mais comum desse tipo de
projeto.

### 7.2 Script `treinar_modelo.py`

1. Carrega `dataset.npz`.
2. Divide treino/teste **por pessoa** (`GroupShuffleSplit` ou uma pessoa separada só para
   teste). Dividir aleatoriamente por amostra infla a acurácia, porque amostras da mesma
   pessoa ficam muito parecidas.
3. Treina e compara 3 candidatos, todos com `Pipeline` do scikit-learn:
   - `RandomForestClassifier(n_estimators=300)` — **padrão do MVP**
   - `StandardScaler` + `SVC(kernel="rbf", probability=True)`
   - `StandardScaler` + `MLPClassifier(hidden_layer_sizes=(256, 128))`
4. Escolhe o de melhor **F1 macro** na validação por pessoa.
5. Retreina o escolhido com **todos** os dados e salva:
   - `models/classificador.joblib`
   - `models/classificador_info.json` (classes, T, DURACAO_JANELA, versão das features,
     métricas, data). O `executar.py` confere se os parâmetros batem com o `config.py`.

Tempo de treino esperado: poucos segundos a 1 minuto em notebook comum.

---

## 8. Classificação em tempo real (`executar.py`)

Laço principal (simplificado):

```
enquanto rodando:
    frame      = camera.ler()
    landmarks  = extrator.extrair(frame)             # MediaPipe
    buffer.adicionar(timestamp, landmarks)           # mantém só os últimos 1,5 s

    se frame_atual % PASSO_INFERENCIA == 0 e buffer tem >= 1,2 s:
        se mãos presentes na maior parte do buffer:
            vetor            = features.janela_para_vetor(buffer)
            sinal, confianca = classificador.prever(vetor)   # argmax de predict_proba
        senão:
            sinal, confianca = "_NADA", 1.0
        palavra = estabilizador.atualizar(sinal, confianca, agora)
        se palavra: frase.adicionar(palavra)

    se frase.pausa_detectada(agora): voz.falar(frase.finalizar())
    desenho.tela(frame, landmarks, sinal, confianca, frase.texto(), fps)
```

Detalhes:

- **Janela deslizante:** a cada `PASSO_INFERENCIA = 5` frames (~6 vezes por segundo a 30 fps)
  classificamos a janela dos últimos 1,5 s. Não precisa classificar todo frame.
- **Economia:** se não há mão na imagem, nem chama o classificador.
- **Tela:** mostra landmarks, sinal "candidato" com barra de confiança, frase em
  construção, FPS e latência.
- **Teclado:** `ESPAÇO` fala a frase agora · `BACKSPACE` apaga a última palavra ·
  `C` limpa · `Q` sai.

---

## 9. Evitando repetição da mesma palavra (`estabilizador.py`)

Como classificamos ~6 vezes por segundo, um único sinal de OI geraria "OI OI OI OI OI…".
Usamos **quatro regras simples**, em sequência:

| # | Regra | Parâmetro (config) | Efeito |
|---|---|---|---|
| 1 | **Limiar de confiança:** ignorar previsões com probabilidade baixa | `LIMIAR_CONFIANCA = 0.75` | Corta dúvidas |
| 2 | **Estabilidade:** exigir o mesmo sinal em *N* previsões seguidas | `N_CONSECUTIVAS = 3` | Corta "piscadas" do modelo |
| 3 | **Cooldown:** depois de emitir uma palavra, ignorar tudo por um tempo | `COOLDOWN_S = 1.0` | Dá tempo do gesto terminar |
| 4 | **Liberação:** para emitir a **mesma** palavra de novo, é preciso ter passado por `_NADA` (ou mãos fora da imagem) antes | — | Permite "SIM… SIM" intencional, mas não repetição acidental |

Após emitir, o **buffer é esvaziado** para que o fim do gesto anterior não contamine a
próxima janela.

Máquina de estados:

```
          confiança ≥ limiar e N iguais
  ┌────────┐ ─────────────────────────► ┌──────────┐
  │ OUVINDO│                            │ EMITIDO  │── emite palavra, limpa buffer
  └────────┘ ◄──── cooldown acabou ──── └──────────┘
       ▲         (e, se for a mesma palavra,
       │          só após ver _NADA)
```

Essa classe **não depende de câmera** — recebe `(sinal, confiança, tempo)` e devolve
`palavra | None` — então é fácil testar com `pytest`.

---

## 10. Formação de pequenas sequências (`frase.py`)

### 10.1 Regras

1. Cada palavra confirmada é **adicionada** à lista da frase atual.
2. **Pausa encerra a frase:** se passar `PAUSA_FRASE_S = 2.5` s sem novas palavras
   (normalmente com as mãos abaixadas), a frase é finalizada e enviada para a voz.
3. Limite de segurança: `MAX_PALAVRAS = 8`.
4. Correção manual: `BACKSPACE` remove a última palavra; `C` limpa.

### 10.2 De palavras para português (`config/frases.json`)

Libras tem gramática própria; o MVP **não** faz tradução gramatical. Usamos um
dicionário de combinações conhecidas; o que não estiver nele é exibido juntando as
palavras.

```json
{
  "OI":             "Oi!",
  "BOM DIA":        "Bom dia!",
  "OI BOM DIA":     "Oi, bom dia!",
  "MEU NOME":       "Meu nome é",
  "EU AJUDA":       "Eu preciso de ajuda.",
  "AJUDA":          "Ajuda!",
  "OBRIGADO":       "Obrigado!",
  "SIM":            "Sim.",
  "NAO":            "Não."
}
```

Algoritmo: procurar a **maior** sequência de palavras que exista no dicionário a partir do
início, substituir, continuar. Ex.: `OI BOM DIA OBRIGADO` → "Oi, bom dia! Obrigado!".
Fallback: `EU NÃO` → "Eu não".

Na tela: linha 1 = palavras reconhecidas (glosa, ex.: `OI · BOM · DIA`); linha 2 = frase em
português.

---

## 11. Conversão em voz (`voz.py`)

- Motor padrão: **pyttsx3** — gratuito, **offline**, usa a voz do sistema operacional.
- Seleção automática de uma voz cujo idioma contenha `pt` (configurável em `config.py`);
  velocidade `TAXA_FALA ≈ 170`.
- **Não pode travar o vídeo:** a fala roda numa **thread separada** que consome uma
  **fila** (`queue.Queue`). O laço principal só faz `voz.falar(texto)` e segue.
- Robustez: em algumas versões do Windows, `runAndWait()` repetido trava; a *thread*
  cria o motor uma vez e, se houver falha, recria o motor para cada fala.
- **Quando falar:** por padrão, a **frase inteira** ao final da pausa. Opção em config
  `FALAR_CADA_PALAVRA = False` para falar também cada palavra ao ser reconhecida (bom para
  demonstração).

Interface simples, para trocar o motor no futuro:

```
class MotorVoz:  falar(texto: str) -> None ;  encerrar() -> None
```

Alternativas futuras: **Piper TTS** (offline, voz neural pt-BR de boa qualidade) ou
**gTTS** (voz boa, mas exige internet).

---

## 12. Como medir precisão e tempo de resposta

### 12.1 Precisão offline (`avaliar_modelo.py`)

- **Validação por pessoa (Leave-One-Person-Out):** treina com todas as pessoas menos uma e
  testa na que ficou de fora; repete para cada pessoa; tira a média. Mede se o sistema
  funciona para **alguém que ele nunca viu**.
- Métricas (scikit-learn): **acurácia**, **precisão, recall e F1 por classe**
  (`classification_report`) e **matriz de confusão** (salva em `reports/matriz_confusao.png`).
- A matriz mostra quais sinais se confundem (ex.: EU × MEU) → orienta regravação ou
  mudança de features.

### 12.2 Precisão em tempo real (protocolo de teste manual)

O que importa na prática é o sistema completo (com estabilizador). Protocolo:

1. Cada participante faz **cada sinal 10 vezes**, em ordem aleatória, e 1 minuto
   **sem sinalizar** (conversando/gesticulando).
2. Registrar numa planilha: acerto, erro (qual palavra saiu), não detectado.
3. Calcular: **taxa de acerto**, **taxa de não detecção** e **falsos positivos por minuto**
   (palavras emitidas no minuto sem sinalizar).

### 12.3 Tempo de resposta (`metricas.py`)

Cronometrar cada etapa com `time.perf_counter()` e gravar em `reports/latencia_<data>.csv`:

| Métrica | Como medir |
|---|---|
| **FPS** | média móvel de frames processados por segundo |
| Tempo MediaPipe (ms/frame) | antes/depois de `extrator.extrair` |
| Tempo de inferência (ms) | antes/depois de `classificador.prever` |
| Tempo total por frame (ms) | início ao fim de cada iteração do laço |
| **Latência sinal→texto** | do momento em que a mão "para" (fim do movimento) até a palavra aparecer — aproximado pelo tempo entre a 1.ª previsão correta e a emissão pelo estabilizador + metade da janela |

### 12.4 Metas do MVP

| Indicador | Meta |
|---|---|
| Acurácia offline (por pessoa) | ≥ 90 % |
| Taxa de acerto em tempo real | ≥ 80 % |
| Falsos positivos | ≤ 1 por minuto |
| FPS | ≥ 15 |
| Latência sinal→texto | ≤ 1 s |

---

## 13. Organização para evolução futura

### 13.1 Adicionar um sinal novo — **sem alterar código**

1. Documentar o sinal em `docs/SINAIS.md`.
2. `python scripts/coletar_dados.py --sinal CASA --pessoa ana` (as classes vêm das pastas
   de `data/raw/`).
3. `construir_dataset.py` → `treinar_modelo.py` → `avaliar_modelo.py`.
4. (Opcional) adicionar combinações em `config/frases.json`.

### 13.2 Pontos de troca (interfaces simples)

| Peça | Hoje | Amanhã |
|---|---|---|
| Classificador | RandomForest (joblib) | Keras LSTM/GRU/CNN-1D — basta outra classe com o mesmo método `prever(vetor) -> (sinal, conf)` |
| Features | posição normalizada | + velocidades, ângulos dos dedos, expressão facial (Face Landmarker) |
| Voz | pyttsx3 | Piper TTS |
| Interface | janela OpenCV | Tkinter/Streamlit/web |
| Frases | dicionário | regras gramaticais ou modelo de linguagem |

### 13.3 Boas práticas que valem desde o início

- **Git** com branches por funcionalidade; `data/raw` pode ir para um drive compartilhado se
  ficar grande.
- **`config.py` único** — nenhum "número mágico" espalhado pelo código.
- **Testes** para `features`, `estabilizador` e `frase` (lógica pura, sem câmera).
- **`classificador_info.json`** salva junto com o modelo, para saber com que parâmetros ele
  foi treinado.
- **Versão das features** (`VERSAO_FEATURES = 1`) — se o pré-processamento mudar, o modelo
  antigo é recusado com mensagem clara.

### 13.4 Roteiro sugerido

| Fase | Entrega |
|---|---|
| **1. Base** | Câmera + MediaPipe desenhando landmarks na tela; FPS visível (`testar_deteccao.py`) |
| **2. Dados** | `coletar_dados.py` + `visualizar_amostra.py`; `SINAIS.md`; coleta com o grupo |
| **3. Modelo** | `features.py`, `construir_dataset.py`, `treinar_modelo.py`, `avaliar_modelo.py` |
| **4. Tempo real** | `executar.py` mostrando o sinal + confiança |
| **5. Estabilidade** | `estabilizador.py` + `frase.py` + testes |
| **6. Voz** | `voz.py` em thread |
| **7. Avaliação** | protocolo de tempo real, métricas de latência, relatório final |
| **Futuro** | mais sinais, LSTM, expressões faciais, datilologia (alfabeto), interface gráfica |

---

## 14. Riscos conhecidos e mitigação

| Risco | Mitigação |
|---|---|
| Sinais parecidos (EU × MEU) | Features relativas ao corpo; gravar com cuidado; olhar a matriz de confusão |
| Falsos positivos quando não há sinal | Classe `_NADA` bem gravada + limiar + estabilidade |
| Funciona só para quem gravou | Várias pessoas na coleta; avaliação por pessoa |
| Iluminação ruim / fundo poluído | Orientar ambiente; incluir variações na coleta |
| Voz pt-BR indisponível no SO | Documentar instalação; fallback: exibir só texto |
| Incompatibilidade de versões (MediaPipe × Python) | Python 3.11 + `requirements.txt` fixado |
| Canhotos | MVP: documentar mão dominante; futuro: *data augmentation* espelhando a amostra |
