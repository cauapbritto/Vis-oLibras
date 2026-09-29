# Vis-oLibras

**Tradução de Libras para Texto e Voz utilizando Visão Computacional e Inteligência Artificial**

Protótipo acadêmico que usa a webcam para reconhecer, em tempo real, um vocabulário
pequeno de sinais de Libras, montar a sequência de palavras e falar a frase.

- **Vocabulário inicial (MVP):** OI, EU, MEU, NOME, BOM, DIA, OBRIGADO, SIM, NÃO, AJUDA
- **Tecnologias:** Python · OpenCV · MediaPipe · NumPy · scikit-learn · pyttsx3 ·
  CustomTkinter — tudo gratuito e executado localmente (offline)
- **Plano técnico completo:** [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md)

## Dois modos

| | **Modo usuário / demonstração** | **Modo desenvolvimento / treinamento** |
|---|---|---|
| Para quê | apresentar: webcam → Libras → texto → voz | coletar dados, analisar, treinar, avaliar |
| Onde | `scripts/demonstracao/` | `scripts/desenvolvimento/` |
| Instala | `requirements.txt` | `requirements-dev.txt` |
| Precisa de | `models/` com o modelo treinado | `data/` com as gravações |

A aplicação não carrega nada do treino (dataset, relatórios, matplotlib, pytest). Isso é
verificado automaticamente pelos testes (`tests/test_modos.py`).

## Requisitos

- Python **3.10 a 3.12** (recomendado **3.11**) e uma webcam
- Voz em português instalada no sistema:
  - **Windows:** Configurações → Hora e idioma → adicionar "Português (Brasil)" com recurso de fala
  - **macOS:** voz nativa (ex.: "Luciana")
- **Linux:** `sudo apt install python3-tk espeak-ng alsa-utils libegl1 libgles2`

---

## Modo usuário / demonstração

### Instalação

**Windows (PowerShell)**, na pasta do projeto:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> Se o PowerShell bloquear a ativação: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
>
> Em redes que interceptam HTTPS (erro `CERTIFICATE_VERIFY_FAILED`), atualize primeiro o
> pip: `python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org`
> e depois instale normalmente — o pip novo usa os certificados do Windows. Ou use outra rede.

**Linux / macOS:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Não é preciso `pip install -e .`: os scripts encontram o código sozinhos.

### Uso

```bash
python scripts/demonstracao/app.py         # interface gráfica (recomendada para apresentar)
python -m libras                           # o mesmo, se o pacote estiver instalado
python scripts/demonstracao/executar.py    # versão simples em janela do OpenCV
```

A interface mostra a webcam com os landmarks, o **sinal detectado agora** (com a
confiança), o **último sinal confirmado**, a **sequência** e a **frase final**, e os
indicadores de câmera, modelo, mãos e voz. Botões: Iniciar/Parar câmera, Finalizar frase,
Reproduzir voz, Remover última palavra e Limpar frase (atalhos: Espaço, Backspace, C).
Sem modelo treinado, a câmera funciona e mostra só os landmarks.

Quando a frase é finalizada (botão, Espaço ou 2,5 s sem sinais), ela aparece em "Frase
final" e é falada em português do Brasil. A frase é a própria sequência de sinais (glosa,
ex.: "EU NOME CAUA"): o MVP não traduz a gramática da Libras.

**Na janela do OpenCV (`executar.py`):** C limpa, BACKSPACE apaga a última palavra,
ESPAÇO encerra a frase, Q/ESC sai. Opções: `--sem-voz`, `--camera 1` e os parâmetros de
estabilidade abaixo.

### Parâmetros de estabilidade

Em `src/libras/config.py` ou pela linha de comando do `executar.py`:

| Parâmetro | Padrão | Opção | Aumentar | Diminuir |
|---|---|---|---|---|
| `LIMIAR_CONFIANCA` | 0.75 | `--limiar` | menos palavras erradas, mais sinais ignorados | aceita sinais "duvidosos" |
| `N_CONSECUTIVAS` | 3 | `--consecutivas` | mais estável, mais lento | mais rápido, mais "piscadas" |
| `COOLDOWN_S` | 1.0 | `--cooldown` | mais tempo entre palavras | frases mais rápidas |
| `COOLDOWN_MESMO_SINAL_S` | 2.0 | `--cooldown-mesmo` | repetir a mesma palavra demora mais | repete mais rápido |
| `EXIGIR_LIBERACAO` | True | `--sem-liberacao` | — | repete a palavra sem abaixar as mãos |
| `PASSO_INFERENCIA` | 5 | `--passo` | menos CPU, reação mais lenta | reage mais rápido, mais CPU |
| `PAUSA_FRASE_S` | 2.5 | — | frases mais longas | encerra a frase mais cedo |

### Levar para o computador da apresentação

No computador de desenvolvimento (com o modelo treinado):

```bash
python scripts/desenvolvimento/empacotar_app.py   # gera dist/Vis-oLibras-demo.zip
```

O zip leva só o necessário (código da aplicação, `requirements.txt` e os modelos,
inclusive os do MediaPipe — útil em redes que bloqueiam o download) e um `LEIA-ME.txt`
com os comandos.

---

## Modo desenvolvimento / treinamento

### Instalação

Igual ao modo usuário, trocando o arquivo de dependências:

```bash
pip install -r requirements-dev.txt      # aplicação + matplotlib + pytest
python -m libras.config                  # confere caminhos, câmera, classes e limiares
pytest                                   # roda os testes
```

### Fluxo

```
testar_deteccao → coletar_dados → analisar_dataset → treinar_modelo → avaliar_modelo
                → teste_controlado → resumir_testes → empacotar_app
```

