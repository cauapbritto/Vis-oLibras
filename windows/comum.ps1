# Funções usadas pelo instalador e pelo menu do Vis-oLibras.
$ErrorActionPreference = "Continue"
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

$NoWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
if ($NoWindows) { $PythonVenv = Join-Path $Raiz ".venv\Scripts\python.exe" }
else            { $PythonVenv = Join-Path $Raiz ".venv/bin/python" }

# O pacote de demonstração (empacotar_app.py) não tem os scripts de treino.
$ModoDesenvolvimento = Test-Path (Join-Path $Raiz "scripts/desenvolvimento")

function Titulo([string]$texto) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkCyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor DarkCyan
}
function Ok([string]$texto)    { Write-Host "   [OK]    $texto" -ForegroundColor Green }
function Aviso([string]$texto) { Write-Host "   [AVISO] $texto" -ForegroundColor Yellow }
function Erro([string]$texto)  { Write-Host "   [ERRO]  $texto" -ForegroundColor Red }
function Pausar { [void](Read-Host "`nPressione Enter para continuar") }

function Sem-Acentos([string]$texto) {
    $decomposto = $texto.Normalize([Text.NormalizationForm]::FormD)
    $limpo = -join ($decomposto.ToCharArray() | Where-Object {
        [Globalization.CharUnicodeInfo]::GetUnicodeCategory($_) -ne [Globalization.UnicodeCategory]::NonSpacingMark })
    return $limpo
}
