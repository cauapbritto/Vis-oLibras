# Instalador de um clique do Librahin (chamado pelo INSTALAR.bat).
# Pode ser executado de novo quantas vezes quiser: o que já existe é aproveitado.
. (Join-Path $PSScriptRoot "comum.ps1")
$Log = Join-Path $Raiz "instalar.log"
# Python em modo UTF-8: sem isso, no Windows o pip lê arquivos com a codificação
# antiga do sistema (cp1252) e pode travar em acentos.
$env:PYTHONUTF8 = "1"
try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

function Encerrar([int]$codigo) {
    try { Stop-Transcript | Out-Null } catch {}
    if ($codigo -ne 0) { Write-Host "`nDetalhes em: $Log" -ForegroundColor Yellow }
    Pausar
    exit $codigo
}

function Encontrar-Python {
    # Devolve o comando de um Python 3.10 a 3.12 (preferência: 3.11), ou $null.
    foreach ($versao in "3.11", "3.12", "3.10") {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py "-$versao" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$versao") }
        }
    }
    foreach ($nome in "python", "python3") {
        if (Get-Command $nome -ErrorAction SilentlyContinue) {
            $versao = & $nome -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $versao -in "3.10", "3.11", "3.12") { return @($nome) }
        }
    }
    return $null
}

function Executar-Python([string[]]$comando, [string[]]$argumentos) {
    $programa = $comando[0]
    $extras = @($comando | Select-Object -Skip 1)
    & $programa @extras @argumentos
    return $LASTEXITCODE
}

Titulo "Librahin - Instalação"
Write-Host "   Pasta: $Raiz"

# Caminho longo: o Windows limita caminhos a 260 caracteres (se os caminhos longos não
# estiverem liberados) e algumas bibliotecas têm arquivos ~115 caracteres dentro do .venv.
# Acontece quando o zip é extraído com a pasta repetida (...up1w9y\...up1w9y).
function Caminhos-Longos-Liberados {
    try {
        $chave = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -ErrorAction Stop
        return $chave.LongPathsEnabled -eq 1
    } catch { return $false }
}
$LimiteCaminho = 100
if ($NoWindows -and $Raiz.Length -gt $LimiteCaminho -and -not (Caminhos-Longos-Liberados)) {
    Aviso "O caminho desta pasta é longo demais para o Windows ($($Raiz.Length) caracteres)."
    Write-Host "   A instalação falharia no meio. A solução é usar uma pasta de caminho curto."
    $destino = Join-Path $HOME "Librahin"
    $n = 2
    while (Test-Path $destino) { $destino = Join-Path $HOME "Librahin$n"; $n++ }
    $resposta = Read-Host "Copiar o projeto para $destino e instalar lá? [S/n]"
    if ("$resposta" -match "^[nN]") {
        Erro "Mova a pasta do projeto para um caminho curto (ex.: $HOME\Librahin) e rode o INSTALAR.bat de novo."
        Encerrar 1
    }
    New-Item -ItemType Directory -Path $destino | Out-Null
    Get-ChildItem $Raiz -Force | Where-Object { $_.Name -notin ".venv", "instalar.log" } |
        Copy-Item -Destination $destino -Recurse -Force
    Ok "Projeto copiado para $destino (com as gravações e o modelo, se houver)"
    Write-Host "   A instalação continua numa nova janela. Esta pasta antiga pode ser apagada depois."
    try { Stop-Transcript | Out-Null } catch {}
    Start-Process (Join-Path $destino "INSTALAR.bat") -WorkingDirectory $destino
    exit 0
}

