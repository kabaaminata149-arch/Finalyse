"""pages/setup_wizard.py — Assistant de configuration au premier lancement
S'affiche si Ollama ou Tesseract ne sont pas installés.
"""
import os
import sys
import subprocess
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QProgressBar, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor
from theme import C, PrimaryButton, SecondaryButton, shadow, Divider


# ── Vérifications ─────────────────────────────────────────────────────────

def _tesseract_ok() -> bool:
    import shutil
    if shutil.which("tesseract"):
        return True
    paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    appdata = os.path.expandvars("%LOCALAPPDATA%")
    if appdata:
        parent = os.path.dirname(appdata)
        try:
            for u in os.listdir(parent):
                paths.append(os.path.join(parent, u, "AppData", "Local",
                                          "Programs", "Tesseract-OCR", "tesseract.exe"))
        except Exception:
            pass
    return any(os.path.isfile(p) for p in paths)


def _ollama_ok() -> bool:
    import shutil, urllib.request
    if not shutil.which("ollama"):
        return False
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def needs_setup() -> bool:
    return not _tesseract_ok() or not _ollama_ok()


# ── Worker installation ────────────────────────────────────────────────────

class _InstallWorker(QThread):
    progress = pyqtSignal(str, int)   # message, %
    done     = pyqtSignal(bool, str)  # ok, message

    def __init__(self, task: str):
        super().__init__()
        self._task = task

    def run(self):
        try:
            if self._task == "tesseract":
                self._install_tesseract()
            elif self._task == "ollama":
                self._install_ollama()
        except Exception as e:
            self.done.emit(False, str(e))

    def _install_tesseract(self):
        import urllib.request, tempfile
        url = ("https://github.com/UB-Mannheim/tesseract/releases/download/"
               "v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe")
        self.progress.emit("Téléchargement de Tesseract OCR...", 10)
        tmp = os.path.join(tempfile.gettempdir(), "tesseract_setup.exe")

        def _hook(b, bs, t):
            if t > 0:
                pct = min(int(b * bs / t * 70), 70)
                self.progress.emit(f"Téléchargement... {pct}%", 10 + pct)

        urllib.request.urlretrieve(url, tmp, reporthook=_hook)
        self.progress.emit("Installation de Tesseract...", 85)
        result = subprocess.run(
            [tmp, "/S"],  # installation silencieuse
            capture_output=True, timeout=120
        )
        if result.returncode == 0:
            self.progress.emit("Tesseract installé ✓", 100)
            self.done.emit(True, "Tesseract OCR installé avec succès.")
        else:
            self.done.emit(False, "Erreur installation Tesseract.")

    def _install_ollama(self):
        import urllib.request, tempfile
        url = "https://ollama.com/download/OllamaSetup.exe"
        self.progress.emit("Téléchargement d'Ollama...", 10)
        tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")

        def _hook(b, bs, t):
            if t > 0:
                pct = min(int(b * bs / t * 70), 70)
                self.progress.emit(f"Téléchargement... {pct}%", 10 + pct)

        urllib.request.urlretrieve(url, tmp, reporthook=_hook)
        self.progress.emit("Installation d'Ollama...", 85)
        result = subprocess.run([tmp, "/S"], capture_output=True, timeout=180)
        if result.returncode == 0:
            self.progress.emit("Ollama installé ✓", 100)
            self.done.emit(True, "Ollama installé. Redémarrez l'application.")
        else:
            self.done.emit(False, "Erreur installation Ollama.")


# ── Dialog principal ───────────────────────────────────────────────────────

