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

## 2. Estrutura de diretórios e os dois modos

O projeto tem **dois modos claramente separados**:

| | **Modo usuário / demonstração** | **Modo desenvolvimento / treinamento** |
|---|---|---|
| Para quê | apresentar: webcam → Libras → texto → voz | construir o modelo: coletar, analisar, treinar, avaliar |
| Scripts | `scripts/demonstracao/` (`app.py`, `executar.py`) ou `python -m libras` | `scripts/desenvolvimento/` |
| Dependências | `requirements.txt` | `requirements-dev.txt` (= aplicação + matplotlib + pytest) |
| Arquivos usados | `models/` (modelos do MediaPipe + classificador treinado) | `data/`, `models/`, `reports/` |
| Módulos | núcleo + aplicação | todos |

```
Vis-oLibras/
├── README.md
├── requirements.txt             # MODO USUÁRIO: só o que a aplicação precisa
├── requirements-dev.txt         # MODO DESENVOLVIMENTO: -r requirements.txt + treino/testes
├── pyproject.toml               # mesmas listas: pip install -e .  |  pip install -e ".[desenvolvimento]"
│
├── src/libras/
│   ├── __init__.py              # define as três camadas (listas de módulos)
│   │
│   │   NÚCLEO (usado pelos dois modos)
│   ├── config.py                # TODAS as constantes: sinais, limiares, caminhos...
│   ├── camera.py                # webcam com tratamento de erros
│   ├── extrator.py              # MediaPipe: frame → landmarks crus (mãos + pose)
│   ├── features.py              # normalização e vetor de features (igual no treino e no tempo real)
│   ├── temporal.py              # sequência dos últimos segundos + características de movimento
│   ├── desenho.py               # landmarks, painéis e textos na imagem
│   ├── metricas.py              # FPS
│   │
│   │   APLICAÇÃO (modo usuário)
│   ├── classificador.py         # carregar o modelo e prever (sinal, confiança)
│   ├── estabilizador.py         # anti-repetição
│   ├── reconhecedor.py          # sequência + modelo + estabilizador, frame a frame
│   ├── frase.py                 # gerenciador de sentença
│   ├── voz.py                   # text-to-speech offline em thread
│   ├── pipeline.py              # frame → landmarks → reconhecimento → imagem
│   ├── captura.py               # câmera + pipeline em thread (a interface não trava)
│   ├── interface.py             # interface gráfica (CustomTkinter)
│   ├── __main__.py              # python -m libras → abre a interface
│   │
│   │   DESENVOLVIMENTO (modo treinamento)
│   ├── dataset.py               # gravar, ler, validar e analisar amostras
│   └── avaliacao.py             # sinais confundidos e matriz de confusão
│
├── scripts/
│   ├── demonstracao/            # MODO USUÁRIO
│   │   ├── app.py               # interface gráfica (recomendada para apresentar)
│   │   └── executar.py          # versão simples em janela do OpenCV
│   └── desenvolvimento/         # MODO DESENVOLVIMENTO
│       ├── testar_deteccao.py   # diagnóstico: webcam → MediaPipe (sem reconhecimento)
│       ├── coletar_dados.py     # grava amostras de um sinal
│       ├── analisar_dataset.py  # valida o dataset: contagens, inválidas, inconsistências, gráficos
│       ├── construir_dataset.py # data/raw → data/processed/dataset.npz
│       ├── treinar_modelo.py    # compara RF/SVM/MLP, avalia e salva o modelo
│       ├── avaliar_modelo.py    # avalia o modelo salvo (ex.: com uma pessoa nova)
│       ├── comparar_features.py # features v1 (posição) × v2 (+ movimento)
│       ├── empacotar_app.py     # gera o zip do modo usuário (dist/Vis-oLibras-demo.zip)
│       └── visualizar_amostra.py# (a implementar) reproduz uma amostra gravada
│
├── data/                        # (desenvolvimento) amostras; fora do Git
│   ├── raw/<SINAL>/*.npy        # identificadores sem acento: NAO é exibido como "NÃO"
│   ├── processed/dataset.npz
│   └── metadata.csv
├── models/                      # (os dois modos) .task do MediaPipe + classificador treinado
├── reports/                     # (desenvolvimento) métricas e gráficos
├── docs/                        # arquitetura e descrição dos sinais
└── tests/                       # testes (inclui test_modos.py, que garante a separação)
```