# 1. Python ------------------------------------------------------------------
Titulo "[1/6] Python 3.10 a 3.12"
$python = Encontrar-Python
if (-not $python -and $NoWindows -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "   Python não encontrado. Instalando o Python 3.11 pelo winget..."
    winget install -e --id Python.Python.3.11 --source winget --silent `
        --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    $python = Encontrar-Python
}
if (-not $python) {
    Erro "Python 3.10 a 3.12 não encontrado."
    Write-Host "   Instale o Python 3.11 pelo site (vou abrir a página). Na primeira tela do"
    Write-Host "   instalador, MARQUE 'Add python.exe to PATH'. Depois rode o INSTALAR.bat de novo."
    if ($NoWindows) { Start-Process "https://www.python.org/downloads/windows/" }
    Encerrar 1
}
Ok ("Python encontrado: " + ($python -join " "))

# 2. Ambiente virtual --------------------------------------------------------
Titulo "[2/6] Ambiente virtual (.venv)"
if (Test-Path $PythonVenv) {
    Ok "Ambiente já existe, reaproveitando"
} else {
    if ((Executar-Python $python @("-m", "venv", ".venv")) -ne 0 -or -not (Test-Path $PythonVenv)) {
        Erro "Não foi possível criar o ambiente virtual."
        Encerrar 1
    }
    Ok "Ambiente criado"
}

# 3. pip atualizado (usa os certificados do Windows: resolve redes com proxy) --
Titulo "[3/6] Atualizando o pip"
# O pip 24.2 ou mais novo usa os certificados do Windows, o que resolve as redes que
# interceptam HTTPS (faculdade, empresa). Atenção: sem conseguir acessar a internet,
# o pip diz "já instalado" e termina SEM erro, então conferimos a versão.
function Pip-Atualizado {
    & $PythonVenv -c "import pip, sys; v = tuple(int(x) for x in pip.__version__.split('.')[:2]); sys.exit(0 if v >= (24, 2) else 1)"
    return $LASTEXITCODE -eq 0
}
& $PythonVenv -m pip install --upgrade pip
if (-not (Pip-Atualizado)) {
    Aviso "A rede bloqueou a atualização (comum em redes que interceptam HTTPS). Tentando de novo..."
    & $PythonVenv -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
}
if (-not (Pip-Atualizado)) {
    Erro "Não foi possível atualizar o pip. Verifique a internet ou use outra rede (ex.: roteador do celular)."
    Encerrar 1
}
$versaoPip = & $PythonVenv -c "import pip; print(pip.__version__)"
Ok "pip atualizado (versão $versaoPip)"

# 4. Dependências --------------------------------------------------------------
Titulo "[4/6] Instalando as bibliotecas (alguns minutos)"
$requisitos = if ($ModoDesenvolvimento) { "requirements-dev.txt" } else { "requirements.txt" }
& $PythonVenv -m pip install -r $requisitos
if ($LASTEXITCODE -ne 0) {
    Aviso "Falhou. Tentando de novo sem verificar o certificado do PyPI (redes com proxy)..."
    & $PythonVenv -m pip install -r $requisitos --trusted-host pypi.org --trusted-host files.pythonhosted.org
}
if ($LASTEXITCODE -ne 0) {
    Erro "A instalação das bibliotecas falhou. Se o erro fala em CERTIFICATE_VERIFY_FAILED,"
    Write-Host "   a rede está bloqueando: conecte em outra rede (ex.: roteador do celular) e rode de novo."
    Encerrar 1
}
$faltando = & $PythonVenv -c "import importlib.util as u; print(' '.join(m for m in ['tkinter', 'cv2', 'mediapipe', 'sklearn', 'numpy', 'customtkinter', 'pyttsx3', 'PIL'] if u.find_spec(m) is None))"
if ("$faltando" -match "tkinter") {
    Erro "Este Python veio sem o tkinter (a parte que desenha as janelas)."
    Write-Host "   Rode o instalador do Python de novo > Modify > marque 'tcl/tk and IDLE'."
    Write-Host "   Depois apague a pasta .venv do projeto e rode o INSTALAR.bat de novo."
    Encerrar 1
}
& $PythonVenv -c "import cv2, mediapipe, sklearn, numpy, customtkinter, pyttsx3, PIL"
if ($LASTEXITCODE -ne 0) {
    Erro "As bibliotecas foram instaladas, mas não carregam (faltando: $faltando). Veja o erro acima."
    Write-Host "   Apague a pasta .venv do projeto e rode o INSTALAR.bat de novo. Se o erro falar em"
    Write-Host "   'Long Path' ou 'No such file', mova o projeto para uma pasta de caminho curto (ex.: $HOME\Librahin)."
    Encerrar 1
}
Ok "Bibliotecas instaladas e funcionando"

# 5. Modelos do MediaPipe e voz ------------------------------------------------
Titulo "[5/6] Modelos do MediaPipe e voz"
$codigo = "import sys; sys.path.insert(0, 'src'); from libras import config; " +
          "from libras.extrator import garantir_modelo; " +
          "garantir_modelo(config.ARQ_HAND_LANDMARKER, config.URL_HAND_LANDMARKER); " +
          "garantir_modelo(config.ARQ_POSE_LANDMARKER, config.URL_POSE_LANDMARKER)"
& $PythonVenv -c $codigo
if ($LASTEXITCODE -eq 0) { Ok "Modelos do MediaPipe prontos (a câmera funciona sem internet)" }
else { Aviso "Não baixou agora; será baixado na primeira vez que a câmera abrir." }

$voz = & $PythonVenv -c "import sys; sys.path.insert(0, 'src'); from libras.voz import Voz; v = Voz(); print(v.nome_voz if v.disponivel else 'INDISPONIVEL'); v.encerrar()" 2>$null
if ($voz -match "INDISPONIVEL" -or -not $voz) {
    Aviso "Nenhuma voz encontrada: o programa funciona, mas sem falar."
} elseif ($voz -match "portug|brazil|pt-br|pt_br|maria|daniel|luciana") {
    Ok "Voz em português: $voz"
} else {
    Aviso "Voz encontrada ($voz), mas não parece ser em português."
    Write-Host "   Windows: Configurações > Hora e idioma > Idioma e região > adicionar"
    Write-Host "   'Português (Brasil)' com o recurso de Fala."
}

# 6. Atalho na Área de Trabalho --------------------------------------------------
Titulo "[6/6] Atalho"
if ($NoWindows) {
    try {
        $area = [Environment]::GetFolderPath("Desktop")
        $atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $area "Librahin.lnk"))
        $atalho.TargetPath = Join-Path $Raiz "Librahin.bat"
        $atalho.WorkingDirectory = $Raiz
        $atalho.Description = "Librahin - Libras para texto e voz"
        $icone = Join-Path $Raiz "src\libras\recursos\icone.ico"
        if (Test-Path $icone) { $atalho.IconLocation = "$icone,0" }
        $atalho.Save()
        Ok "Atalho 'Librahin' criado na Área de Trabalho"
        # O projeto se chamava Vis-oLibras: apaga o atalho antigo, só se foi este instalador que o criou
        $antigo = Join-Path $area "Vis-oLibras.lnk"
        if (Test-Path $antigo) {
            $alvo = (New-Object -ComObject WScript.Shell).CreateShortcut($antigo).TargetPath
            if ($alvo -like "*\Vis-oLibras.bat") {
                Remove-Item $antigo -Force
                Ok "Atalho antigo 'Vis-oLibras' removido (o projeto agora se chama Librahin)"
            }
        }
    } catch {
        Aviso "Não foi possível criar o atalho. Use o arquivo Librahin.bat da pasta do projeto."
    }
} else {
    Aviso "Fora do Windows: rode ./windows/menu.ps1 com o pwsh, ou use os comandos do README."
}

Titulo "Instalação concluída!"
Write-Host "   Abra o 'Librahin' (atalho na Área de Trabalho ou Librahin.bat)."
Encerrar 0