**1. Diagnóstico da câmera** (sem reconhecimento):

```bash
python scripts/desenvolvimento/testar_deteccao.py            # --camera 1 para outra câmera
```

Mostra landmarks (verde = direita, azul = esquerda), FPS e mãos detectadas. Só a mão
**direita** deve mostrar "Mao direita"; se aparecer "esquerda", use `TROCAR_LADOS = True`
no `config.py`.

**2. Coletar dados** — preencha antes [`docs/SINAIS.md`](docs/SINAIS.md) com a variante
de cada sinal:

```bash
python scripts/desenvolvimento/coletar_dados.py --sinal OI --pessoa ana      # --label também funciona
python scripts/desenvolvimento/coletar_dados.py --sinal _NADA --pessoa ana   # classe "nenhum sinal"
```

ESPAÇO inicia/pausa a gravação contínua, D apaga a última amostra, Q/ESC sai. Fique a
~1 m da câmera com os ombros visíveis. São salvos só os landmarks
(`data/raw/<SINAL>/*.npy`), sem imagens. Meta: **40 amostras por sinal por pessoa, com 3
pessoas ou mais**, e o dobro para `_NADA`.

**3. Analisar o dataset:**

```bash
python scripts/desenvolvimento/analisar_dataset.py       # relatório + gráficos em reports/
```

**4. Treinar:**

```bash
python scripts/desenvolvimento/treinar_modelo.py         # compara RF, SVM e MLP e salva o melhor
python scripts/desenvolvimento/treinar_modelo.py --modelo rf --reconstruir
python scripts/desenvolvimento/construir_dataset.py      # (opcional) só gera o dataset.npz
python scripts/desenvolvimento/comparar_features.py      # features v1 (posição) × v2 (+ movimento)
```

Saídas: `models/classificador.joblib`, `models/classes.json`,
`models/classificador_info.json`, `reports/classification_report.txt` e
`reports/matriz_confusao.png`. Desde a versão 2 das features, o vetor inclui
características de movimento ([`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), seção 7.3);
modelos antigos (v1) continuam funcionando.

**5. Avaliar o modelo salvo** (por exemplo, com uma pessoa que não participou do treino):

```bash
python scripts/desenvolvimento/avaliar_modelo.py --pessoa dani
```

**6. Testes controlados com participantes** (métricas para o trabalho):

```bash
python scripts/desenvolvimento/teste_controlado.py --participante p01           # cada sinal 10x, ordem aleatória
python scripts/desenvolvimento/teste_controlado.py --participante p01 --incluir-nada   # + falsos positivos
python scripts/desenvolvimento/resumir_testes.py                                 # resumo de todos os CSVs
```

O teste mostra "Faça: SINAL", conta até o "JÁ!" e registra sinal esperado, reconhecido,
confiança, tempo de resposta, latência, FPS e tempo de inferência — uma linha por tentativa
em `reports/testes/<sessao>.csv`, gravada na hora (D descarta uma tentativa errada pelo
participante). O resumo calcula accuracy, precision, recall, F1, matriz de confusão, erros
por sinal e estatísticas de tempo **somente com as tentativas registradas**, e exporta
`resumo.txt`, `resumo.json`, `por_classe.csv`, `matriz_confusao.csv/.png`.

**7. Empacotar para a demonstração:** `python scripts/desenvolvimento/empacotar_app.py`.

### Testes

`pytest` roda os testes automáticos (sem webcam). O checklist manual (câmera, reconhecimento,
iluminação, distância, sinais, voz, interface) está em [`docs/TESTES.md`](docs/TESTES.md), e
o roteiro do dia da apresentação em
[`docs/CHECKLIST_DEMONSTRACAO.md`](docs/CHECKLIST_DEMONSTRACAO.md).

---

## Limitações conhecidas

- Vocabulário pequeno e fixo (10 sinais); sinais novos exigem gravar e treinar.
- Não traduz a gramática da Libras: a frase é a sequência de sinais (glosa).
- Não usa expressões faciais nem datilologia (soletração); nomes próprios não são reconhecidos.
- Um sinal por vez: é preciso abaixar as mãos entre sinais iguais seguidos.
- Precisa dos ombros visíveis (referência da normalização) e de boa iluminação.
- O desempenho depende do dataset: poucas pessoas ou condições diferentes das da gravação
  reduzem a precisão com pessoas novas.
- A voz depende das vozes instaladas no sistema operacional.
- O modelo é salvo com `joblib` (pickle): só carregue modelos gerados por vocês.

## Configuração

Todas as configurações ficam em [`src/libras/config.py`](src/libras/config.py): câmera,
quantidade de frames, confiança mínima, lista de sinais, caminhos do dataset e do modelo,
voz, frases. Os caminhos são relativos à pasta do projeto. Variáveis de ambiente úteis:

```bash
LIBRAS_CAMERA=1 python scripts/demonstracao/app.py         # outra câmera (Linux/macOS)
$env:LIBRAS_CAMERA=1; python scripts/demonstracao/app.py   # Windows (PowerShell)
LIBRAS_DATA=/caminho/do/drive python scripts/desenvolvimento/treinar_modelo.py  # dataset em outro lugar
```

## Estrutura

```
src/libras/                 código (núcleo + aplicação + desenvolvimento; ver __init__.py)
scripts/demonstracao/       modo usuário
scripts/desenvolvimento/    modo desenvolvimento
data/                       gravações (desenvolvimento, fora do Git)
models/                     modelos do MediaPipe e classificador treinado
reports/                    métricas e gráficos (desenvolvimento)
tests/                      testes automatizados
docs/                       arquitetura e descrição dos sinais
```

Detalhes em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), seção 2.