**Regras de dependência entre camadas** (verificadas por `tests/test_modos.py`):

- o **núcleo** só importa o núcleo;
- a **aplicação** só importa núcleo + aplicação — nunca `dataset`, `avaliacao`, matplotlib ou pytest;
- o **desenvolvimento** pode usar tudo (ex.: `treinar_modelo.py` usa `classificador.salvar_classificador`).

**Pacote de demonstração:** `empacotar_app.py` gera um zip só com o núcleo, a aplicação,
os scripts de demonstração, o `requirements.txt` e os modelos — sem dataset, relatórios,
testes ou código de treino. Todos os scripts ajustam o caminho de `src/` sozinhos, então
funcionam sem `pip install -e .`.

**Dependências:** a aplicação ainda precisa do scikit-learn e do joblib para abrir o modelo
(o modelo salvo é um objeto do scikit-learn). O matplotlib não é usado pelo nosso código na
aplicação, mas continua instalado porque o próprio MediaPipe depende dele. O OpenCV é o
`opencv-contrib-python`, o mesmo que o MediaPipe instala (ter também o `opencv-python`
causa conflito).

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

Uso: `python scripts/desenvolvimento/coletar_dados.py --sinal OI --pessoa ana` (`--label` também é aceito)

Funcionamento:

1. Abre a câmera e mostra landmarks das mãos e a linha dos ombros.
2. **ESPAÇO** inicia a gravação contínua: contagem de 3 s, grava **1,5 s**, pausa de 1 s,
   grava a próxima... até a meta (`--meta`, padrão 40). **ESPAÇO** de novo pausa.
3. Cada amostra é validada na hora (`dataset.validar_amostra`) e descartada, com o
   motivo na tela, se: poucos frames (câmera lenta), mãos em < 70 % dos frames (exceto
   `_NADA`), ombros em < 70 % dos frames ou não gerar o vetor de features.
4. **D** apaga a última amostra salva; **Q/ESC** sai.
5. A tela mostra sinal, amostras (sessão/total/descartadas), mãos, ombros, FPS e estado.

O extrator reaproveita a última pose por até 0,5 s quando o rastreamento do MediaPipe
falha num frame isolado (os ombros quase não se movem durante um sinal).

### 5.4 Análise do dataset (`analisar_dataset.py`)

Usa as mesmas regras do coletor e mostra: sinais cadastrados, amostras por sinal e por
pessoa, tamanho do vetor, amostras inválidas (e duplicatas), classes com poucas amostras,
inconsistências (pastas desconhecidas, divergências com o `metadata.csv`, desbalanceamento,
poucas pessoas), amostras suspeitas (muito diferentes das outras do mesmo sinal ou usando
outra mão) e os pares de sinais mais parecidos. Salva `reports/analise_dataset.txt` e
`reports/analise_dataset.png`. `--remover-invalidas` apaga as inválidas (com confirmação).

### 5.5 Quantidade e diversidade

| Item | Meta mínima |
|---|---|
| Amostras por sinal por pessoa | 30–40 |
| Pessoas diferentes | 3 ou mais (ideal: todo o grupo) |
| Amostras de `_NADA` | o dobro de um sinal comum |
| Variações | iluminação, roupa, fundo, distância (0,8–1,5 m), leve rotação |

Total estimado: 11 classes × 40 × 3 pessoas ≈ **1.300 amostras** → ~1 h de gravação
dividida entre o grupo.

`visualizar_amostra.py` (a implementar) permitirá reproduzir amostras como "esqueleto" para conferir e
apagar gravações ruins.

---

## 6. Armazenamento dos landmarks

### 6.1 Guardar o **bruto**, processar depois

Salvamos os landmarks **sem normalização**. Assim, se mudarmos a forma de
pré-processar, não é preciso regravar nada — basta rodar `construir_dataset.py` de novo.

### 6.2 Formato de cada amostra (`.npy`)

Arquivo: `data/raw/OI/ana_20260929_153012_123456.npy` — um array `float32` de forma
**`(F, 1 + 126 + 2 + 99)`** onde `F` = número de frames gravados (~45 a 30 fps):

