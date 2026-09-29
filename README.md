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
| 1 | Câmera + MediaPipe desenhando landmarks | ⏳ próxima |
| 2 | Coleta de dados | — |
| 3 | Dataset, treino e avaliação | — |
| 4 | Reconhecimento em tempo real | — |
| 5 | Anti-repetição e frases | — |
| 6 | Voz | — |
| 7 | Avaliação final | — |

## Requisitos

- Python **3.10 a 3.12** (recomendado **3.11**)
- Webcam
- Voz em português instalada no sistema (para a fase de voz):
  - **Windows:** instalar o idioma "Português (Brasil)" com recurso de fala
  - **Linux:** `sudo apt install espeak-ng`
  - **macOS:** voz nativa (ex.: "Luciana")

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
