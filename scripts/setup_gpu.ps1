# Install CUDA-enabled PyTorch and create D: drive ML cache directories.
# Run from repo root: .\scripts\setup_gpu.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$VenvPip = Join-Path $Root ".venv\Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "No .venv found. Run: uv sync  (or python -m venv .venv && pip install -r requirements.txt)"
}

$CacheRoot = "D:\boolmind-ai\ml-cache"
$FidpOut = "D:\boolmind-ai\fidp-output"
foreach ($dir in @($CacheRoot, "$CacheRoot\hub", "$FidpOut")) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
Write-Host "Created cache dirs under D:\boolmind-ai\"

Write-Host "Uninstalling CPU-only torch (if present)..."
cmd /c "`"$VenvPip`" uninstall -y torch torchvision torchaudio >nul 2>&1"

Write-Host "Installing PyTorch with CUDA 12.4 wheels..."
& $VenvPip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Verifying GPU..."
& $VenvPython (Join-Path $Root "scripts\verify_gpu.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Add to your .env (if not already present):"
Write-Host "  HF_HOME=D:\boolmind-ai\ml-cache"
Write-Host "  FIDP_OUTPUT_DIR=D:\boolmind-ai\fidp-output"
Write-Host ""
Write-Host "Restart uvicorn after updating .env so downloads use D:."
