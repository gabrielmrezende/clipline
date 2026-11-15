<#
.SYNOPSIS
    Instala o clipline num comando no Windows.

.DESCRIPTION
    Confere o Python (3.12 ou 3.13) e o Node (22.12 ou mais novo), cria o .venv, instala o pacote com os extras
    painel e dev, gera o build do painel, cria as pastas do canal ao lado do repositório se faltarem e roda o doctor.
    Pode rodar de novo: o que já existe fica como está (nada é apagado nem sobrescrito).
    A variável CLIPLINE_PYTHON escolhe o interpretador.

.PARAMETER SemPainel
    Não gera o build do painel (dispensa o Node).

.PARAMETER Canal
    Nome do canal, repassado ao "esteira init" quando ele existir.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
#>
[CmdletBinding()]
param(
    [switch]$SemPainel,
    [string]$Canal
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $PSScriptRoot
$Raiz = Split-Path -Parent $Repo
$PastasDoCanal = @('1 - Programas', '2 - Cortes', '3 - Identidade')

function Passo([string]$Texto) {
    Write-Host ''
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

function Falhar([string]$Texto) {
    Write-Host "Erro: $Texto" -ForegroundColor Red
    exit 1
}

# O Windows PowerShell 5.1 transforma o stderr de um programa em erro quando $ErrorActionPreference é 'Stop'.
# Por isso os programas rodam com 'Continue': o aviso do pip ou do npm só aparece na tela.

# Roda um programa com a saída direto na tela; o código de saída fica em $LASTEXITCODE.
function Rodar {
    param([string]$Programa, [string[]]$Argumentos = @())
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Programa @Argumentos } finally { $ErrorActionPreference = $anterior }
}

function Exigir {
    param([string]$Programa, [string[]]$Argumentos, [string]$Mensagem)
    Rodar $Programa $Argumentos
    if ($LASTEXITCODE -ne 0) { Falhar "$Mensagem (código $LASTEXITCODE)" }
}

# Roda calado e diz só se deu certo.
function Funciona {
    param([string]$Programa, [string[]]$Argumentos = @())
    if (-not (Get-Command $Programa -ErrorAction SilentlyContinue)) { return $false }
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Programa @Argumentos *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $anterior
    }
}

$VersaoAceita = 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 12), (3, 13)) else 1)'

function Aceita([string]$Programa, [string[]]$Antes = @()) {
    return Funciona $Programa ($Antes + @('-c', $VersaoAceita))
}

function Achar-Python {
    if ($env:CLIPLINE_PYTHON) {
        if (Aceita $env:CLIPLINE_PYTHON) { return , @($env:CLIPLINE_PYTHON) }
        Falhar "CLIPLINE_PYTHON=$($env:CLIPLINE_PYTHON) não é Python 3.12 nem 3.13."
    }
    foreach ($versao in @('3.12', '3.13')) {
        if (Aceita 'py' @("-$versao")) { return , @('py', "-$versao") }
    }
    if (Aceita 'python') { return , @('python') }
    Falhar 'Python 3.12 ou 3.13 não encontrado. Instale pelo python.org (marque "Add python.exe to PATH") e rode de novo.'
}

function Conferir-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Falhar 'Node.js não encontrado. Instale o Node 22.12 ou mais novo (nodejs.org) ou rode com -SemPainel.'
    }
    $versao = (& node --version).TrimStart('v')
    $partes = $versao.Split('.')
    $maior = [int]$partes[0]
    $menor = [int]$partes[1]
    if (-not ($maior -gt 22 -or ($maior -eq 22 -and $menor -ge 12))) {
        Falhar "Node $versao é antigo para o build do painel. Instale o 22.12 ou mais novo, ou rode com -SemPainel."
    }
    return $versao
}

function Pasta-Vazia([string]$Pasta) {
    return -not (Get-ChildItem -LiteralPath $Pasta -Force | Select-Object -First 1)
}

function Layout-Completo {
    foreach ($pasta in $PastasDoCanal + @('Contexto')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Raiz $pasta) -PathType Container)) { return $false }
    }
    return -not (Pasta-Vazia (Join-Path $Raiz 'Contexto'))
}

