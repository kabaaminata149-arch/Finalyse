"""pages/splash.py — Ecran de demarrage Finalyse"""
import os, math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QLinearGradient, QRadialGradient, QColor, QPainter, QBrush, QPen, QFont, QFontMetrics

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.ico")


class BackendWaiter(QThread):
    ready = pyqtSignal(bool)
    def run(self):
        try:
            from api_client import api
            self.ready.emit(api.wait_ready(max_seconds=20))
        except Exception:
            self.ready.emit(False)


class SplashPage(QWidget):
    finished = pyqtSignal()

    MSGS = [
        "Initialisation du systeme...",
        "Chargement de la base de donnees...",
        "Demarrage du moteur IA...",
        "Connexion au serveur...",
        "Pret.",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive    = True
        self._step     = 0
        self._progress = 0.0
        self._dots     = 0
        self._waiter   = None
        self._timer    = None
        self._dot_timer = None
        self._target_progress = 0.0
        self._anim_timer = None
        QTimer.singleShot(200, self._start)

    # ── Dessin ────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # Fond dégradé bleu profond
        g = QLinearGradient(0, 0, W, H)
        g.setColorAt(0.0, QColor("#000444"))
        g.setColorAt(0.5, QColor("#000666"))
        g.setColorAt(1.0, QColor("#0a0a8a"))
        p.fillRect(self.rect(), QBrush(g))

        # Cercle lumineux central (halo)
        rg = QRadialGradient(W / 2, H * 0.42, H * 0.35)
        rg.setColorAt(0.0, QColor(30, 30, 120, 60))
        rg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(rg))

        # Ligne décorative verte en bas
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1b6d24"))
        p.drawRect(0, H - 4, W, 4)

        # ── Logo texte "Finalyse" ─────────────────────────────────────────────
        font_brand = QFont("Segoe UI", int(H * 0.09), QFont.Weight.Bold)
        p.setFont(font_brand)
        p.setPen(QColor("white"))
        fm = QFontMetrics(font_brand)
        brand_w = fm.horizontalAdvance("Finalyse")
        brand_y = int(H * 0.38)
        p.drawText((W - brand_w) // 2, brand_y, "Finalyse")

        # Sous-titre
        font_sub = QFont("Segoe UI", int(H * 0.025))
        p.setFont(font_sub)
        p.setPen(QColor(180, 180, 220, 180))
        sub = "Analyse Intelligente de Factures"
        fm2 = QFontMetrics(font_sub)
        sub_w = fm2.horizontalAdvance(sub)
        p.drawText((W - sub_w) // 2, brand_y + int(H * 0.065), sub)

        # ── Barre de progression ──────────────────────────────────────────────
        bar_w  = int(W * 0.45)
        bar_h  = 4
        bar_x  = (W - bar_w) // 2
        bar_y  = int(H * 0.68)

        # Fond barre
        p.setBrush(QColor(255, 255, 255, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)

        # Remplissage barre
        fill_w = int(bar_w * self._progress / 100)
        if fill_w > 0:
            grad_bar = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            grad_bar.setColorAt(0.0, QColor("#4fc3f7"))
            grad_bar.setColorAt(1.0, QColor("#1b6d24"))
            p.setBrush(QBrush(grad_bar))
            p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 2, 2)

        # ── Message ───────────────────────────────────────────────────────────
        font_msg = QFont("Segoe UI", int(H * 0.022))
        p.setFont(font_msg)
        p.setPen(QColor(200, 200, 230, 160))
        msg = self.MSGS[min(self._step, len(self.MSGS) - 1)]
        dots = "." * (self._dots % 4)
        msg_full = msg.rstrip(".") + dots
        fm3 = QFontMetrics(font_msg)
        msg_w = fm3.horizontalAdvance(msg_full)
        p.drawText((W - msg_w) // 2, bar_y + int(H * 0.06), msg_full)

        # ── Version ───────────────────────────────────────────────────────────
        font_ver = QFont("Segoe UI", int(H * 0.018))
        p.setFont(font_ver)
        p.setPen(QColor(255, 255, 255, 50))
        p.drawText(W - 80, H - 16, "v1.0.0")

    # ── Logique ───────────────────────────────────────────────────────────────

    def _start(self):
        self._waiter = BackendWaiter()
        self._waiter.ready.connect(self._on_backend)
        self._waiter.start()

        # Timer progression
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(700)

        # Timer animation points
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start(300)

        # Timer animation barre fluide
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_anim)
        self._anim_timer.start(30)

    def _tick(self):
        if not self._alive: return
        self._step += 1
        self._target_progress = min(self._step * 18, 85)

    def _tick_dots(self):
        if not self._alive: return
        self._dots += 1
        self.update()

    def _tick_anim(self):
        if not self._alive: return
        if self._progress < self._target_progress:
            self._progress = min(self._progress + 1.5, self._target_progress)
            self.update()

    @pyqtSlot(bool)
    def _on_backend(self, ok: bool):
        if not self._alive: return
        for t in [self._timer, self._dot_timer]:
            if t: t.stop()
        self._step = len(self.MSGS) - 1
        self._target_progress = 100
        # Attendre que la barre atteigne 100%
        QTimer.singleShot(600, self._emit_finished)

    def _emit_finished(self):
        if self._alive: self.finished.emit()

    def closeEvent(self, e):
        self._alive = False
        for t in [self._timer, self._dot_timer, self._anim_timer]:
            if t: t.stop()
        super().closeEvent(e)
