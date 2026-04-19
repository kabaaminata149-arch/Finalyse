# build_installer.ps1 — Construit Finalyse_Setup.exe
# Lance : powershell -ExecutionPolicy Bypass -File installer/build_installer.ps1

$ErrorActionPreference = "Stop"
$BASE = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$INST = Join-Path $BASE "installer"
$EMBED = Join-Path $INST "embed"
$OUT   = Join-Path $INST "output"

New-Item -ItemType Directory -Force -Path $EMBED | Out-Null
New-Item -ItemType Directory -Force -Path $OUT   | Out-Null

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Finalyse - Build Package Installation" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# ── 1. Telecharger Python 3.11 portable ───────────────────────────────────
$PY_VER  = "3.11.9"
$PY_URL  = "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-embed-amd64.zip"
$PY_ZIP  = Join-Path $EMBED "python_embed.zip"
$PY_DIR  = Join-Path $EMBED "python"

if (-not (Test-Path (Join-Path $PY_DIR "python.exe"))) {
    Write-Host "[1/6] Telechargement Python $PY_VER portable..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PY_URL -OutFile $PY_ZIP -UseBasicParsing
    Write-Host "[1/6] Extraction..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $PY_DIR | Out-Null
    Expand-Archive -Path $PY_ZIP -DestinationPath $PY_DIR -Force
    # Activer site-packages
    Get-ChildItem $PY_DIR -Filter "*._pth" | ForEach-Object {
        (Get-Content $_.FullName) -replace "#import site","import site" | Set-Content $_.FullName
    }
    Write-Host "[1/6] Python portable OK" -ForegroundColor Green
} else {
    Write-Host "[1/6] Python portable deja present" -ForegroundColor Green
}

$PYTHON = Join-Path $PY_DIR "python.exe"

# ── 2. Installer pip ───────────────────────────────────────────────────────
$PIP = Join-Path $PY_DIR "Scripts\pip.exe"
if (-not (Test-Path $PIP)) {
    Write-Host "[2/6] Installation pip..." -ForegroundColor Yellow
    $GET_PIP = Join-Path $EMBED "get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GET_PIP -UseBasicParsing
    & $PYTHON $GET_PIP --quiet
    Write-Host "[2/6] pip OK" -ForegroundColor Green
} else {
    Write-Host "[2/6] pip deja installe" -ForegroundColor Green
}

# ── 3. Installer les dependances ───────────────────────────────────────────
Write-Host "[3/6] Installation des dependances (5-10 min)..." -ForegroundColor Yellow
$PACKAGES = @(
    "fastapi==0.111.0",
    "uvicorn[standard]==0.30.1",
    "python-multipart==0.0.9",
    "python-jose[cryptography]==3.3.0",
    "passlib[bcrypt]==1.7.4",
    "httpx==0.27.0",
    "pdfplumber==0.11.0",
    "Pillow==10.3.0",
    "pydantic==2.7.1",
    "python-dotenv==1.0.1",
    "reportlab==4.2.0",
    "PyQt6==6.7.0",
    "pytesseract==0.3.13",
    "opencv-python-headless==4.9.0.80",
    "numpy==1.26.4",
    "openpyxl==3.1.2",
    "email-validator==2.1.1",
    "pyinstaller==6.3.0"
)
foreach ($pkg in $PACKAGES) {
    Write-Host "  -> $pkg" -NoNewline
    & $PIP install $pkg --quiet --no-warn-script-location 2>$null
    Write-Host " OK" -ForegroundColor Green
}

# ── 4. Copier le code source ───────────────────────────────────────────────
Write-Host "[4/6] Copie du code source..." -ForegroundColor Yellow
$APP_DIR = Join-Path $EMBED "app"
if (Test-Path $APP_DIR) { Remove-Item $APP_DIR -Recurse -Force }
New-Item -ItemType Directory -Force -Path $APP_DIR | Out-Null

foreach ($folder in @("backend", "frontend")) {
    $src = Join-Path $BASE $folder
    $dst = Join-Path $APP_DIR $folder
    Copy-Item $src $dst -Recurse -Force
}
Copy-Item (Join-Path $BASE "GO.py") (Join-Path $APP_DIR "GO.py") -Force

# Nettoyer __pycache__
Get-ChildItem $APP_DIR -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem $APP_DIR -Recurse -Filter "*.pyc" | Remove-Item -Force
Write-Host "[4/6] Code source copie" -ForegroundColor Green

# ── 5. Compiler Finalyse.exe (launcher) avec PyInstaller ──────────────────
Write-Host "[5/6] Compilation du launcher Finalyse.exe..." -ForegroundColor Yellow
$LAUNCHER = Join-Path $INST "launcher.py"
$PYINST   = Join-Path $PY_DIR "Scripts\pyinstaller.exe"

