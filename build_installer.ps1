param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$DistExe    = Join-Path $ProjectDir "dist\HOPEPluginTester\HOPEPluginTester.exe"
$IssFile    = Join-Path $ProjectDir "installer.iss"
$OutDir     = Join-Path $ProjectDir "dist\installer"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    OK: $msg" -ForegroundColor Green }
function Fail       { param($msg) Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# -- Step 1: Build exe with PyInstaller (unless -SkipBuild) ------------------
if (-not $SkipBuild) {
    Write-Step "Building exe with PyInstaller..."
    Push-Location $ProjectDir
    try {
        py -m PyInstaller hope_plugin_tester.spec --noconfirm
        if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
}

if (-not (Test-Path $DistExe)) {
    Fail "Exe not found: $DistExe`nRun without -SkipBuild or fix the spec."
}
Write-Ok "Exe found: $DistExe"

# -- Step 2: Locate or install Inno Setup 6 ----------------------------------
Write-Step "Locating Inno Setup 6..."

$IsccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$IsccPath = $null
foreach ($c in $IsccCandidates) { if (Test-Path $c) { $IsccPath = $c; break } }

if (-not $IsccPath) {
    Write-Host "    Inno Setup 6 not found - fetching latest version from GitHub..." -ForegroundColor Yellow

    $releaseInfo  = Invoke-RestMethod "https://api.github.com/repos/jrsoftware/issrc/releases/latest"
    $asset        = $releaseInfo.assets | Where-Object { $_.name -like "innosetup*.exe" } | Select-Object -First 1
    if (-not $asset) { Fail "Could not find Inno Setup asset in GitHub release." }

    $InnoUrl       = $asset.browser_download_url
    $InnoInstaller = Join-Path $env:TEMP $asset.name

    Write-Host "    Downloading $($asset.name) ..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $InnoUrl -OutFile $InnoInstaller -UseBasicParsing
    Write-Host "    Installing silently..." -ForegroundColor Yellow

    Start-Process -FilePath $InnoInstaller -ArgumentList "/VERYSILENT", "/NORESTART" -Wait -NoNewWindow

    foreach ($c in $IsccCandidates) { if (Test-Path $c) { $IsccPath = $c; break } }
    if (-not $IsccPath) { Fail "Inno Setup install failed or unexpected path." }
}

Write-Ok "ISCC: $IsccPath"

# -- Step 3: Compile installer -----------------------------------------------
Write-Step "Compiling installer.iss..."

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

Push-Location $ProjectDir
try {
    & $IsccPath $IssFile
    if ($LASTEXITCODE -ne 0) { Fail "ISCC.exe failed (exit $LASTEXITCODE)." }
} finally { Pop-Location }

# -- Done --------------------------------------------------------------------
$SetupExe = Get-ChildItem $OutDir -Filter "HOPEPluginTester_Setup_*.exe" |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($SetupExe) {
    $SizeMB = [math]::Round($SetupExe.Length / 1MB, 1)
    Write-Host "`n+------------------------------------------+" -ForegroundColor Green
    Write-Host "| Installer ready!                         |" -ForegroundColor Green
    Write-Host "|   $($SetupExe.FullName)" -ForegroundColor Green
    Write-Host "|   Size: $SizeMB MB                       |" -ForegroundColor Green
    Write-Host "+------------------------------------------+`n" -ForegroundColor Green
} else {
    Fail "Could not find output installer in $OutDir"
}