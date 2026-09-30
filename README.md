# Librahin

**Tradução de Libras para Texto e Voz utilizando Visão Computacional e Inteligência Artificial**

*Antes chamado Vis-oLibras (o endereço do repositório no GitHub pode continuar com o nome antigo).*

Protótipo acadêmico que usa a webcam para reconhecer, em tempo real, um vocabulário
pequeno de sinais de Libras, montar a sequência de palavras e falar a frase.

- **Vocabulário inicial (MVP):** OI, EU, MEU, NOME, BOM, DIA, OBRIGADO, SIM, NÃO, AJUDA
- **Tecnologias:** Python · OpenCV · MediaPipe · NumPy · scikit-learn · pyttsx3 ·
  CustomTkinter — tudo gratuito e executado localmente (offline)
- **Plano técnico completo:** [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md)

> **Vai testar ou gravar sinais para o grupo?** Siga o
> [tutorial passo a passo](docs/TUTORIAL_COLEGAS.md).
>
> **Prefere container?** Treinar, analisar e testar funcionam com Docker em qualquer
> sistema; câmera e interface, só no Linux. Veja [`docs/DOCKER.md`](docs/DOCKER.md).

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

**Windows, jeito fácil (um clique):** extraia o zip do projeto e dê dois cliques em
**`INSTALAR.bat`**. Ele instala o Python 3.11 (pelo `winget`, se faltar), cria o `.venv`,
instala as bibliotecas (com nova tentativa em redes que interceptam HTTPS), baixa os
modelos do MediaPipe, confere a voz em português e cria o atalho **Librahin** na Área
de Trabalho. O atalho (ou `Librahin.bat`) abre um menu numerado com a aplicação, o
teste da câmera, a gravação, o envio/junção de gravações, a análise, o treino e o teste
controlado. Se o Windows mostrar "O Windows protegeu o computador": **Mais informações** →
**Executar assim mesmo**. Os scripts ficam em `windows/`; o log da instalação, em
`instalar.log`.

**Windows (PowerShell), passo a passo**, na pasta do projeto:

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

A janela abre na hora e mostra "Carregando" enquanto o MediaPipe, o modelo e a voz são
preparados em segundo plano; o botão **Iniciar câmera** é liberado ao terminar. Depois
mostra a webcam com os landmarks, o **sinal detectado agora** (com a confiança e uma
marca no limite de aceitação de 75%), o **último sinal confirmado**, a **sequência** (uma
etiqueta por sinal) e a **frase final**. A barra de baixo mostra o estado da câmera, do
modelo, das mãos e da voz, e o botão **Sobre** mostra os créditos. Botões: Iniciar/Parar
câmera, Finalizar frase, Reproduzir voz, Remover última palavra e Limpar frase (atalhos:
Espaço, Backspace, C). Sem modelo treinado, a câmera funciona e mostra só os landmarks.
Tema claro: `python scripts/demonstracao/app.py --tema claro`.

Quando a frase é finalizada (botão, Espaço ou 2,5 s sem sinais), ela aparece em "Frase
final" e é falada em português do Brasil.

**Tabela de frases (`frases.txt`).** Sequências cadastradas pelo grupo viram português:
com `EU NOME = Meu nome é` e `OBRIGADO = Obrigado!`, os sinais EU · NOME · OBRIGADO
aparecem como "Meu nome é obrigado!", com "Sinais: EU NOME OBRIGADO" em letra pequena
embaixo. O que não estiver na tabela continua como glosa (a sequência de sinais, em
maiúsculas): o sistema não traduz a gramática da Libras. Edite o `frases.txt` no Bloco de
Notas (o formato está explicado no próprio arquivo) e confira com
`python scripts/demonstracao/testar_frases.py` (menu → F), que aponta erros pelo número da
linha e testa sequências sem abrir a câmera, ex.: `testar_frases.py EU NOME OBRIGADO`.
**Revisem as frases com quem conhece Libras.** Para voltar ao modo só glosa:
`USAR_TABELA_FRASES = False` no `config.py`.