| Colunas | Conteúdo |
|---|---|
| 0 | timestamp em segundos (relativo ao início) |
| 1–63 | mão **direita**: 21 pontos × (x, y, z) |
| 64–126 | mão **esquerda**: 21 pontos × (x, y, z) |
| 127–128 | flags de presença (mão direita, mão esquerda) = 0/1 |
| 129–227 | pose: 33 pontos × (x, y, z) (usaremos só alguns, mas guardamos todos) |

x e z são multiplicados por largura/altura da imagem ("unidades da altura"), para que as
distâncias não fiquem distorcidas em câmeras 4:3 ou 16:9.

Mão não detectada → zeros + flag 0.

> **Atenção à lateralidade:** com a imagem espelhada, o MediaPipe pode inverter
> "Left/Right". Definir em `config.py` a convenção e **usar a mesma na coleta e no tempo
> real** (ambos passam pelo mesmo `extrator.py`, então isso fica garantido).

### 6.3 `data/metadata.csv`

```
arquivo,sinal,pessoa,data_hora,num_frames,fps_medio,pct_frames_com_mao,pct_frames_com_ombros
raw/OI/ana_20260929_153012_007.npy,OI,ana,2026-09-29T15:30:12,46,30.4,0.96,1.00
```

Serve para contar amostras por classe/pessoa, filtrar gravações ruins e dividir
treino/teste **por pessoa**.

### 6.4 Dataset processado

`data/processed/dataset.npz` contém `X` (n_amostras × n_features), `y` (rótulos) e
`pessoa` (para validação). É gerado — pode ser apagado e recriado.

---

## 7. Treinamento do modelo

### 7.1 Pré-processamento (`features.py`) — idêntico no treino e no tempo real

Objetivo: o modelo deve aprender o **formato e o movimento** da mão e **onde o sinal é feito
em relação ao corpo** — e não a posição da mão na imagem, a distância até a câmera ou o
tamanho da mão de quem gravou.

Para **cada mão presente em cada frame** (coordenadas já corrigidas pela proporção da imagem):

1. **Forma (63 valores):** pontos relativos ao punho, divididos pelo tamanho da palma
   (punho → base do dedo médio). Invariante à posição na imagem, à distância e ao tamanho
   da mão.
2. **Posição (2 valores):** punho relativo ao centro dos ombros, dividido pela largura dos
   ombros. Não é a posição na câmera: é o *ponto de articulação* do sinal (peito, boca,
   testa), que em Libras diferencia sinais como EU × MEU. Invariante à posição da pessoa e à
   distância.
3. Mão ausente → 63 + 2 zeros. Vetor do frame: [forma D, posição D, forma E, posição E,
   flags] = **132 valores**.

Para **cada amostra/janela**:

4. **Falhas curtas de detecção** (a mão some por até 3 frames) são interpoladas.
5. Frames sem ombros usam a referência do frame mais próximo; sem ombros em nenhum frame,
   a janela é inválida (`ErroJanela`).
6. **Reamostragem temporal** para **T = 20 frames** igualmente espaçados no tempo (frame
   mais próximo de cada instante — evita misturar um frame com mão e outro sem). Torna o
   sistema independente do FPS da máquina.
7. **Achatar** → vetor de 20 × 132 = **2.640 features** (versão 1).
8. **Versão 2 (atual):** + **152 características de movimento** (seção 7.3) → **2.792 features**.

Função única: `features.janela_para_vetor(frames_brutos) -> np.ndarray`. **Treino e tempo
real chamam exatamente a mesma função** — isso evita o erro mais comum desse tipo de
projeto.

### 7.2 Script `treinar_modelo.py`

1. Carrega `dataset.npz` (gerado por `construir_dataset.py`, ou na hora com
   `--reconstruir`) e **valida**: versão das features, formato de X, NaN, rótulos
   conhecidos, pelo menos 2 classes e 2 amostras por classe.
2. Separa **treino (75 %) e teste (25 %) de forma estratificada** (mesma proporção de cada
   sinal nos dois), com `random_state = SEMENTE`.
