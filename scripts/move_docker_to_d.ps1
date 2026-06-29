# Move Docker Desktop WSL data from C: to D: via directory junction.
# Frees ~38 GB on C: while keeping Docker paths unchanged.
#
# BEFORE RUNNING:
#   1. Quit Docker Desktop (system tray → Quit)
#   2. Run PowerShell as Administrator
#
# Usage: .\scripts\move_docker_to_d.ps1

$ErrorActionPreference = "Stop"

$source = Join-Path $env:LOCALAPPDATA "Docker\wsl"
$target = "D:\Docker\wsl"

Write-Host "Docker WSL migration: C: -> D:" -ForegroundColor Cyan
Write-Host "  Source: $source"
Write-Host "  Target: $target"
Write-Host ""

if (-not (Test-Path "D:\")) {
    Write-Error "D: drive not found."
}

$vhdx = Join-Path $source "disk\docker_data.vhdx"
if (-not (Test-Path $vhdx)) {
    Write-Error "Docker data not found at $vhdx. Is Docker Desktop installed?"
}

$sizeGb = [math]::Round((Get-Item $vhdx).Length / 1GB, 1)
Write-Host "Docker disk image: ~${sizeGb} GB" -ForegroundColor Yellow

$dockerProcs = Get-Process -Name "Docker Desktop", "com.docker.backend", "com.docker.service" -ErrorAction SilentlyContinue
if ($dockerProcs) {
    Write-Host "Stop Docker Desktop first (still running)." -ForegroundColor Red
    exit 1
}

Write-Host "Shutting down WSL..."
wsl --shutdown
Start-Sleep -Seconds 3

if (Test-Path $target) {
    Write-Error "Target already exists: $target. Remove or pick another path."
}

New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null

Write-Host "Moving data to D: (this may take several minutes)..."
Move-Item -LiteralPath $source -Destination $target

Write-Host "Creating junction so Docker still finds data at the original path..."
cmd /c "mklink /J `"$source`" `"$target`""

Write-Host ""
Write-Host "Done. Restart Docker Desktop." -ForegroundColor Green
Write-Host "Data is physically on D:; Docker uses the junction on C:."
Write-Host ""
Write-Host "Alternative (GUI): Docker Desktop -> Settings -> Resources -> Advanced"
Write-Host "  Disk image location -> D:\Docker\wsl"