**Letras do alfabeto (datilologia).** As letras A a Z e Ç podem ser gravadas e treinadas
como qualquer sinal, e são **opcionais**: entram no modelo só as que forem gravadas, sem
avisos pelas que faltam. Letras seguidas viram uma palavra soletrada, sem precisar de
tabela: MEU · NOME · C · A · U · A aparece como "Meu nome é Caua" (glosa: MEU NOME C-A-U-A),
e uma palavra soletrada conta como uma palavra só no limite da frase. Para repetir a mesma
letra (ex.: o N de "ANNA"), abaixe a mão rapidamente entre as duas. Muitas letras têm
formatos de mão parecidos: confira os pares confundidos na matriz de confusão depois de
treinar.

**Sem voz?** `python scripts/demonstracao/testar_voz.py` (ou menu → V) testa cada motor de
voz do sistema, um por vez (no Windows: as vozes do sistema pelo PowerShell/System.Speech,
que é o padrão, e o pyttsx3). Se só um funcionar, escolha-o em `MOTOR_VOZ` no `config.py`.

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
python scripts/desenvolvimento/empacotar_app.py   # gera dist/Librahin-demo.zip
```

O zip leva só o necessário (código da aplicação, `requirements.txt`, os modelos,
inclusive os do MediaPipe — útil em redes que bloqueiam o download — e o instalador de um
clique) e um `LEIA-ME.txt` com os comandos. No computador da apresentação: extrair, dois
cliques em `INSTALAR.bat` (instala só o `requirements.txt`) e depois no atalho
**Librahin** → opção 1.

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
**direita** deve mostrar "Mao direita" (em verde). O MediaPipe entrega os rótulos das mãos
invertidos com a imagem espelhada; os dados gravados usam os rótulos dele e só os nomes na
tela são corrigidos (`NOMES_MAOS_INVERTIDOS = True` no `config.py`). Se num computador a
tela mostrar os nomes trocados, mude para `False`. Não use `TROCAR_LADOS` com a coleta em
andamento: ele muda o que é gravado.

**2. Coletar dados** — preencha antes [`docs/SINAIS.md`](docs/SINAIS.md) com a variante
de cada sinal:

```bash
python scripts/desenvolvimento/coletar_dados.py --sinal OI --pessoa ana      # --label também funciona
python scripts/desenvolvimento/coletar_dados.py --sinal _NADA --pessoa ana   # classe "nenhum sinal"
python scripts/desenvolvimento/coletar_dados.py --sinal A --pessoa ana       # letras: A a Z e Ç (opcionais)
```

No menu do Windows (opção 3), digite `A-E` para gravar de A até E, `LETRAS` para o alfabeto
inteiro ou uma lista como `OI,A,B`.

ESPAÇO inicia/pausa a gravação contínua, D apaga a última amostra, Q/ESC sai. Fique a
~1 m da câmera com os ombros visíveis. São salvos só os landmarks
(`data/raw/<SINAL>/*.npy`), sem imagens. Meta: **40 amostras por sinal por pessoa, com 3
pessoas ou mais**, e o dobro para `_NADA`.

**3. Analisar o dataset:**

```bash
python scripts/desenvolvimento/analisar_dataset.py       # relatório + gráficos em reports/
python scripts/desenvolvimento/analisar_dataset.py --reconstruir-metadata   # após juntar gravações de várias pessoas
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
- Não traduz a gramática da Libras: a frase é a sequência de sinais (glosa), e só as
  sequências cadastradas no `frases.txt` viram português.
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
windows/                    instalador de um clique e menu (INSTALAR.bat, Librahin.bat)
```

Detalhes em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), seção 2.

## Equipe

Trabalho acadêmico do curso de Tecnologia em Análise e Desenvolvimento de Sistemas.

- Cauã Pedrozo Brito
- Adryel da Assunção Rocha
- Alber Alberguini Cabral
- João Francisco da Silva Malaquias

**Professor orientador:** Éder Lemes

Os créditos também aparecem no menu do Windows (`Librahin.bat` → **C**).
