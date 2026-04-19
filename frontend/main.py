"""main.py — Finalyse Application de Bureau v1.0 (Français)"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget,
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QGraphicsOpacityEffect,
)
from PyQt6.QtGui import QFont, QIcon, QCursor
from PyQt6.QtCore import pyqtSlot, Qt, QPropertyAnimation, QEasingCurve

_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.ico")
# Fallback PNG si ICO absent
if not os.path.exists(_ICON_PATH):
    _ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")


class Session:
    token=""; uid=0; email=""; nom=""

S = Session()


class AppShell(QWidget):
    PAGE_TITLES = {
        0: "Tableau de Bord",
        1: "Import Factures",
        2: "Rapports",
        3: "Historique",
        4: "Sauvegarde Cloud",
    }

    def __init__(self, logout_cb, parent=None, user_nom: str = ""):
        super().__init__(parent)
        self._logout_cb = logout_cb
        self._alive     = True
        from theme import C, shadow as _shadow
        self.setStyleSheet(f"background:{C['surface']};border:none;")

        from widgets.sidebar   import Sidebar, TopBar
        from pages.dashboard   import DashboardPage
        from pages.import_page import ImportPage
        from pages.rapports    import RapportsPage
        from pages.historique  import HistoriquePage
        from pages.chatbot     import ChatbotPage
        from pages.backup      import BackupPage

        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._go)
        self.sidebar.logout_requested.connect(self._logout)
        if user_nom:
            self.sidebar.set_user(user_nom)
        root.addWidget(self.sidebar)

        center = QWidget()
        cl = QVBoxLayout(center); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        self.topbar = TopBar("Tableau de Bord"); cl.addWidget(self.topbar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{C['surface']};")

        self._pages = {
            0: DashboardPage(),
            1: ImportPage(),
            2: RapportsPage(),
            3: HistoriquePage(),
            4: BackupPage(),
        }
        for i in range(5):
            self.stack.addWidget(self._pages[i])

        if hasattr(self._pages[0], "navigate_to"):
            self._pages[0].navigate_to.connect(self._go)
        if hasattr(self._pages[1], "uploads_completed"):
            self._pages[1].uploads_completed.connect(self._pages[0].refresh)
            if hasattr(self._pages[2], "refresh"):
                self._pages[1].uploads_completed.connect(self._pages[2].refresh)
            if hasattr(self._pages[3], "refresh"):
                self._pages[1].uploads_completed.connect(self._pages[3].refresh)

        # Wrapper pour superposer le bouton flottant et le panel chatbot
        self._wrapper = QWidget()
        self._wrapper.setStyleSheet("background:transparent;")
        wl = QVBoxLayout(self._wrapper); wl.setContentsMargins(0,0,0,0); wl.setSpacing(0)
        wl.addWidget(self.stack)

        # Bouton flottant
        self._chat_btn = QPushButton("IA")
        self._chat_btn.setFixedSize(56, 56)
        self._chat_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._chat_btn.setToolTip("Assistant IA")
        self._chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {C['primary']}, stop:1 {C['primary_c']});
                color: white; border: none; border-radius: 28px;
                font-size: 13px; font-weight: 800; letter-spacing: 1px;
            }}
            QPushButton:hover   {{ background: {C['accent']}; }}
            QPushButton:pressed {{ background: {C['primary_c']}; }}
        """)
        _shadow(self._chat_btn, blur=20, y=6, color=C["primary"], alpha=60)
        self._chat_btn.setParent(self._wrapper)
        self._chat_btn.raise_()
        self._chat_btn.clicked.connect(self._open_chat)

        # Panel chatbot — fond opaque, pas de transparence
        self._chatbot_page = ChatbotPage()
        self._chatbot_page.setParent(self._wrapper)
        self._chatbot_page.setVisible(False)
        self._chatbot_page.setStyleSheet(f"""
            background: {C['surf_lowest']};
            border-radius: 16px;
            border: 1px solid {C['outline_var']};
        """)
        _shadow(self._chatbot_page, blur=32, y=8, color=C["primary"], alpha=40)

        self._wrapper.resizeEvent = self._on_resize
        cl.addWidget(self._wrapper)
        root.addWidget(center)
        self._go(0)

    def _on_resize(self, e):
        w = self._wrapper.width()
        h = self._wrapper.height()

        # Adapter la sidebar selon la largeur totale
        total_w = self.width()
        if total_w < 900:
            self.sidebar.setFixedWidth(160)
        elif total_w < 1100:
            self.sidebar.setFixedWidth(190)
        else:
            self.sidebar.setFixedWidth(220)

        # Bouton flottant — coin bas droit
        self._chat_btn.move(w - 72, h - 72)
        self._chat_btn.raise_()
        # Panel chatbot — taille adaptative
        pw = min(400, w - 32)
        ph = min(560, h - 100)
        self._chatbot_page.setGeometry(w - pw - 16, h - ph - 80, pw, ph)
        self._chatbot_page.raise_()

    def _open_chat(self):
        visible = self._chatbot_page.isVisible()
        self._chatbot_page.setVisible(not visible)
        self._chatbot_page.raise_()
        self._chat_btn.raise_()

    def _go(self, idx: int):
        if not self._alive: return
        if idx not in self._pages: idx = 0
        if self.stack.currentIndex() == idx:
            return
        # Fade-out current page, switch, fade-in new page
        current = self.stack.currentWidget()
        self.stack.setCurrentIndex(idx)
        new_page = self.stack.currentWidget()

        eff = QGraphicsOpacityEffect(new_page)
        new_page.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity")
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: new_page.setGraphicsEffect(None))
        self._page_anim = anim  # keep reference
        anim.start()

        self.sidebar.navigate_to(idx)
        self.topbar.set_title(self.PAGE_TITLES.get(idx, "Finalyse"))
        self._chatbot_page.setVisible(False)

        # Rafraîchir la page si elle a une méthode refresh (sauf dashboard qui se gère seul)
        page = self._pages.get(idx)
        if idx in (2, 3) and page and hasattr(page, "refresh"):
            page.refresh()

    def _logout(self):
        from api_client import api; api.logout()
        if self._logout_cb: self._logout_cb()

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)