class SetupWizard(QDialog):
    """Dialog de configuration affiché au premier lancement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration de Finalyse")
        self.setMinimumSize(580, 520)
        self.resize(580, 520)
        self.setStyleSheet(f"background:{C['surface']};")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._workers = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(20)

        # Titre
        title = QLabel("Configuration initiale")
        title.setStyleSheet(f"font-size:20px;font-weight:800;color:{C['primary']};background:transparent;")
        lay.addWidget(title)

        sub = QLabel("Installez les composants nécessaires au bon fonctionnement de Finalyse.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size:13px;color:{C['on_surf_var']};background:transparent;")
        lay.addWidget(sub)

        lay.addWidget(Divider())

        # ── Tesseract ─────────────────────────────────────────────────────
        self._tess_card = self._make_component_card(
            "Tesseract OCR",
            "Moteur de reconnaissance de texte — nécessaire pour lire les factures scannées (images/PDF scannés).",
            "Requis",
            _tesseract_ok(),
            "tesseract"
        )
        lay.addWidget(self._tess_card["frame"])

        # ── Ollama ────────────────────────────────────────────────────────
        self._ollama_card = self._make_component_card(
            "Ollama (IA locale)",
            "Moteur d'IA local — améliore l'extraction des données. Optionnel si vous avez une connexion internet (DeepSeek API).",
            "Optionnel",
            _ollama_ok(),
            "ollama"
        )
        lay.addWidget(self._ollama_card["frame"])

        lay.addStretch()
        lay.addWidget(Divider())

        # Boutons
        btns = QHBoxLayout()
        self._skip_btn = SecondaryButton("Ignorer pour l'instant")
        self._skip_btn.setFixedHeight(42)
        self._skip_btn.clicked.connect(self.accept)
        self._done_btn = PrimaryButton("Continuer vers Finalyse →")
        self._done_btn.setFixedHeight(42)
        self._done_btn.clicked.connect(self.accept)
        shadow(self._done_btn, blur=12, y=3, color=C["primary"], alpha=25)
        btns.addWidget(self._skip_btn)
        btns.addStretch()
        btns.addWidget(self._done_btn)
        lay.addLayout(btns)

    def _make_component_card(self, name, desc, badge, installed, task):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame{{background:{C['surf_lowest']};border-radius:12px;border:none;}}"
        )
        shadow(frame, blur=12, y=3, color=C["primary"], alpha=8)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(20, 16, 20, 16)
        fl.setSpacing(10)

        # En-tête
        hdr = QHBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['on_surface']};background:transparent;")
        badge_lbl = QLabel(badge)
        badge_bg  = C["ok_bg"] if badge == "Requis" else C["primary_fixed"]
        badge_fg  = C["secondary"] if badge == "Requis" else C["primary"]
        badge_lbl.setStyleSheet(
            f"font-size:10px;font-weight:700;color:{badge_fg};"
            f"background:{badge_bg};border-radius:6px;padding:2px 8px;"
        )
        hdr.addWidget(name_lbl); hdr.addWidget(badge_lbl); hdr.addStretch()
        fl.addLayout(hdr)

        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        fl.addWidget(desc_lbl)

        # Statut + bouton
        status_row = QHBoxLayout()
        status_lbl = QLabel("✅ Installé" if installed else "❌ Non installé")
        status_lbl.setStyleSheet(
            f"font-size:12px;font-weight:600;"
            f"color:{C['secondary'] if installed else C['error']};"
            f"background:transparent;"
        )
        status_row.addWidget(status_lbl); status_row.addStretch()

        if not installed:
            install_btn = PrimaryButton(f"Installer {name.split()[0]}")
            install_btn.setFixedHeight(36)
            install_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            install_btn.clicked.connect(lambda _, t=task, c={"status": status_lbl, "btn": install_btn}: self._install(t, c))
            status_row.addWidget(install_btn)

        fl.addLayout(status_row)

        # Barre de progression (cachée par défaut)
        prog = QProgressBar()
        prog.setRange(0, 100); prog.setValue(0)
        prog.setFixedHeight(6)
        prog.setStyleSheet(f"""
            QProgressBar{{background:{C['surf_low']};border-radius:3px;border:none;}}
            QProgressBar::chunk{{background:{C['primary']};border-radius:3px;}}
        """)
        prog.setVisible(False)
        fl.addWidget(prog)

        prog_lbl = QLabel("")
        prog_lbl.setStyleSheet(f"font-size:11px;color:{C['on_surf_var']};background:transparent;")
        prog_lbl.setVisible(False)
        fl.addWidget(prog_lbl)

        return {"frame": frame, "status": status_lbl, "prog": prog, "prog_lbl": prog_lbl}

    def _install(self, task: str, card: dict):
        btn = card.get("btn")
        if btn:
            btn.setEnabled(False)
            btn.setText("Installation...")

        # Trouver la card complète
        c = self._tess_card if task == "tesseract" else self._ollama_card
        c["prog"].setVisible(True)
        c["prog_lbl"].setVisible(True)

        w = _InstallWorker(task)
        w.progress.connect(lambda msg, pct, c=c: (
            c["prog"].setValue(pct),
            c["prog_lbl"].setText(msg)
        ))
        w.done.connect(lambda ok, msg, c=c, task=task: self._on_done(ok, msg, c, task))
        self._workers.append(w)
        w.start()

    def _on_done(self, ok: bool, msg: str, card: dict, task: str):
        card["prog"].setVisible(False)
        card["prog_lbl"].setVisible(False)
        if ok:
            card["status"].setText("✅ Installé")
            card["status"].setStyleSheet(
                f"font-size:12px;font-weight:600;color:{C['secondary']};background:transparent;"
            )
        else:
            card["status"].setText(f"❌ Erreur : {msg[:60]}")
            card["status"].setStyleSheet(
                f"font-size:12px;font-weight:600;color:{C['error']};background:transparent;"
            )
