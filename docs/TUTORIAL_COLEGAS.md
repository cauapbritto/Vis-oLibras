# Tutorial — como testar e gravar sinais para o Vis-oLibras

Este guia é para quem vai **instalar o projeto, testar a câmera e gravar sinais** para
treinar o modelo. Tempo total: cerca de **40 minutos** (15 de instalação, 25 de gravação).

Não precisa saber programar: é só copiar e colar os comandos no **PowerShell**
(tecla Windows → digite `PowerShell` → Enter). Cole **um bloco por vez** e espere
terminar antes do próximo.

> Parte A é para cada colega. Parte B é só para quem vai juntar as gravações e treinar.

---

## Parte A — Colegas

### A1. O que você precisa

- Computador com **Windows 10 ou 11** e **webcam**
- Internet (só para instalar)
- Um lugar **bem iluminado**, com a luz de frente para você (não de costas)

### A2. Instalar o Python 3.11

```powershell
winget install -e --id Python.Python.3.11 --source winget
```

**Feche e abra o PowerShell de novo** e confira:

```powershell
py -3.11 --version
```

Deve aparecer `Python 3.11.x`.

> Se o `winget` não funcionar: baixe o **Python 3.11 (Windows installer 64-bit)** em
> https://www.python.org/downloads/windows/ e, na primeira tela do instalador, **marque
> "Add python.exe to PATH"** antes de clicar em Install Now.

### A3. Baixar o projeto

1. Abra https://github.com/cauapbritto/Vis-oLibras
2. Clique no botão verde **Code** → **Download ZIP**
3. Salve na pasta **Downloads**

Descompacte e renomeie a pasta para `Vis-oLibras` (o nome original é longo):

```powershell
cd $HOME\Downloads
Expand-Archive .\Vis-oLibras-*.zip -DestinationPath . -Force
Get-ChildItem -Directory -Filter "Vis-oLibras-*" | Rename-Item -NewName "Vis-oLibras"
cd .\Vis-oLibras
```

### A4. Instalar as dependências

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Depois do `Activate.ps1` deve aparecer **`(.venv)`** no começo da linha. A instalação
demora alguns minutos.

> **Erro `CERTIFICATE_VERIFY_FAILED`** (comum na rede da faculdade/empresa): rode
> `python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org`
> e depois repita o `pip install -r requirements-dev.txt`. Se continuar, use outra rede
> (roteador do celular).

### A5. Testar a câmera

```powershell
python scripts/desenvolvimento/testar_deteccao.py
```

Confira e depois aperte **Q** para sair:

- [ ] A imagem aparece **espelhada** (como um espelho)
- [ ] Levantando **só a mão direita** aparece "Mao direita" (linha verde)
- [ ] Levantando **só a esquerda** aparece "Mao esquerda" (linha azul)
- [ ] FPS **15 ou mais**

> Câmera não abre? Feche Teams, Zoom e o navegador. Tem mais de uma câmera? Tente
> `python scripts/desenvolvimento/testar_deteccao.py --camera 1`.

### A6. Combinar os sinais com o grupo