& $PYINST $LAUNCHER `
    --onefile --windowed --name Finalyse `
    --distpath $OUT --workpath (Join-Path $INST "build_tmp") `
    --noconfirm --clean 2>&1 | Out-Null

if (Test-Path (Join-Path $OUT "Finalyse.exe")) {
    Write-Host "[5/6] Finalyse.exe compile" -ForegroundColor Green
} else {
    Write-Host "[5/6] ERREUR compilation launcher" -ForegroundColor Red
    exit 1
}

# ── 6. Telecharger et installer NSIS, puis creer l'installeur ─────────────
Write-Host "[6/6] Creation de l'installeur..." -ForegroundColor Yellow

$NSIS_EXE = "C:\Program Files (x86)\NSIS\makensis.exe"
if (-not (Test-Path $NSIS_EXE)) {
    $NSIS_EXE = "C:\Program Files\NSIS\makensis.exe"
}

if (-not (Test-Path $NSIS_EXE)) {
    Write-Host "  Telechargement NSIS..." -ForegroundColor Yellow
    $NSIS_URL = "https://downloads.sourceforge.net/project/nsis/NSIS%203/3.10/nsis-3.10-setup.exe"
    $NSIS_SETUP = Join-Path $EMBED "nsis_setup.exe"
    Invoke-WebRequest -Uri $NSIS_URL -OutFile $NSIS_SETUP -UseBasicParsing
    Write-Host "  Installation NSIS silencieuse..." -ForegroundColor Yellow
    Start-Process $NSIS_SETUP -ArgumentList "/S" -Wait
    $NSIS_EXE = "C:\Program Files (x86)\NSIS\makensis.exe"
}

# Generer le script NSIS
$APP_DIR_ESC  = $APP_DIR.Replace("\", "\\")
$PY_DIR_ESC   = $PY_DIR.Replace("\", "\\")
$OUT_EXE      = Join-Path $OUT "Finalyse_Setup.exe"
$LAUNCHER_EXE = Join-Path $OUT "Finalyse.exe"

$NSI = @"
!include "MUI2.nsh"
Name "Finalyse"
OutFile "$OUT_EXE"
InstallDir "`$APPDATA\Finalyse"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_WELCOMEPAGE_TITLE "Installation de Finalyse"
!define MUI_WELCOMEPAGE_TEXT "Finalyse - Analyse Intelligente de Factures`r`n`r`nL'installation va configurer l'application sur votre ordinateur."
!define MUI_FINISHPAGE_RUN "`$INSTDIR\Finalyse.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Finalyse"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Section "Finalyse" SecMain
    SetOutPath "`$INSTDIR"
    DetailPrint "Installation de Finalyse en cours..."

    SetOutPath "`$INSTDIR\python"
    File /r "$PY_DIR_ESC\*.*"

    SetOutPath "`$INSTDIR\app"
    File /r "$APP_DIR_ESC\*.*"

    SetOutPath "`$INSTDIR"
    File "$LAUNCHER_EXE"

    CreateShortcut "`$DESKTOP\Finalyse.lnk" "`$INSTDIR\Finalyse.exe"
    CreateDirectory "`$SMPROGRAMS\Finalyse"
    CreateShortcut "`$SMPROGRAMS\Finalyse\Finalyse.lnk" "`$INSTDIR\Finalyse.exe"
    CreateShortcut "`$SMPROGRAMS\Finalyse\Desinstaller.lnk" "`$INSTDIR\Uninstall.exe"

    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Finalyse" "DisplayName" "Finalyse"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Finalyse" "UninstallString" "`$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Finalyse" "DisplayVersion" "1.0.0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Finalyse" "Publisher" "Finalyse"
    WriteUninstaller "`$INSTDIR\Uninstall.exe"
    DetailPrint "Installation terminee !"
SectionEnd

Section "Uninstall"
    Delete "`$DESKTOP\Finalyse.lnk"
    RMDir /r "`$SMPROGRAMS\Finalyse"
    RMDir /r "`$INSTDIR"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Finalyse"
SectionEnd
"@

$NSI_FILE = Join-Path $INST "finalyse.nsi"
$NSI | Set-Content $NSI_FILE -Encoding UTF8

& $NSIS_EXE $NSI_FILE

if (Test-Path $OUT_EXE) {
    $SIZE = [math]::Round((Get-Item $OUT_EXE).Length / 1MB, 0)
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "  PACKAGE CREE AVEC SUCCES !" -ForegroundColor Green
    Write-Host "  Fichier : installer/output/Finalyse_Setup.exe" -ForegroundColor Green
    Write-Host "  Taille  : $SIZE MB" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "L'utilisateur telecharge Finalyse_Setup.exe," -ForegroundColor Cyan
    Write-Host "double-clique, et Finalyse s'installe automatiquement." -ForegroundColor Cyan
} else {
    Write-Host "[6/6] ERREUR creation installeur" -ForegroundColor Red
}