function Criar-Layout {
    foreach ($pasta in $PastasDoCanal) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Raiz $pasta) | Out-Null
    }
    # Regras de exemplo só onde ainda não há regra nenhuma: um Contexto\ do canal nunca recebe arquivo de exemplo.
    $contexto = Join-Path $Raiz 'Contexto'
    if (-not (Test-Path -LiteralPath $contexto) -or (Pasta-Vazia $contexto)) {
        New-Item -ItemType Directory -Force -Path $contexto | Out-Null
        Copy-Item -Path (Join-Path $Repo 'Contexto.exemplo\*') -Destination $contexto -Recurse
        Write-Host 'Contexto\ criado com as regras de exemplo; reescreva com as do seu canal.'
    }
}

Passo 'Python'
$Python = Achar-Python
$PythonExe = $Python[0]
$PythonArgs = @($Python | Select-Object -Skip 1)
Write-Host "$(& $PythonExe @PythonArgs --version) ($($Python -join ' '))"

if (-not $SemPainel) {
    Passo 'Node'
    $versaoNode = Conferir-Node
    Write-Host "Node $versaoNode, npm $(& npm --version)"
}

Passo 'Ambiente virtual (.venv)'
$Venv = Join-Path $Repo '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
if (Test-Path -LiteralPath $VenvPy) {
    if (-not (Aceita $VenvPy)) {
        Falhar "o .venv existente usa $(& $VenvPy --version), e o projeto pede 3.12 ou 3.13. Apague $Venv e rode de novo."
    }
    Write-Host "já existe ($(& $VenvPy --version)); só atualizo os pacotes"
} else {
    if (Test-Path -LiteralPath $Venv) { Falhar "$Venv existe mas não tem Python. Apague essa pasta e rode de novo." }
    Exigir $PythonExe ($PythonArgs + @('-m', 'venv', $Venv)) 'não consegui criar o .venv'
    Write-Host "criado em $Venv"
}

Passo 'Pacote clipline com os extras painel e dev'
Push-Location $Repo
try {
    Exigir $VenvPy @('-m', 'pip', 'install', '--upgrade', 'pip') 'falhou a atualização do pip'
    Exigir $VenvPy @('-m', 'pip', 'install', '-e', '.[painel,dev]') 'falhou a instalação do pacote'
} finally {
    Pop-Location
}

if (-not $SemPainel) {
    Passo 'Build do painel (painel-web\)'
    Push-Location (Join-Path $Repo 'painel-web')
    try {
        Exigir 'npm' @('ci', '--no-audit', '--no-fund') 'falhou o npm ci'
        Exigir 'npm' @('run', 'build') 'falhou o build do painel'
    } finally {
        Pop-Location
    }
} else {
    Passo 'Build do painel: pulado (-SemPainel)'
}

Passo "Pastas do canal em $Raiz"
# Dentro do repositório: "python -m esteira" pega primeiro a pasta esteira\ do diretório atual.
Push-Location $Repo
try {
    if (Layout-Completo) {
        Write-Host 'já existem; nada mudou'
    } elseif (Funciona $VenvPy @('-m', 'esteira', 'init', '--help')) {
        $argumentos = @('-m', 'esteira', 'init', $Raiz, '--sem-perguntas')
        if ($Canal) { $argumentos += @('--canal', $Canal) }
        Exigir $VenvPy $argumentos 'falhou o esteira init'
    } else {
        Criar-Layout
        Write-Host '1 - Programas\, 2 - Cortes\, 3 - Identidade\ e Contexto\ prontos'
    }
} finally {
    Pop-Location
}

Passo 'Diagnóstico (esteira doctor)'
Push-Location $Repo
try {
    Rodar $VenvPy @('-m', 'esteira', 'doctor')
    $codigoDoctor = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Host ''
if ($codigoDoctor -eq 0) {
    Write-Host 'Tudo pronto.' -ForegroundColor Green
} else {
    Write-Host 'Instalação feita. O doctor apontou o que ainda falta (linhas FALTA acima): modelos de rosto em modelos\' -ForegroundColor Yellow
    Write-Host '(veja modelos\LEIA.md), ffmpeg em bin\ ou no PATH, ou encerramentos em 3 - Identidade\.' -ForegroundColor Yellow
}
Write-Host "Para abrir o painel: $VenvPy -m esteira painel"
