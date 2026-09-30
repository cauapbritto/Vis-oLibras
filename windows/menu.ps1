# Menu do Librahin (chamado pelo Librahin.bat).
. (Join-Path $PSScriptRoot "comum.ps1")
$Sinais = "OI", "EU", "MEU", "NOME", "BOM", "DIA", "OBRIGADO", "SIM", "NAO", "AJUDA"

if (-not (Test-Path $PythonVenv)) {
    Erro "O projeto ainda não foi instalado. Dê dois cliques em INSTALAR.bat primeiro."
    Pausar
    exit 1
}

function Rodar([string[]]$argumentos, [string]$seFalhar = "O comando terminou com erro. Veja a mensagem acima.") {
    & $PythonVenv @argumentos
    if ($LASTEXITCODE -ne 0) { Aviso $seFalhar }
}

$AvisoAnalise = "A análise encontrou problemas no dataset: veja INVÁLIDAS e INCONSISTÊNCIAS acima (relatório completo em reports\analise_dataset.txt)."

function Pedir-Nome {
    $nome = Read-Host "Seu nome (só letras e números, ex.: ana)"
    $nome = (Sem-Acentos $nome).ToLower() -replace "[^a-z0-9]", ""
    if (-not $nome) { Erro "Nome inválido."; return $null }
    return $nome
}

function Gravar-Sinais {
    $pessoa = Pedir-Nome
    if (-not $pessoa) { return }
    Write-Host "`nSinais: $($Sinais -join ', ')"
    $escolha = Read-Host "Quais gravar? Enter = todos, ou digite separados por vírgula (ex.: OI,SIM)"
    $lista = if ($escolha.Trim()) { $escolha.Split(",") | ForEach-Object { (Sem-Acentos $_).Trim().ToUpper() } | Where-Object { $_ } } else { $Sinais }
    $nada = Read-Host "Gravar também o NENHUM SINAL (_NADA) no final? [S/n]"

    Write-Host "`nEm cada janela: ESPAÇO começa, faça o sinal quando a borda ficar vermelha,"
    Write-Host "abaixe as mãos entre as gravações, D apaga a última, Q passa para o próximo."
    foreach ($sinal in $lista) {
        Titulo "Próximo sinal: $sinal"
        [void](Read-Host "Pressione Enter para abrir a câmera")
        Rodar @("scripts/desenvolvimento/coletar_dados.py", "--sinal", $sinal, "--pessoa", $pessoa, "--meta", "30")
    }
    if ($nada -notmatch "^[nN]") {
        Titulo "NENHUM SINAL (_NADA): fique natural, coce o rosto, mexa as mãos à toa"
        [void](Read-Host "Pressione Enter para abrir a câmera")
        Rodar @("scripts/desenvolvimento/coletar_dados.py", "--sinal", "_NADA", "--pessoa", $pessoa, "--meta", "60")
    }
    Ok "Gravação concluída. Para enviar, use a opção 'Gerar arquivo com minhas gravações'."
}

function Contar-Gravacoes {
    $pasta = Join-Path $Raiz "data/raw"
    $grupos = Get-ChildItem $pasta -Recurse -Filter *.npy -ErrorAction SilentlyContinue |
              Group-Object { $_.Directory.Name } | Sort-Object Name
    if (-not $grupos) { Aviso "Nenhuma gravação ainda."; return }
    Write-Host ""
    foreach ($g in $grupos) {
        $pessoas = ($g.Group | ForEach-Object { $_.BaseName.Split("_")[0] } | Sort-Object -Unique) -join ", "
        Write-Host ("   {0,-10} {1,4} gravações   ({2})" -f $g.Name, $g.Count, $pessoas)
    }
}

