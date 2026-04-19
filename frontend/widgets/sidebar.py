"""widgets/sidebar.py — Barre latérale de navigation Finalyse"""
import os
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QPixmap
from theme import C, Divider, shadow

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.svg")


class NavItem(QPushButton):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._active = False
        lay = QHBoxLayout(self); lay.setContentsMargins(14,0,14,0); lay.setSpacing(0)
        self._lbl = QLabel(label)
        lay.addWidget(self._lbl); lay.addStretch()
        self.setFixedHeight(44); self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._style()

    def set_active(self, v: bool):
        self._active = v; self.setChecked(v); self._style()

    def _style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton{{background:{C['sidebar_active']};border:none;border-radius:10px;
                             border-left:3px solid {C['primary']};}}
            """)
            self._lbl.setStyleSheet(
                f"background:transparent;font-size:13px;font-weight:700;color:{C['primary']};"
            )
        else:
            self.setStyleSheet(f"""
                QPushButton{{background:transparent;border:none;border-radius:10px;}}
                QPushButton:hover{{background:{C['sidebar_active']};}}
            """)
            self._lbl.setStyleSheet(
                f"background:transparent;font-size:13px;font-weight:600;color:{C['slate_500']};"
            )


class Sidebar(QFrame):
    page_changed     = pyqtSignal(int)
    logout_requested = pyqtSignal()

    ITEMS = [
        ("Tableau de Bord", 0),
        ("Import Factures", 1),
        ("Rapports",        2),
        ("Historique",      3),
        ("Sauvegarde",      4),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(260)
        self.setFixedWidth(220)
        self.setStyleSheet(f"""
            QFrame{{background:{C['sidebar_bg']};border:none;
                    border-right:1px solid {C['outline_var']};}}
        """)
        self._btns: list[tuple[int, NavItem]] = []
        lay = QVBoxLayout(self); lay.setContentsMargins(12,24,12,20); lay.setSpacing(4)

        # Logo
        logo_frame = QHBoxLayout(); logo_frame.setContentsMargins(6,0,6,0); logo_frame.setSpacing(10)
        if os.path.exists(_LOGO_PATH):
            logo_img = QLabel()
            pix = QPixmap(_LOGO_PATH).scaledToHeight(28, Qt.TransformationMode.SmoothTransformation)
            logo_img.setPixmap(pix); logo_img.setStyleSheet("background:transparent;")
            logo_frame.addWidget(logo_img)
        else:
            logo_txt = QLabel("Finalyse")
            logo_txt.setStyleSheet(
                f"font-size:20px;font-weight:800;color:{C['primary']};background:transparent;"
            )
            logo_frame.addWidget(logo_txt)
        logo_frame.addStretch(); lay.addLayout(logo_frame)

        sub = QLabel("FINANCE INTELLIGENTE")
        sub.setStyleSheet(
            f"font-size:8px;font-weight:700;color:{C['slate_500']};"
            f"letter-spacing:1.5px;background:transparent;padding-left:6px;"
        )
        lay.addWidget(sub); lay.addSpacing(20)

        nav_lbl = QLabel("NAVIGATION")
        nav_lbl.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{C['outline']};"
            f"letter-spacing:1.5px;background:transparent;padding-left:14px;"
        )
        lay.addWidget(nav_lbl); lay.addSpacing(4)

        for label, idx in self.ITEMS:
            btn = NavItem(label)
            btn.clicked.connect(lambda _, i=idx: self._click(i))
            self._btns.append((idx, btn)); lay.addWidget(btn)

        lay.addStretch(); lay.addWidget(Divider()); lay.addSpacing(8)

        # ── Infos utilisateur ─────────────────────────────────────────────
        self._user_lbl = QLabel("")
        self._user_lbl.setWordWrap(False)
        self._user_lbl.setMaximumWidth(196)
        self._user_lbl.setStyleSheet(
            f"font-size:12px;font-weight:600;color:{C['on_surface']};"
            f"background:{C['primary_fixed']};border-radius:8px;"
            f"padding:6px 10px;"
        )
        lay.addWidget(self._user_lbl)
        lay.addSpacing(6)

        logout = QPushButton("Déconnexion")
        logout.setFixedHeight(40)
        logout.setStyleSheet(f"""
            QPushButton{{background:{C['err_container']};color:{C['error']};border:none;
                         border-radius:10px;font-weight:700;font-size:13px;}}
            QPushButton:hover{{background:#ffb3ae;}}
        """)
        logout.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        logout.clicked.connect(self.logout_requested.emit); lay.addWidget(logout)
        self._activate(0)

    def _click(self, idx: int):
        self._activate(idx); self.page_changed.emit(idx)

    def _activate(self, idx: int):
        for i, btn in self._btns: btn.set_active(i==idx)

    def navigate_to(self, idx: int):
        self._activate(idx)

    def set_user(self, nom: str):
        """Affiche le nom de l'utilisateur connecté avec troncature."""
        from PyQt6.QtCore import Qt as _Qt
        self._user_lbl.setText(nom or "")
        self._user_lbl.setToolTip(nom or "")  # tooltip pour voir le nom complet


class TopBar(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setStyleSheet(f"""
            QFrame{{
                background:{C['surf_lowest']};
                border:none;
                border-bottom:2px solid {C['primary']};
            }}
        """)
        from PyQt6.QtWidgets import QHBoxLayout
        from theme import StyledLineEdit, shadow
        lay = QHBoxLayout(self); lay.setContentsMargins(24,0,24,0); lay.setSpacing(16)

        # Titre de la page
        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"font-size:17px;font-weight:800;color:{C['primary']};background:transparent;"
        )
        lay.addWidget(self._title); lay.addStretch()

        # Barre de recherche — s'adapte à la largeur
        search = StyledLineEdit("Rechercher...")
        search.setMinimumWidth(120)
        search.setMaximumWidth(280)
        search.setFixedHeight(34)
        lay.addWidget(search)

        shadow(self, blur=8, y=2, color=C["primary"], alpha=12)

    def set_title(self, t: str): self._title.setText(t)