Antes de gravar, **todos devem fazer cada sinal do mesmo jeito**. Confiram juntos no
[Dicionário de Libras do INES](https://dicionario.ines.gov.br/) e anotem em
`docs/SINAIS.md`. Os sinais do projeto são:

**OI · EU · MEU · NOME · BOM · DIA · OBRIGADO · SIM · NÃO · AJUDA**

### A7. Gravar

Troque `seunome` pelo **seu nome, só letras minúsculas e números, sem espaço nem acento**
(ex.: `ana`, `joao2`). Use sempre o mesmo nome.

Cole este bloco inteiro de uma vez:

```powershell
$pessoa = "seunome"
$sinais = "OI","EU","MEU","NOME","BOM","DIA","OBRIGADO","SIM","NAO","AJUDA"
foreach ($s in $sinais) {
    Write-Host "`n=== Próximo sinal: $s ===" -ForegroundColor Cyan
    Read-Host "Pressione Enter para abrir a câmera"
    python scripts/desenvolvimento/coletar_dados.py --sinal $s --pessoa $pessoa --meta 30
}
Write-Host "`n=== Agora: NENHUM SINAL (_NADA) ===" -ForegroundColor Cyan
Read-Host "Pressione Enter para abrir a câmera"
python scripts/desenvolvimento/coletar_dados.py --sinal _NADA --pessoa $pessoa --meta 60
```

**Em cada janela da câmera:**

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
> Precisou parar no meio? Aperte Ctrl+C. O que já foi gravado fica salvo; depois rode de
> novo só com os sinais que faltam (ex.: `$sinais = "BOM","DIA"`).

### A8. Conferir e enviar as gravações

Confira quantas gravações você fez de cada sinal:

```powershell
Get-ChildItem data\raw -Recurse -Filter *.npy | Group-Object { $_.Directory.Name } | Select-Object Name, Count
```

Deve aparecer ~30 em cada sinal e ~60 no `_NADA`. Então crie o arquivo para enviar:

```powershell
Compress-Archive -Path data\raw -DestinationPath "gravacoes_$pessoa.zip" -Force
```

Envie o arquivo `gravacoes_seunome.zip` (fica na pasta `Vis-oLibras`) para o responsável
pelo treino (grupo, Drive, e-mail). É pequeno: só pontos das mãos, **nenhuma imagem ou
vídeo seu é gravado**.

### A9. (Depois do treino) Testar o reconhecimento

Quando o responsável enviar o modelo treinado (3 arquivos: `classificador.joblib`,
`classes.json` e `classificador_info.json`), copie-os para a pasta `models` e rode:

```powershell
cd $HOME\Downloads\Vis-oLibras
.venv\Scripts\Activate.ps1
python scripts/demonstracao/app.py
```

Clique em **Iniciar câmera** e faça os sinais, **abaixando as mãos entre um e outro**.
Para gerar as métricas do trabalho, faça também o teste controlado (cada sinal 10 vezes):

```powershell
python scripts/desenvolvimento/teste_controlado.py --participante seunome --incluir-nada
```

**ESPAÇO** começa, faça o sinal pedido quando aparecer **"JÁ!"**, **D** descarta se você
errou o sinal, **Q** sai. Envie ao responsável o arquivo `.csv` que aparece em
`reports\testes\`.

---

## Parte B — Responsável pelo treino

### B1. Juntar as gravações de todos

Coloque todos os `gravacoes_*.zip` na pasta `Vis-oLibras` e rode:

```powershell
cd $HOME\Downloads\Vis-oLibras
.venv\Scripts\Activate.ps1
Get-ChildItem gravacoes_*.zip | ForEach-Object { Expand-Archive $_.FullName -DestinationPath data -Force }
python scripts/desenvolvimento/analisar_dataset.py --reconstruir-metadata
```

Os arquivos de cada pessoa têm nomes diferentes, então nada é sobrescrito. O
`--reconstruir-metadata` recria o índice (`data\metadata.csv`) com as gravações de todos.
Confira no relatório: amostras por sinal, **pessoas** por sinal, inválidas e sinais parecidos
(gráficos em `reports\analise_dataset.png`).

### B2. Treinar e avaliar

```powershell
python scripts/desenvolvimento/treinar_modelo.py
```

Anote para o trabalho a **accuracy no teste**, a média do **"TESTE COM PESSOAS NOVAS"**
e os **sinais confundidos** (matriz em `reports\matriz_confusao.png`).

### B3. Distribuir o modelo

- **Para os colegas testarem:** envie os 3 arquivos da pasta `models`:
  `classificador.joblib`, `classes.json` e `classificador_info.json`.
  (Todos devem ter a mesma versão do scikit-learn: confira com `pip show scikit-learn`.)
- **Para o computador da apresentação:** gere o pacote pronto, que já inclui o modelo:

  ```powershell
  python scripts/desenvolvimento/empacotar_app.py
  ```

  O arquivo fica em `dist\Vis-oLibras-demo.zip`, com um `LEIA-ME.txt`.

### B4. Resumo das métricas dos testes controlados

Coloque os `.csv` recebidos em `reports\testes\` e rode:

```powershell
python scripts/desenvolvimento/resumir_testes.py
```

Os resultados (accuracy, precision, recall, F1, tempos, matriz de confusão) ficam em
`reports\testes\resumo\`, prontos para gráficos e para o relatório.

---

## Problemas comuns

| Problema | Solução |
|---|---|
| `py` não é reconhecido | Feche e abra o PowerShell; ou reinstale o Python marcando "Add to PATH" |
| Erro vermelho no `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force` |
| `No module named ...` | Esqueceu de ativar: `.venv\Scripts\Activate.ps1` (tem que aparecer `(.venv)`) |
| `can't open file ...` | Você não está na pasta do projeto: `cd $HOME\Downloads\Vis-oLibras` |
| `CERTIFICATE_VERIFY_FAILED` | Ver dica do passo A4, ou usar outra rede |
| Câmera não abre | Feche Teams/Zoom/navegador; tente `--camera 1` |
| Tudo "Descartada" | Afaste-se (ombros visíveis) e melhore a luz |
| Tecla Q não responde | Clique uma vez na janela da câmera e aperte Q de novo |
| Voz em inglês ou muda | Windows: Configurações → Hora e idioma → Idioma → adicionar Português (Brasil) com fala |
