# Librahin em container (Docker)

O container leva o Python, as bibliotecas e os modelos do MediaPipe já instalados:
em qualquer máquina com Docker, é só montar a imagem e rodar, sem instalar Python nem
dependências. Todos usam **as mesmas versões** (incluindo o scikit-learn), então um modelo
treinado num computador funciona nos outros.

## O que funciona onde

| Tarefa | Linux | Windows / macOS (Docker Desktop) |
|---|---|---|
| Treinar o modelo | ✅ | ✅ |
| Analisar o dataset, resumir testes | ✅ | ✅ |
| Testes automáticos | ✅ | ✅ |
| Coletar dados (webcam) | ✅ | ❌ |
| Interface / reconhecimento ao vivo (webcam + janela + som) | ✅ | ❌ |

**Por que não no Windows/macOS?** O Docker Desktop roda os containers numa máquina
virtual que **não enxerga a webcam** (nem, por padrão, a tela e o som). Nesses sistemas,
use o container para **treinar**, e a instalação normal (`requirements.txt`, ver
[`TUTORIAL_COLEGAS.md`](TUTORIAL_COLEGAS.md)) para **coletar e demonstrar**.

## 1. Instalar o Docker e montar a imagem

- **Windows/macOS:** instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux (Ubuntu):** `sudo apt install docker.io docker-compose-v2` e
  `sudo usermod -aG docker $USER` (saia e entre de novo na sessão)

Na pasta do projeto (uma vez; baixa cerca de 1,5 GB):

```bash
docker compose build
```

> **Rede que intercepta HTTPS** (erro de certificado, como na faculdade): peça à TI o
> certificado da rede (`.crt`) e monte assim:
> `docker build --secret id=ca,src=certificado-da-rede.crt -t librahin .`

## 2. Treinar, analisar e testar (qualquer sistema)

As pastas `data/`, `models/` e `reports/` do projeto são usadas pelo container: as
gravações ficam no seu computador, e o modelo e os relatórios aparecem nelas.

```bash
docker compose run --rm analisar      # relatório do dataset (reports/)
docker compose run --rm treinar       # treina com data/raw e salva em models/
docker compose run --rm testes        # testes automáticos
```

Qualquer outro comando do projeto também funciona:

```bash
docker compose run --rm treinar python scripts/desenvolvimento/treinar_modelo.py --modelo rf
docker compose run --rm treinar python scripts/desenvolvimento/analisar_dataset.py --reconstruir-metadata
docker compose run --rm treinar python scripts/desenvolvimento/resumir_testes.py
docker compose run --rm treinar python scripts/desenvolvimento/empacotar_app.py
```

No Windows (PowerShell), os comandos são os mesmos.

## 3. Coletar e usar a interface (só Linux)

Libere a tela para o container (uma vez por sessão) e rode:

```bash
xhost +local:
export LIBRAS_UID=$(id -u) LIBRAS_GID=$(id -g)   # arquivos criados ficam no seu usuário
docker compose run --rm app                                          # interface gráfica
docker compose run --rm coletar python scripts/desenvolvimento/coletar_dados.py --sinal OI --pessoa ana
```

Outra câmera: `LIBRAS_CAMERA=1 docker compose run --rm app` (e troque `/dev/video0` por
`/dev/video1` em `docker-compose.yml`). Sem som? Confira se `/dev/snd` existe no computador.

## 4. Levar a imagem pronta para outra máquina (sem internet)

```bash
docker save librahin | gzip > librahin-imagem.tar.gz     # na máquina que montou
docker load -i librahin-imagem.tar.gz                        # na outra máquina
```

O arquivo tem cerca de 400 MB. Depois, na outra máquina, os comandos `docker compose run`
funcionam sem precisar montar de novo (copie também a pasta do projeto, por causa do
`docker-compose.yml` e das pastas `data/`, `models/` e `reports/`).

## Problemas comuns

| Problema | Solução |
|---|---|
| `permission denied ... docker.sock` (Linux) | `sudo usermod -aG docker $USER`, saia e entre de novo |
| Arquivos em `models/` ou `reports/` pertencem ao root (Linux) | `export LIBRAS_UID=$(id -u) LIBRAS_GID=$(id -g)` antes do `docker compose run` |
| `cannot open display` (Linux) | Rode `xhost +local:` e confira `echo $DISPLAY` |
| "Não foi possível abrir a câmera" (Linux) | Confira `ls /dev/video*`; ajuste o dispositivo no `docker-compose.yml` |
| Erro de certificado no `build` | Ver a dica do passo 1 |
