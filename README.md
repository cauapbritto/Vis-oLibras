# Vis-oLibras

**Tradução de Libras para Texto e Voz utilizando Visão Computacional e Inteligência Artificial**

Protótipo acadêmico que usa a webcam para reconhecer, em tempo real, um vocabulário
pequeno de sinais de Libras e convertê-los em texto na tela e em áudio.

- **Vocabulário inicial (MVP):** OI, EU, MEU, NOME, BOM, DIA, OBRIGADO, SIM, NÃO, AJUDA
- **Tecnologias:** Python · OpenCV · MediaPipe · NumPy · scikit-learn · pyttsx3 — tudo
  gratuito e executado localmente
- **Plano técnico completo:** [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md)

## Status

| Fase | Descrição | Situação |
|---|---|---|
| 0 | Estrutura do projeto e configuração | ✅ concluída |
| 1 | Câmera + MediaPipe desenhando landmarks | ✅ concluída |
| 2 | Coleta de dados e análise do dataset | ✅ concluída |
| 3 | Dataset, treino e avaliação | ✅ concluída |
| 4 | Reconhecimento em tempo real | ✅ concluída |
| 5 | Anti-repetição e frases | ✅ concluída (sem voz) |
| 6 | Voz | ⏳ próxima |
| 7 | Avaliação final | — |

## Requisitos

- Python **3.10 a 3.12** (recomendado **3.11**)
- Webcam
- Voz em português instalada no sistema (para a fase de voz):
  - **Windows:** instalar o idioma "Português (Brasil)" com recurso de fala
  - **Linux:** `sudo apt install espeak-ng`
  - **macOS:** voz nativa (ex.: "Luciana")
- **Linux:** o MediaPipe precisa das bibliotecas gráficas do sistema:
  `sudo apt install libegl1 libgles2`

## Instalação

Na pasta do projeto:

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

> Se o PowerShell bloquear a ativação: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**Linux / macOS**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

`pip install -e .` instala o pacote `src/libras` em modo editável, para que os scripts
consigam fazer `from libras import config` de qualquer pasta.

### Conferir a instalação

```bash
python -m libras.config   # mostra caminhos, câmera, classes e limiares
pytest                    # roda os testes
```

## Fase 1 — testar câmera e detecção de mãos

```bash
python scripts/testar_deteccao.py            # câmera padrão
python scripts/testar_deteccao.py --camera 1 # outra câmera
```

Na primeira execução, o modelo `models/hand_landmarker.task` (~8 MB) é baixado
automaticamente. A janela mostra os landmarks das mãos (verde = direita, azul =
esquerda), o FPS e quais mãos foram detectadas. **Q** ou **ESC** fecha.

Validação:

1. Sem mãos na frente da câmera → "Nenhuma mao detectada" (após 3 s aparecem dicas).
2. Só a mão **direita** → "Mao direita" (se aparecer "esquerda", use
   `TROCAR_LADOS = True` em `config.py`).
3. Só a mão esquerda → "Mao esquerda". As duas → "Ambas as maos".
4. FPS ≥ 15.

## Fase 2 — coletar e analisar o dataset

```bash
python scripts/coletar_dados.py --sinal OI --pessoa ana      # --label também funciona
python scripts/coletar_dados.py --sinal _NADA --pessoa ana   # classe "nenhum sinal"
python scripts/analisar_dataset.py                           # relatório + gráficos em reports/
```

No coletor: **ESPAÇO** inicia/pausa a gravação contínua, **D** apaga a última amostra,
**Q/ESC** sai. Fique a ~1 m da câmera com os **ombros visíveis**. São salvos apenas os
landmarks (`data/raw/<SINAL>/*.npy`), sem imagens. Antes de gravar, preencha
[`docs/SINAIS.md`](docs/SINAIS.md) com a variante de cada sinal.

Meta para o protótipo: **40 amostras por sinal por pessoa, com 3 pessoas ou mais**
(≥ 120 por sinal) e o dobro para `_NADA`.

## Fase 3 — treinar o modelo

```bash
python scripts/construir_dataset.py     # data/raw -> data/processed/dataset.npz
python scripts/treinar_modelo.py        # compara RF, SVM e MLP e salva o melhor
python scripts/treinar_modelo.py --modelo rf --reconstruir
```

Saídas: `models/classificador.joblib`, `models/classes.json`,
`models/classificador_info.json`, `reports/classification_report.txt` e
`reports/matriz_confusao.png`.

## Fase 4 — reconhecimento em tempo real

```bash
python scripts/executar.py
python scripts/executar.py --limiar 0.6 --consecutivas 4 --cooldown 1.5
```

Teclas: **C** limpa a sequência, **BACKSPACE** apaga a última palavra, **ESPAÇO** encerra
a frase, **Q/ESC** sai. As palavras aceitas também aparecem no terminal.

Parâmetros de estabilidade (em `config.py` ou pela linha de comando):

| Parâmetro | Padrão | Opção | Aumentar | Diminuir |
|---|---|---|---|---|
| `LIMIAR_CONFIANCA` | 0.75 | `--limiar` | menos palavras erradas, mais sinais ignorados | aceita sinais "duvidosos" |
| `N_CONSECUTIVAS` | 3 | `--consecutivas` | mais estável, mais lento | mais rápido, mais "piscadas" |
| `COOLDOWN_S` | 1.0 | `--cooldown` | mais tempo entre palavras | frases mais rápidas |
| `COOLDOWN_MESMO_SINAL_S` | 2.0 | `--cooldown-mesmo` | repetir a mesma palavra demora mais | repete mais rápido |
| `EXIGIR_LIBERACAO` | True | `--sem-liberacao` | — | repete a palavra sem abaixar as mãos |
| `PASSO_INFERENCIA` | 5 | `--passo` | menos CPU, reação mais lenta | reage mais rápido, mais CPU |
| `PAUSA_FRASE_S` | 2.5 | — | frases mais longas | encerra a frase mais cedo |

## Sinais com movimento (features versão 2)

Cada previsão usa uma janela de 1,5 s. Desde a versão 2 das features, além da forma e da
posição das mãos em cada frame, o vetor traz características de movimento (velocidade,
trajetória, mudanças de direção, abertura da mão, distância entre as mãos). Sinais
estáticos continuam funcionando; modelos antigos (v1) também.

```bash
python scripts/comparar_features.py   # v1 x v2 no seu dataset, por sinal
python scripts/treinar_modelo.py      # reconstrói o dataset.npz na versão atual
```

Detalhes e justificativa: [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), seção 7.3.

## Configuração

Todas as configurações ficam em [`src/libras/config.py`](src/libras/config.py): câmera,
quantidade de frames, confiança mínima, lista de sinais, caminhos do dataset e do modelo,
entre outras. Os caminhos são calculados a partir da raiz do projeto, então funcionam em
qualquer computador.

Para usar outra câmera sem editar o arquivo:

```bash
LIBRAS_CAMERA=1 python scripts/executar.py        # Linux/macOS
$env:LIBRAS_CAMERA=1; python scripts/executar.py  # Windows (PowerShell)
```

## Estrutura

```
src/libras/   lógica reutilizável (módulos da aplicação)
scripts/      programas executados pelo usuário
config/       frases.json (combinações de palavras -> português)
data/raw/     amostras gravadas, uma pasta por sinal
models/       modelos do MediaPipe e classificador treinado
reports/      métricas e gráficos gerados
tests/        testes automatizados
docs/         arquitetura e descrição dos sinais
```

Detalhes em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), seção 2.