3. Compara 3 candidatos, todos com `Pipeline` do scikit-learn, por **validação cruzada
   estratificada (5 folds) só no treino**, usando F1 macro:
   - `RandomForestClassifier(n_estimators=300, class_weight="balanced")`
   - `StandardScaler` + SVM RBF (`CalibratedClassifierCV` para dar a confiança)
   - `StandardScaler` + `MLPClassifier(hidden_layer_sizes=(256, 128))`
4. Avalia o escolhido no teste: accuracy, precision/recall/F1 por classe, **matriz de
   confusão** (`reports/matriz_confusao.png`), sinais confundidos e tempo de uma previsão.
5. Com 2+ pessoas, **testa com pessoas novas** (treina sem uma pessoa e testa nela) — a
   separação estratificada mistura amostras da mesma pessoa no treino e no teste e por isso
   é otimista; este teste é a estimativa realista.
6. Retreina o escolhido com **todas** as amostras e salva (`classificador.py`):
   - `models/classificador.joblib` (Pipeline, já em modo de 1 núcleo para previsões rápidas)
   - `models/classes.json` (rótulos na ordem das saídas do modelo)
   - `models/classificador_info.json` (algoritmo, parâmetros, `random_state`, divisão,
     comparação, métricas, confusões, versões das bibliotecas e parâmetros das features).
     Ao carregar, `carregar_classificador()` recusa um modelo treinado com outras features.

Relatório completo em `reports/classification_report.txt`. Tempo de treino: menos de
1 minuto para ~350 amostras em notebook comum.

### 7.3 Sinais com movimento (features versão 2)

**Limitação:** o sistema nunca classificou frames isolados — cada previsão usa uma janela de
1,5 s (20 frames). Mas, na versão 1, o movimento fica *implícito*: o modelo recebe 20
posições soltas e precisa descobrir sozinho que elas formam um aceno. Dos 2.640 números,
2.520 descrevem a forma da mão e só 80 a trajetória; com poucas amostras, o movimento se
perde. Além disso, no tempo real a janela desliza e o aceno aparece em fases diferentes das
amostras gravadas.

**Opções avaliadas:**

| Abordagem | Diferencia movimento? | Dados necessários | Complexidade | Decisão |
|---|---|---|---|---|
| Frame isolado | não | poucos | baixa | — (nunca usamos) |
| Janela posicional (v1) | implicitamente | muitos | baixa | mantida como base |
| **Janela + características de movimento (v2)** | **sim, explicitamente** | **poucos** | **baixa** | **escolhida** |
| LSTM/GRU | sim | muitos (centenas por sinal) | alta (TensorFlow, ajuste) | só se necessário |

Protótipo com 5 classes que só diferem pelo movimento (parado, aceno, círculo, sobe,
desce), mesma forma de mão e posição, com variação de velocidade e fase: com 20 amostras
por classe, **v1 = 85 %** e **v2 = 99 %**; com 40, 98,5 % × 100 %. A v1 aprende o
movimento, mas precisa do dobro de dados.

**Características de movimento** (`temporal.caracteristicas_movimento`, calculadas sobre a
sequência já normalizada, então continuam invariantes à posição, distância e tamanho):

| Por mão | O que captura |
|---|---|
| velocidade do punho entre frames (2 × 19) | direção e ritmo |
| deslocamento total (2) | sobe × desce |
| comprimento da trajetória (1) | parado × em movimento |
| amplitude em x e y (2) | tamanho do movimento |
| mudanças de direção em x e y (2, com suavização e limiar) | aceno, vai-e-vem |
| abertura da mão em cada frame (20) e variação (1) | abrir / fechar a mão |
| **entre as mãos:** distância entre os punhos (20) | aproximar / afastar |

Sinais estáticos continuam funcionando: as features da v1 estão todas lá, e o movimento
perto de zero passa a ser uma pista a mais ("este sinal é parado").

**Compatibilidade:** os dados brutos não mudam (nada precisa ser regravado); o vetor v2 é o
v1 com o bloco de movimento no fim; o modelo salvo registra sua versão e o tempo real gera o
vetor **na versão do modelo** — um modelo v1 continua funcionando. `treinar_modelo.py`
reconstrói o `dataset.npz` automaticamente quando a versão muda.

