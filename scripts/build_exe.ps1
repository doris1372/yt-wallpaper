# Build ytwall.exe on Windows.
# Run from repo root: powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"

# Move to repo root regardless of where the script is invoked from
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

if (-not (Test-Path ".venv")) {
    Write-Host "==> Creating virtualenv (.venv)" -ForegroundColor Cyan
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

Write-Host "==> Installing dependencies" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

# Download libmpv if missing (the lightweight Windows build from sourceforge mirror)
$mpvDll = Join-Path $RepoRoot "mpv-2.dll"
if (-not (Test-Path $mpvDll)) {
    Write-Host "==> mpv-2.dll not found in repo root." -ForegroundColor Yellow
    Write-Host "    Download a Windows libmpv build from https://sourceforge.net/projects/mpv-player-windows/files/libmpv/" -ForegroundColor Yellow
    Write-Host "    Extract mpv-2.dll into the repo root, then re-run this script." -ForegroundColor Yellow
    Write-Host "    The build will continue but the wallpaper engine will not work without it."
}

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
pyinstaller ytwall.spec --clean --noconfirm

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host "Output: dist\ytwall\ytwall.exe" -ForegroundColor Green
