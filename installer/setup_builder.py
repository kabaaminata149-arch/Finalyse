"""
installer/setup_builder.py
Construit Finalyse_Setup.exe — installeur Windows complet.
Lance : python installer/setup_builder.py
"""
import os, sys, shutil, subprocess, urllib.request, zipfile, time

BASE      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INST_DIR  = os.path.join(BASE, "installer")
OUT_DIR   = os.path.join(INST_DIR, "output")
EMBED_DIR = os.path.join(INST_DIR, "embed")
PY_VERSION = "3.11.9"
PY_DIR     = os.path.join(EMBED_DIR, "python")
APP_DIR    = os.path.join(EMBED_DIR, "app")

os.makedirs(OUT_DIR,   exist_ok=True)
os.makedirs(EMBED_DIR, exist_ok=True)


def _download(url, dest, label=""):
    """Télécharge avec retry et affichage progression."""
    for attempt in range(3):
        try:
            def hook(b, bs, t):
                if t > 0:
                    pct = min(int(b * bs / t * 100), 100)
                    print(f"\r  {label} {pct}%   ", end="", flush=True)
            urllib.request.urlretrieve(url, dest, reporthook=hook)
            print()
            return True
        except Exception as e:
            print(f"\n  Tentative {attempt+1}/3 échouée : {e}")
            time.sleep(2)
    return False


# ── 1. Python portable ────────────────────────────────────────────────────

def download_python_embed():
    if os.path.exists(os.path.join(PY_DIR, "python.exe")):
        print("[1] Python portable déjà présent.")
        return
    url  = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
    dest = os.path.join(EMBED_DIR, "python_embed.zip")
    print(f"[1] Téléchargement Python {PY_VERSION} portable...")
    if not _download(url, dest, "Python"):
        print("[1] ERREUR téléchargement Python. Vérifiez votre connexion.")
        sys.exit(1)
    print("[1] Extraction...")
    os.makedirs(PY_DIR, exist_ok=True)
    with zipfile.ZipFile(dest, "r") as z:
        z.extractall(PY_DIR)
    # Activer site-packages
    for f in os.listdir(PY_DIR):
        if f.endswith("._pth"):
            path = os.path.join(PY_DIR, f)
            txt  = open(path, encoding="utf-8").read()
            if "#import site" in txt:
                open(path, "w", encoding="utf-8").write(txt.replace("#import site", "import site"))
    print("[1] Python portable OK")


# ── 2. pip ────────────────────────────────────────────────────────────────

def install_pip():
    pip = os.path.join(PY_DIR, "Scripts", "pip.exe")
    if os.path.exists(pip):
        print("[2] pip déjà installé.")
        return
    print("[2] Installation de pip...")
    dest = os.path.join(EMBED_DIR, "get-pip.py")
    _download("https://bootstrap.pypa.io/get-pip.py", dest, "pip")
    subprocess.run([os.path.join(PY_DIR, "python.exe"), dest, "--quiet"], check=True)
    print("[2] pip OK")


# ── 3. Dépendances — sans versions fixées pour éviter les conflits ────────

REQUIREMENTS = [
    # Backend
    "fastapi",
    "uvicorn[standard]",
    "python-multipart",
    "python-jose[cryptography]",
    "passlib[bcrypt]",
    "pydantic",
    "python-dotenv",
    "email-validator",
    # PDF & OCR
    "pdfplumber",
    "Pillow",
    "pytesseract",
    "opencv-python-headless",
    "numpy",
    "pdf2image",
    # Export
    "reportlab",
    "openpyxl",
    # Frontend
    "PyQt6",
    # Cloud
    "pymongo[srv]",
    # HTTP
    "httpx",
]


def install_deps():
    pip = os.path.join(PY_DIR, "Scripts", "pip.exe")
    print("[3] Installation des dépendances...")
    # Mettre à jour pip d'abord
    subprocess.run([pip, "install", "--upgrade", "pip", "--quiet"], check=False)
    failed = []
    for pkg in REQUIREMENTS:
        print(f"  → {pkg}", end=" ", flush=True)
        r = subprocess.run(
            [pip, "install", pkg, "--quiet", "--no-warn-script-location",
             "--retries", "5", "--timeout", "60"],
            capture_output=True
        )
        if r.returncode == 0:
            print("✓")
        else:
            print("✗ (ignoré)")
            failed.append(pkg)
    if failed:
        print(f"[3] Packages non installés (connexion instable) : {failed}")
        print("    Relancez le script pour réessayer.")
    else:
        print("[3] Toutes les dépendances installées.")