function Empacotar-Gravacoes {
    $pessoa = Pedir-Nome
    if (-not $pessoa) { return }
    $arquivos = Get-ChildItem (Join-Path $Raiz "data/raw") -Recurse -Filter "${pessoa}_*.npy" -ErrorAction SilentlyContinue
    if (-not $arquivos) { Erro "Nenhuma gravação com o nome '$pessoa'."; return }
    $temp = Join-Path ([IO.Path]::GetTempPath()) "librahin_$pessoa"
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($a in $arquivos) {
        $destino = Join-Path $temp ("raw/" + $a.Directory.Name)
        New-Item -ItemType Directory -Force -Path $destino | Out-Null
        Copy-Item $a.FullName $destino
    }
    $zip = Join-Path $Raiz "gravacoes_$pessoa.zip"
    Compress-Archive -Path (Join-Path $temp "raw") -DestinationPath $zip -Force
    Remove-Item $temp -Recurse -Force
    Ok "$($arquivos.Count) gravações em: $zip"
    Write-Host "   Envie esse arquivo para quem vai treinar o modelo."
    if ($NoWindows) { Start-Process explorer.exe "/select,`"$zip`"" }
}

function Juntar-Gravacoes {
    $zips = Get-ChildItem (Join-Path $Raiz "gravacoes_*.zip") -ErrorAction SilentlyContinue
    if (-not $zips) {
        Aviso "Coloque os arquivos gravacoes_*.zip recebidos na pasta do projeto:"
        Write-Host "   $Raiz"
        return
    }
    foreach ($z in $zips) {
        Expand-Archive $z.FullName -DestinationPath (Join-Path $Raiz "data") -Force
        Ok "Juntado: $($z.Name)"
    }
    Rodar @("scripts/desenvolvimento/analisar_dataset.py", "--reconstruir-metadata") $AvisoAnalise
}

function Conferir-Frases {
    Rodar @("scripts/demonstracao/testar_frases.py") "Corrija as linhas indicadas nos avisos acima."
    Write-Host ""
    Write-Host "   Para editar, abra o arquivo frases.txt da pasta do projeto no Bloco de Notas."
    while ($true) {
        $sinais = Read-Host "Teste uma sequência (ex.: EU NOME OBRIGADO), ou Enter para voltar"
        if (-not "$sinais".Trim()) { break }
        Rodar (@("scripts/demonstracao/testar_frases.py") + "$sinais".Trim().Split(" ", [StringSplitOptions]::RemoveEmptyEntries)) "Corrija as linhas indicadas nos avisos acima."
    }
}

function Mostrar-Creditos {
    Clear-Host
    Titulo "Créditos"
    Write-Host ""
    Write-Host "   Tradução de Libras para Texto e Voz utilizando" -ForegroundColor White
    Write-Host "   Visão Computacional e Inteligência Artificial" -ForegroundColor White
    Write-Host ""
    Write-Host "   EQUIPE" -ForegroundColor Cyan
    Write-Host "     Cauã Pedrozo Brito"
    Write-Host "     Adryel da Assunção Rocha"
    Write-Host "     Alber Alberguini Cabral"
    Write-Host "     João Francisco da Silva Malaquias"
    Write-Host ""
    Write-Host "   PROFESSOR ORIENTADOR" -ForegroundColor Cyan
    Write-Host "     Éder Lemes"
    Write-Host ""
    Write-Host "   Curso de Tecnologia em Análise e Desenvolvimento de Sistemas" -ForegroundColor DarkGray
    Write-Host "   Feito com Python, OpenCV, MediaPipe, scikit-learn e CustomTkinter" -ForegroundColor DarkGray
}

while ($true) {
    Clear-Host
    Titulo "Librahin - Libras para texto e voz"
    Write-Host "   APRESENTAÇÃO"
    Write-Host "     1  Abrir a aplicação"
    Write-Host "     V  Testar a voz"
    Write-Host "     F  Conferir a tabela de frases (frases.txt)"
    if ($ModoDesenvolvimento) {
        Write-Host "     2  Testar a câmera"
        Write-Host ""
        Write-Host "   GRAVAR E TREINAR"
        Write-Host "     3  Gravar sinais"
        Write-Host "     4  Ver quantas gravações existem"
        Write-Host "     5  Gerar arquivo com minhas gravações (para enviar)"
        Write-Host "     6  Juntar gravações recebidas (gravacoes_*.zip)"
        Write-Host "     7  Analisar o dataset"
        Write-Host "     8  Treinar o modelo"
        Write-Host "     9  Teste controlado (métricas do trabalho)"
    } else {
        Write-Host "     2  Versão simples (janela do OpenCV)"
    }
    Write-Host ""
    Write-Host "     C  Créditos"
    Write-Host "     0  Sair"
    $opcao = "$(Read-Host "`nEscolha uma opção")".Trim()
    if (-not $ModoDesenvolvimento -and $opcao -notin "0", "1", "2", "v", "f", "c") { $opcao = "invalida" }
    if (-not $ModoDesenvolvimento -and $opcao -eq "2") { $opcao = "simples" }
    switch ($opcao) {
        "1" { Rodar @("scripts/demonstracao/app.py") }
        "2" { Write-Host "Aperte Q na janela da câmera para voltar."; Rodar @("scripts/desenvolvimento/testar_deteccao.py") }
        "3" { Gravar-Sinais }
        "4" { Contar-Gravacoes }
        "5" { Empacotar-Gravacoes }
        "6" { Juntar-Gravacoes }
        "7" { Rodar @("scripts/desenvolvimento/analisar_dataset.py") $AvisoAnalise }
        "8" { Rodar @("scripts/desenvolvimento/treinar_modelo.py") }
        "9" {
            $pessoa = Pedir-Nome
            if ($pessoa) { Rodar @("scripts/desenvolvimento/teste_controlado.py", "--participante", $pessoa, "--incluir-nada") }
        }
        "simples" { Write-Host "Aperte Q na janela da câmera para voltar."; Rodar @("scripts/demonstracao/executar.py") }
        "v" { Rodar @("scripts/demonstracao/testar_voz.py") }
        "f" { Conferir-Frases }
        "c" { Mostrar-Creditos }
        "0" { exit 0 }
        default { Aviso "Opção inválida." }
    }
    Pausar
}
