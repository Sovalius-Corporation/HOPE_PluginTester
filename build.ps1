# Build HOPEPluginTester.exe
# Run from the hope_plugin_tester directory:
#   .\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "`n==> Checking PyInstaller..." -ForegroundColor Cyan
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "    Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}

Write-Host "`n==> Cleaning previous build..." -ForegroundColor Cyan
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist"  }

Write-Host "`n==> Running PyInstaller..." -ForegroundColor Cyan
pyinstaller hope_plugin_tester.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[FAILED] PyInstaller exited with code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

$exePath = Join-Path $root "dist\HOPEPluginTester\HOPEPluginTester.exe"
if (Test-Path $exePath) {
    $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "`n[OK] Built: $exePath  ($size MB)" -ForegroundColor Green
    Write-Host "     Folder: dist\HOPEPluginTester\" -ForegroundColor Green
} else {
    Write-Host "`n[FAILED] exe not found at expected path." -ForegroundColor Red
    exit 1
}
