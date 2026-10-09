<#
    Gera o executavel LEVE do Tradutor de Webtoon.

    Cria uma venv separada (.venv-build) so com a casca do app -- sem Paddle,
    sem CUDA -- para o .exe sair pequeno e o build nao ter como arrastar a
    stack pesada. Nao mexe na sua venv de desenvolvimento (.venv do uv).

    Uso, num PowerShell na raiz do projeto:

        .\build.ps1

    Resultado:  dist\Tradutor de Webtoon.exe   (um arquivo, e so dar dois cliques)

    Pre-requisito: Python 3.12 no PATH (o mesmo que o projeto ja usa). Se so
    tiver o Python do uv, rode antes:  uv python install 3.12
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$venv = Join-Path $root ".venv-build"
$py   = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "==> Criando venv de build em .venv-build" -ForegroundColor Cyan
    python -m venv $venv
}

Write-Host "==> Instalando dependencias leves + PyInstaller" -ForegroundColor Cyan
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r (Join-Path $root "requirements-app.txt")

# Garante o icone (gera se ainda nao existir).
if (-not (Test-Path (Join-Path $root "assets\app.ico"))) {
    Write-Host "==> Gerando icone" -ForegroundColor Cyan
    & $py (Join-Path $root "tools\make_icon.py")
}

Write-Host "==> Empacotando com PyInstaller" -ForegroundColor Cyan
& $py -m PyInstaller --clean --noconfirm (Join-Path $root "webtoon.spec")

$exe = Join-Path $root "dist\Tradutor de Webtoon.exe"
if (Test-Path $exe) {
    $size = "{0:N0} MB" -f ((Get-Item $exe).Length / 1MB)
    Write-Host ""
    Write-Host "OK  ->  $exe  ($size)" -ForegroundColor Green
    Write-Host "Duplo clique abre a janela e o icone aparece na bandeja." -ForegroundColor Green
} else {
    Write-Host "Build terminou mas nao achei o .exe em dist\. Veja o log acima." -ForegroundColor Yellow
}