**Quando partir para LSTM/GRU:** muitos sinais dinâmicos com mesma forma e trajetória
parecida (diferença só na ordem fina do movimento), sinais de duração muito variável (> 2 s),
vocabulário > 30 sinais e > 100 amostras por sinal — e só se `comparar_features.py` e a
matriz de confusão mostrarem que a v2 não resolve. A interface `Classificador.prever(vetor)`
permite trocar o modelo sem mexer no resto (a sequência T × 132 já existe em
`features.sequencia_normalizada`).

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

Como classificamos ~5 vezes por segundo, um único sinal de OI geraria "OI OI OI OI OI…".
Uma palavra só é aceita quando passa por **todas** as regras (valores em `config.py`, e
também ajustáveis pela linha de comando do `executar.py`):

| # | Regra | Parâmetro | Efeito |
|---|---|---|---|
| 1 | **Limiar de confiança** | `LIMIAR_CONFIANCA = 0.75` (`--limiar`) | Corta dúvidas |
| 2 | **Estabilidade:** mesmo sinal em *N* previsões seguidas | `N_CONSECUTIVAS = 3` (`--consecutivas`) | Corta "piscadas" do modelo |
| 3 | **Cooldown geral** após qualquer palavra | `COOLDOWN_S = 1.0` (`--cooldown`) | Dá tempo do gesto terminar |
| 4 | **Mesma palavra de novo:** tempo mínimo | `COOLDOWN_MESMO_SINAL_S = 2.0` (`--cooldown-mesmo`) | Evita repetição acidental |
| 5 | **Liberação:** repetir a mesma palavra exige passar por `_NADA` (ou mãos fora da imagem) | `EXIGIR_LIBERACAO = True` (`--sem-liberacao`) | Segurar NOME por 10 s gera um NOME só |

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

### 10.2 Gerenciador de sentença (sem tradução inventada)

`frase.GerenciadorSentenca` é independente da visão e separa quatro estados: **sinal atual**
(o que o modelo vê agora), **último confirmado**, **sequência** e **frase final**. Funções:
adicionar (com proteção extra contra repetição involuntária), remover a última, limpar,
finalizar (botão, Espaço, pausa ou frase cheia).

O MVP **não traduz** Libras para português: a frase é a própria sequência de sinais (glosa),
ex.: "EU NOME CAUA". Libras tem gramática própria, e combinações como "EU AJUDA" são ambíguas
("eu ajudo"? "me ajude"?). A arquitetura aceita `regras` (funções palavras → palavras)
aplicadas antes de montar o texto, para regras validadas no futuro.

---

## 11. Conversão em voz (`voz.py`)

- **Offline e gratuito:** Windows usa o **pyttsx3** (vozes SAPI5 do sistema); Linux usa o
  pyttsx3 com eSpeak ou, se faltar o `aplay` (com o qual o pyttsx3 toca o som e sem o qual
  fica mudo sem avisar), o comando `espeak-ng`; macOS usa o comando `say` (o pyttsx3 trava
  fora da thread principal no Mac).
- **Português do Brasil** quando disponível (`IDIOMAS_VOZ`), velocidade `TAXA_FALA ≈ 170`.
- **Não trava o vídeo:** a fala roda numa thread própria com fila. `falar(texto)` / `speak(texto)`
  devolve na hora; texto vazio é ignorado; durante outra fala, o pedido é ignorado ou
  enfileirado (`POLITICA_VOZ`); sem sistema de voz, `disponivel = False` e o resto funciona;
  erro durante a fala é registrado e o motor é recriado.
- **Quando falar:** a frase inteira quando é finalizada (`FALAR_AO_FINALIZAR`), e
  opcionalmente cada palavra (`FALAR_CADA_PALAVRA`). O texto vai em minúsculas, porque
  sintetizadores leem palavras em MAIÚSCULAS como siglas.
- Motor trocável (`Voz(criar_motor=...)`): alternativas futuras são **Piper TTS** (offline,
  voz neural pt-BR) ou **gTTS** (exige internet).

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
2. `python scripts/desenvolvimento/coletar_dados.py --sinal CASA --pessoa ana` (as classes vêm das pastas
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
