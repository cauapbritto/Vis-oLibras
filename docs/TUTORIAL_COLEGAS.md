# Tutorial — como testar e gravar sinais para o Vis-oLibras

Este guia é para quem vai **instalar o projeto, testar a câmera e gravar sinais** para
treinar o modelo. Tempo total: cerca de **40 minutos** (10 a 15 de instalação, 25 de
gravação). Não precisa saber programar nem digitar comandos: é tudo por **dois cliques**
e um **menu com números**.

> Parte A é para cada colega. Parte B é só para quem vai juntar as gravações e treinar.
> Se o instalador não funcionar no seu computador, use os
> [comandos manuais](#apêndice--instalação-manual-pelo-powershell) no fim.

---

## Parte A — Colegas

### A1. O que você precisa

- Computador com **Windows 10 ou 11** e **webcam**
- Internet (só para instalar)
- Um lugar **bem iluminado**, com a luz de frente para você (não de costas)

### A2. Baixar o projeto

1. Abra https://github.com/cauapbritto/Vis-oLibras
2. Clique no botão verde **Code** → **Download ZIP**
3. Abra a pasta **Downloads**, clique com o botão direito no zip → **Extrair tudo…** →
   **Extrair**

> Use a pasta extraída, não abra os arquivos de dentro do zip (o instalador não
> funciona lá dentro).

### A3. Instalar (um clique)

Na pasta extraída, dê **dois cliques em `INSTALAR.bat`**.

- Se aparecer **"O Windows protegeu o computador"**: clique em **Mais informações** →
  **Executar assim mesmo** (o aviso aparece para qualquer arquivo baixado da internet).
- Uma janela preta mostra 6 passos. Se não houver Python, ele instala o **Python 3.11**
  sozinho (o Windows pode pedir permissão: clique em **Sim**).
- A instalação das bibliotecas demora alguns minutos. No fim aparece
  **"Instalação concluída!"** e um atalho **Vis-oLibras** na Área de Trabalho.

Pode rodar o `INSTALAR.bat` de novo quantas vezes precisar: ele aproveita o que já foi
instalado. Se algo der errado, a mensagem em vermelho diz o que fazer, e os detalhes ficam
no arquivo `instalar.log` da pasta do projeto.

> **"Python não encontrado"** mesmo depois do passo 1: instale o **Python 3.11 (Windows
> installer 64-bit)** de https://www.python.org/downloads/windows/, **marcando "Add
> python.exe to PATH"** na primeira tela, e rode o `INSTALAR.bat` de novo.

### A4. Abrir o menu

Dê dois cliques no atalho **Vis-oLibras** da Área de Trabalho (ou em `Vis-oLibras.bat`,
na pasta do projeto). Aparece o menu:

```
   APRESENTAÇÃO
     1  Abrir a aplicação
     2  Testar a câmera

   GRAVAR E TREINAR
     3  Gravar sinais
     4  Ver quantas gravações existem
     5  Gerar arquivo com minhas gravações (para enviar)
     6  Juntar gravações recebidas (gravacoes_*.zip)
     7  Analisar o dataset
     8  Treinar o modelo
     9  Teste controlado (métricas do trabalho)

     0  Sair
```

Digite o número e aperte **Enter**.

### A5. Testar a câmera (opção 2)

Confira e depois aperte **Q** na janela da câmera para voltar ao menu:

- [ ] A imagem aparece **espelhada** (como um espelho)
- [ ] Levantando **só a mão direita** aparece "Mao direita" (linha verde)
- [ ] Levantando **só a esquerda** aparece "Mao esquerda" (linha azul)
- [ ] FPS **15 ou mais**

> Câmera não abre? Feche Teams, Zoom e o navegador e tente de novo.

### A6. Combinar os sinais com o grupo

Antes de gravar, **todos devem fazer cada sinal do mesmo jeito**. Confiram juntos no
[Dicionário de Libras do INES](https://dicionario.ines.gov.br/) e anotem em
`docs/SINAIS.md`. Os sinais do projeto são:

**OI · EU · MEU · NOME · BOM · DIA · OBRIGADO · SIM · NÃO · AJUDA**

### A7. Gravar (opção 3)

O menu pergunta:

1. **Seu nome** — só letras e números, sem espaço (ex.: `ana`, `joao2`). Use **sempre o
   mesmo nome**.
2. **Quais sinais** — aperte **Enter** para gravar todos (ou digite só alguns, ex.:
   `BOM,DIA`, se precisar continuar depois).
3. **Gravar o NENHUM SINAL no final?** — aperte **Enter** (sim).

Para cada sinal, aperte Enter para abrir a câmera. **Em cada janela da câmera:**

1. Fique a **~1 metro**, com **ombros e mãos aparecendo** ("Ombros: OK" no painel)
2. Aperte **ESPAÇO** → contagem de 3 s
3. Quando a **borda ficar vermelha**, faça o sinal (você tem 1,5 s)
4. **Abaixe as mãos** — o programa grava a próxima sozinho, 1 s depois
5. Errou? Aperte **D** para apagar a última gravação
6. Chegou em **30** ("Sessão: 30/30")? Aperte **Q** → abre o próximo sinal

**No `_NADA` (60 gravações) NÃO faça sinais:** fique parado, coce o rosto, ajeite o
cabelo ou os óculos, mexa as mãos à toa. Isso ensina o sistema o que **não** é sinal.

> "Descartada" em amarelo? Leia o motivo: *ombros não visíveis* → afaste-se; *mãos em só
> X%* → mantenha a mão visível durante todo o sinal. O que foi descartado não conta.
>
> Precisou parar no meio? Feche a janela preta. O que já foi gravado fica salvo; depois
> escolha a opção 3 de novo e digite só os sinais que faltam.

### A8. Conferir e enviar as gravações (opções 4 e 5)

- **Opção 4** mostra quantas gravações existem de cada sinal: deve aparecer ~30 em cada
  sinal e ~60 no `_NADA`, com o seu nome entre parênteses.
- **Opção 5** pede o seu nome e cria o arquivo **`gravacoes_seunome.zip`** na pasta do
  projeto (a pasta abre sozinha, com o arquivo selecionado).

Envie esse arquivo para o responsável pelo treino (grupo, Drive, e-mail). É pequeno: só
pontos das mãos, **nenhuma imagem ou vídeo seu é gravado**.

### A9. (Depois do treino) Testar o reconhecimento

Quando o responsável enviar o modelo treinado (3 arquivos: `classificador.joblib`,
`classes.json` e `classificador_info.json`), copie-os para a pasta `models` do projeto.
Abra o menu e escolha a **opção 1**. Clique em **Iniciar câmera** e faça os sinais,
**abaixando as mãos entre um e outro**.

Para gerar as métricas do trabalho, faça também o **teste controlado (opção 9)**: cada
sinal 10 vezes. **ESPAÇO** começa, faça o sinal pedido quando aparecer **"JÁ!"**, **D**
descarta se você errou o sinal, **Q** sai. Envie ao responsável o arquivo `.csv` que
aparece em `reports\testes\`.

---

## Parte B — Responsável pelo treino

Instale como na Parte A (A2 e A3).

### B1. Juntar as gravações de todos (opção 6)

Coloque todos os `gravacoes_*.zip` recebidos na pasta do projeto (a mesma do
`INSTALAR.bat`) e escolha a **opção 6**. Ela descompacta tudo em `data\raw`, recria o
índice das gravações (`data\metadata.csv`) e mostra o relatório do dataset. Os arquivos de
cada pessoa têm nomes diferentes, então nada é sobrescrito.

Confira no relatório: amostras por sinal, **pessoas** por sinal, amostras inválidas e
sinais parecidos. A **opção 7** repete a análise quando quiser (gráficos em
`reports\analise_dataset.png`).

### B2. Treinar e avaliar (opção 8)

Anote para o trabalho a **accuracy no teste**, a média do **"TESTE COM PESSOAS NOVAS"**
e os **sinais confundidos** (matriz em `reports\matriz_confusao.png`).

### B3. Distribuir o modelo

- **Para os colegas testarem:** envie os 3 arquivos da pasta `models`:
  `classificador.joblib`, `classes.json` e `classificador_info.json`.
  (Todos devem ter a mesma versão do scikit-learn; quem instalou pelo `INSTALAR.bat` no
  mesmo período terá.)
- **Para o computador da apresentação:** gere o pacote pronto, que já inclui o modelo e o
  instalador. No PowerShell, dentro da pasta do projeto:

  ```powershell
  .venv\Scripts\python.exe scripts/desenvolvimento/empacotar_app.py
  ```

  O arquivo fica em `dist\Vis-oLibras-demo.zip`. No computador da apresentação: extrair,
  dois cliques em `INSTALAR.bat` e depois no atalho **Vis-oLibras** → opção 1.

### B4. Resumo das métricas dos testes controlados

Coloque os `.csv` recebidos em `reports\testes\` e rode no PowerShell, dentro da pasta do
projeto:

```powershell
.venv\Scripts\python.exe scripts/desenvolvimento/resumir_testes.py
```

Os resultados (accuracy, precision, recall, F1, tempos, matriz de confusão) ficam em
`reports\testes\resumo\`, prontos para gráficos e para o relatório.

---

## Problemas comuns

| Problema | Solução |
|---|---|
| "O Windows protegeu o computador" | **Mais informações** → **Executar assim mesmo** |
| "Extraia o zip antes de usar" | Você abriu o `.bat` de dentro do zip: extraia (A2) e rode o da pasta extraída |
| "O projeto ainda não foi instalado" | Rode o `INSTALAR.bat` primeiro |
| "Python não encontrado" | Ver a dica do passo A3 |
| "Este Python veio sem o tkinter" | Siga a mensagem: instalador do Python → Modify → marque *tcl/tk and IDLE*; apague a pasta `.venv` e rode o `INSTALAR.bat` |
| Erro nas bibliotecas / `CERTIFICATE_VERIFY_FAILED` | A rede (faculdade/empresa) está bloqueando: conecte em outra rede (roteador do celular) e rode o `INSTALAR.bat` de novo |
| Câmera não abre | Feche Teams/Zoom/navegador |
| Tudo "Descartada" | Afaste-se (ombros visíveis) e melhore a luz |
| Tecla Q não responde | Clique uma vez na janela da câmera e aperte Q de novo |
| Voz em inglês ou muda | Configurações → Hora e idioma → Idioma e região → adicionar Português (Brasil) com fala |

---

## Apêndice — instalação manual pelo PowerShell

Se o `INSTALAR.bat` não funcionar, faça o mesmo à mão. Abra o **PowerShell** (tecla
Windows → digite `PowerShell` → Enter) e cole **um bloco por vez**:

```powershell
winget install -e --id Python.Python.3.11 --source winget
```

Feche e abra o PowerShell de novo. Entre na pasta extraída (troque pelo caminho certo) e
instale:

```powershell
cd $HOME\Downloads\Vis-oLibras-claude-libras-text-speech-architecture-up1w9y
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Depois do `Activate.ps1` deve aparecer **`(.venv)`** no começo da linha. Em redes que
interceptam HTTPS (`CERTIFICATE_VERIFY_FAILED`), atualize o pip com
`python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org`
e repita o `pip install`.

Equivalentes das opções do menu (com o `(.venv)` ativo):

| Opção | Comando |
|---|---|
| 1 | `python scripts/demonstracao/app.py` |
| 2 | `python scripts/desenvolvimento/testar_deteccao.py` |
| 3 | `python scripts/desenvolvimento/coletar_dados.py --sinal OI --pessoa seunome --meta 30` (um sinal por vez; `_NADA` com `--meta 60`) |
| 6 | `Get-ChildItem gravacoes_*.zip \| ForEach-Object { Expand-Archive $_.FullName -DestinationPath data -Force }` e depois `python scripts/desenvolvimento/analisar_dataset.py --reconstruir-metadata` |
| 7 | `python scripts/desenvolvimento/analisar_dataset.py` |
| 8 | `python scripts/desenvolvimento/treinar_modelo.py` |
| 9 | `python scripts/desenvolvimento/teste_controlado.py --participante seunome --incluir-nada` |