# ── 4. Code source ────────────────────────────────────────────────────────

def copy_app():
    print("[4] Copie du code source...")
    if os.path.exists(APP_DIR):
        # Forcer la suppression même si OneDrive verrouille
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", APP_DIR],
                       capture_output=True)
        if os.path.exists(APP_DIR):
            # Fallback : changer les permissions puis supprimer
            for root, dirs, files in os.walk(APP_DIR):
                for f in files:
                    try:
                        fp = os.path.join(root, f)
                        os.chmod(fp, 0o777)
                    except Exception:
                        pass
            shutil.rmtree(APP_DIR, ignore_errors=True)

    os.makedirs(APP_DIR)
    for folder in ["backend", "frontend"]:
        shutil.copytree(
            os.path.join(BASE, folder),
            os.path.join(APP_DIR, folder),
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "*.db-shm", "*.db-wal",
                "uploads", "exports", ".git", "build", "dist"
            )
        )
    shutil.copy2(os.path.join(BASE, "GO.py"), os.path.join(APP_DIR, "GO.py"))
    print("[4] Code source copié.")


# ── 5. Compiler Finalyse.exe avec PyInstaller ─────────────────────────────

def build_launcher():
    print("[5] Compilation du launcher Finalyse.exe...")
    launcher_src = os.path.join(INST_DIR, "launcher.py")

    # Écrire le launcher
    with open(launcher_src, "w", encoding="utf-8") as f:
        f.write(
            'import os, sys, subprocess\n'
            'def main():\n'
            '    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))\n'
            '    install_dir = os.path.join(appdata, "Finalyse")\n'
            '    python_exe  = os.path.join(install_dir, "python", "python.exe")\n'
            '    go_py       = os.path.join(install_dir, "app", "GO.py")\n'
            '    if not os.path.exists(python_exe) or not os.path.exists(go_py):\n'
            '        import ctypes\n'
            '        ctypes.windll.user32.MessageBoxW(0,\n'
            '            "Installation corrompue.\\nReinstallez Finalyse.",\n'
            '            "Finalyse", 0x10)\n'
            '        return\n'
            '    subprocess.Popen([python_exe, go_py],\n'
            '        cwd=os.path.dirname(go_py),\n'
            '        creationflags=subprocess.CREATE_NO_WINDOW)\n'
            'if __name__ == "__main__":\n'
            '    main()\n'
        )

    # Utiliser PyInstaller du système (pas du Python portable)
    pyinst = shutil.which("pyinstaller")
    if not pyinst:
        # Essayer dans Scripts Python courant
        pyinst = os.path.join(os.path.dirname(sys.executable), "Scripts", "pyinstaller.exe")

    if not pyinst or not os.path.exists(pyinst):
        print("[5] PyInstaller non trouvé — installation...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "--quiet"])
        pyinst = os.path.join(os.path.dirname(sys.executable), "Scripts", "pyinstaller.exe")

    icon_path = os.path.join(BASE, "frontend", "assets", "logo.ico")
    cmd = [
        pyinst, launcher_src,
        "--onefile", "--windowed",
        "--name", "Finalyse",
        "--distpath", OUT_DIR,
        "--workpath", os.path.join(INST_DIR, "build_tmp"),
        "--noconfirm", "--clean",
    ]
    if os.path.exists(icon_path):
        cmd += ["--icon", icon_path]

    result = subprocess.run(cmd, capture_output=True, text=True)
    launcher_exe = os.path.join(OUT_DIR, "Finalyse.exe")
    if os.path.exists(launcher_exe):
        print("[5] Finalyse.exe compilé.")
        return launcher_exe
    else:
        print("[5] ERREUR compilation launcher:")
        print(result.stdout[-500:] if result.stdout else "")
        print(result.stderr[-500:] if result.stderr else "")
        sys.exit(1)


# ── 6. Script NSIS ────────────────────────────────────────────────────────

def generate_nsis(launcher_exe):
    nsis_script  = os.path.join(INST_DIR, "finalyse_setup.nsi")
    app_nsis     = APP_DIR.replace("/", "\\")
    py_nsis      = PY_DIR.replace("/", "\\")
    out_exe      = os.path.join(OUT_DIR, "Finalyse_Setup.exe").replace("/", "\\")
    launcher_win = launcher_exe.replace("/", "\\")

    lines = [
        '!include "MUI2.nsh"',
        'Name "Finalyse"',
        'OutFile "' + out_exe + '"',
        'InstallDir "$APPDATA\\Finalyse"',
        'RequestExecutionLevel user',
        'SetCompressor /SOLID lzma',
        '',
        '!define MUI_ABORTWARNING',
        '!define MUI_WELCOMEPAGE_TITLE "Installation de Finalyse"',
        '!define MUI_WELCOMEPAGE_TEXT "Finalyse - Analyse Intelligente de Factures$\\n$\\nCliquez sur Suivant pour installer."',
        '!define MUI_FINISHPAGE_RUN "$INSTDIR\\Finalyse.exe"',
        '!define MUI_FINISHPAGE_RUN_TEXT "Lancer Finalyse"',
        '',
        '!insertmacro MUI_PAGE_WELCOME',
        '!insertmacro MUI_PAGE_INSTFILES',
        '!insertmacro MUI_PAGE_FINISH',
        '!insertmacro MUI_UNPAGE_CONFIRM',
        '!insertmacro MUI_UNPAGE_INSTFILES',
        '!insertmacro MUI_LANGUAGE "French"',
        '',
        'Section "Finalyse" SecMain',
        '    SetOutPath "$INSTDIR\\python"',
        '    File /r "' + py_nsis + '\\*.*"',
        '    SetOutPath "$INSTDIR\\app"',
        '    File /r "' + app_nsis + '\\*.*"',
        '    SetOutPath "$INSTDIR"',
        '    File "' + launcher_win + '"',
        '    CreateShortcut "$DESKTOP\\Finalyse.lnk" "$INSTDIR\\Finalyse.exe"',
        '    CreateDirectory "$SMPROGRAMS\\Finalyse"',
        '    CreateShortcut "$SMPROGRAMS\\Finalyse\\Finalyse.lnk" "$INSTDIR\\Finalyse.exe"',
        '    CreateShortcut "$SMPROGRAMS\\Finalyse\\Desinstaller.lnk" "$INSTDIR\\Uninstall.exe"',
        '    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Finalyse" "DisplayName" "Finalyse"',
        '    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Finalyse" "UninstallString" "$INSTDIR\\Uninstall.exe"',
        '    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Finalyse" "DisplayVersion" "1.0.0"',
        '    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Finalyse" "Publisher" "Finalyse"',
        '    WriteUninstaller "$INSTDIR\\Uninstall.exe"',
        'SectionEnd',
        '',
        'Section "Uninstall"',
        '    Delete "$DESKTOP\\Finalyse.lnk"',
        '    RMDir /r "$SMPROGRAMS\\Finalyse"',
        '    RMDir /r "$INSTDIR"',
        '    DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Finalyse"',
        'SectionEnd',
    ]

    with open(nsis_script, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[6] Script NSIS généré.")
    return nsis_script


# ── 7. Compiler NSIS ──────────────────────────────────────────────────────

def compile_nsis(nsis_script):
    for path in [r"C:\Program Files (x86)\NSIS\makensis.exe",
                 r"C:\Program Files\NSIS\makensis.exe"]:
        if os.path.exists(path):
            print("[7] Compilation installeur NSIS...")
            r = subprocess.run([path, nsis_script])
            return r.returncode == 0
    print("[7] NSIS non trouvé. Téléchargez : https://nsis.sourceforge.io/Download")
    return False


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Finalyse — Build Package d'Installation")
    print("=" * 55)

    download_python_embed()
    install_pip()
    install_deps()
    copy_app()
    launcher_exe = build_launcher()
    nsis_script  = generate_nsis(launcher_exe)

    if compile_nsis(nsis_script):
        out  = os.path.join(OUT_DIR, "Finalyse_Setup.exe")
        size = os.path.getsize(out) / 1024 / 1024
        print()
        print("=" * 55)
        print("  SUCCES ! Fichier créé :")
        print(f"  {out}")
        print(f"  Taille : {size:.0f} MB")
        print("=" * 55)
        print()
        print("Distribuez ce fichier — l'utilisateur double-clique")
        print("et Finalyse s'installe automatiquement.")
    else:
        print()
        print("Build partiel — vérifiez les erreurs ci-dessus.")
