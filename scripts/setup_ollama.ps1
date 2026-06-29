# Setup Ollama for local dev (Windows host).
# Stores models on D: to save C: drive space.
# Run: .\scripts\setup_ollama.ps1

$ErrorActionPreference = "Stop"

$ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$model = "qwen3:14b"
$modelsDir = "D:\boolmind-ai\ollama-models"
$defaultModelsDir = Join-Path $env:USERPROFILE ".ollama\models"

Write-Host "Boolmind AI — Ollama dev setup" -ForegroundColor Cyan

if (-not (Test-Path "D:\")) {
    Write-Host "D: drive not found. Edit `$modelsDir in this script or set OLLAMA_MODELS manually." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ollamaExe)) {
    Write-Host "Ollama not found at $ollamaExe" -ForegroundColor Red
    Write-Host "Install from https://ollama.com then re-run this script."
    exit 1
}

New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelsDir, "User")
$env:OLLAMA_MODELS = $modelsDir

Write-Host "Ollama models directory: $modelsDir" -ForegroundColor Green
Write-Host "OLLAMA_MODELS set as a persistent user environment variable." -ForegroundColor Green

# Ollama only reads OLLAMA_MODELS at startup — restart the app so pulls go to D:
$ollamaProcs = Get-Process -Name "ollama", "Ollama" -ErrorAction SilentlyContinue
if ($ollamaProcs) {
    Write-Host "Restarting Ollama so it uses D: for model storage..." -ForegroundColor Yellow
    $ollamaProcs | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Start-Process $ollamaExe
Start-Sleep -Seconds 4

Write-Host "Ollama version: $(& $ollamaExe --version)"

try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 15 | Out-Null
    Write-Host "Ollama API is running on http://localhost:11434" -ForegroundColor Green
} catch {
    Write-Host "Ollama API not reachable. Quit Ollama from the system tray, reopen it, then re-run this script." -ForegroundColor Red
    exit 1
}

$existing = & $ollamaExe list 2>&1 | Select-String $model
if ($existing) {
    Write-Host "Model $model already present." -ForegroundColor Green
} else {
    Write-Host "Pulling $model (~9 GB) to $modelsDir ..." -ForegroundColor Yellow
    & $ollamaExe pull $model
}

if (Test-Path $defaultModelsDir) {
    $cSize = (Get-ChildItem $defaultModelsDir -Recurse -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    if ($cSize -gt 1GB) {
        Write-Host ""
        Write-Host "Old models may still be on C: at $defaultModelsDir" -ForegroundColor Yellow
        Write-Host "  (~$([math]::Round($cSize / 1GB, 1)) GB). Safe to delete after confirming $model works:"
        Write-Host "  Remove-Item -Recurse -Force `"$defaultModelsDir`""
    }
}

Write-Host ""
Write-Host "Done. For Docker dev:" -ForegroundColor Green
Write-Host "  cp .env.docker.example .env"
Write-Host "  docker compose up -d --build"
Write-Host "  open http://localhost:8000/advisor"