class MainWindow(QMainWindow):
    SPLASH=0; LOGIN=1; REG=2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Finalyse — Analyse Intelligente de Factures")
        self.setMinimumSize(800, 600); self.resize(1360, 840)
        if os.path.exists(_ICON_PATH): self.setWindowIcon(QIcon(_ICON_PATH))

        # Centrer la fenêtre sur l'écran
        from PyQt6.QtGui import QScreen
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(
                sg.x() + (sg.width()  - self.width())  // 2,
                sg.y() + (sg.height() - self.height()) // 2,
            )

        self._stack = QStackedWidget(); self.setCentralWidget(self._stack)
        from pages.splash import SplashPage
        from pages.login  import LoginPage, RegisterPage

        self._splash = SplashPage()
        self._login  = LoginPage()
        self._reg    = RegisterPage()
        self._app    = None

        self._stack.addWidget(self._splash)  # 0
        self._stack.addWidget(self._login)   # 1
        self._stack.addWidget(self._reg)     # 2

        self._splash.finished.connect(self._on_splash_done)
        self._login.auth_success.connect(self._on_auth)
        self._login.go_register.connect(lambda: self._stack.setCurrentIndex(self.REG))
        self._reg.auth_success.connect(self._on_auth)
        self._reg.go_login.connect(lambda: self._stack.setCurrentIndex(self.LOGIN))
        self._stack.setCurrentIndex(self.SPLASH)

    def _on_splash_done(self):
        # Vérifier si setup nécessaire au premier lancement
        try:
            from pages.setup_wizard import needs_setup, SetupWizard
            if needs_setup():
                wizard = SetupWizard(self)
                wizard.exec()
        except Exception:
            pass
        self._stack.setCurrentIndex(self.LOGIN)

    @pyqtSlot(dict)
    def _on_auth(self, r: dict):
        from api_client import api
        S.token = r.get("access_token", ""); S.uid = r.get("uid", 0)
        S.email = r.get("email", "");        S.nom  = r.get("nom", "")
        api.set_token(S.token)
        if self._app is not None:
            self._stack.removeWidget(self._app); self._app.deleteLater(); self._app = None
        self._app = AppShell(logout_cb=self._on_logout, user_nom=S.nom or S.email)
        self._stack.addWidget(self._app); self._stack.setCurrentWidget(self._app)

    def _on_logout(self):
        self._stack.setCurrentIndex(self.LOGIN)


def main():
    # Capturer toutes les exceptions non gérées pour éviter les crashes silencieux
    import traceback
    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(f"[CRASH] Exception non geree:\n{error_msg}")
        # Ecrire dans un fichier log
        try:
            with open("crash.log", "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"\n{'='*60}\n{datetime.now()}\n{error_msg}\n")
        except Exception:
            pass
    import sys as _sys
    _sys.excepthook = handle_exception
    # Windows : définir l'AppUserModelID pour que la barre des tâches
    # affiche l'icône Finalyse au lieu de l'icône Python
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Finalyse.App.1.0")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    # Style global — scrollbars fines et modernes
    from theme import SCROLLBAR_STYLE
    app.setStyleSheet(SCROLLBAR_STYLE)

    # Icône globale de l'application (barre des tâches + fenêtres)
    if os.path.exists(_ICON_PATH):
        app.setWindowIcon(QIcon(_ICON_PATH))

    win = MainWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
