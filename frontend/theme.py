"""theme.py — Finalyse Design System (Français)"""
from PyQt6.QtWidgets import (
    QFrame, QLabel, QPushButton, QLineEdit,
    QGraphicsDropShadowEffect, QWidget,
    QVBoxLayout, QHBoxLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect
from PyQt6.QtGui import QColor, QFont, QCursor

C = {
    "primary":        "#000666",
    "primary_c":      "#1a237e",
    "primary_fixed":  "#e8eaf6",
    "secondary":      "#1b6d24",
    "surface":        "#f8f9fa",
    "surf_low":       "#f3f4f5",
    "surf_lowest":    "#ffffff",
    "surf_high":      "#e8e9ea",
    "on_surface":     "#191c1d",
    "on_surf_var":    "#454652",
    "outline":        "#757575",
    "outline_var":    "#e0e0e0",
    "error":          "#b3261e",
    "err_container":  "#fce4ec",
    "sidebar_bg":     "#ffffff",
    "sidebar_active": "#eef0fb",
    "slate_500":      "#64748b",
    "accent":         "#3949ab",
    "ok_bg":          "#e8f5e9",
    "ok_fg":          "#1b6d24",
    "warn_bg":        "#fff8e1",
    "warn_fg":        "#f57c00",
}


def shadow(widget, blur=16, y=4, color="#000666", alpha=20):
    """
    BUG CORRIGE : l'ancienne version construisait #RRGGBBAA mais QColor
    attend #AARRGGBB → alpha toujours 0 → ombres invisibles.
    """
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    c = QColor(color)
    c.setAlpha(alpha)
    eff.setColor(c)
    widget.setGraphicsEffect(eff)


# Style global scrollbar — appliqué à toute l'app
SCROLLBAR_STYLE = f"""
    QScrollBar:vertical {{
        background: transparent; width: 6px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {C['outline_var']}; border-radius: 3px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {C['outline']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0; background: none;
    }}
    QScrollBar:horizontal {{
        background: transparent; height: 6px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {C['outline_var']}; border-radius: 3px; min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {C['outline']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0; background: none;
    }}
"""


def Divider():
    d = QFrame()
    d.setFrameShape(QFrame.Shape.HLine)
    d.setStyleSheet(f"color: {C['outline_var']};")
    return d


class StyledLineEdit(QLineEdit):
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(44)
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {C['surf_low']};
                border: none; border-radius: 8px;
                padding: 10px 14px; font-size: 13px;
                color: {C['on_surface']};
                font-family: "Segoe UI";
            }}
            QLineEdit:focus {{
                background: white;
                border: 1.5px solid {C['primary']};
            }}
        """)


class PrimaryButton(QPushButton):
    def __init__(self, text="", size="md", parent=None):
        super().__init__(text, parent)
        pad   = "14px 28px" if size == "lg" else "10px 20px"
        fsize = "14px"      if size == "lg" else "13px"
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {C['primary']}, stop:1 {C['primary_c']});
                color: white; border: none; border-radius: 8px;
                padding: {pad}; font-size: {fsize}; font-weight: 700;
                font-family: "Segoe UI";
            }}
            QPushButton:hover   {{ background: {C['accent']}; }}
            QPushButton:pressed {{ background: {C['primary_c']}; }}
            QPushButton:disabled {{
                background: {C['surf_high']}; color: {C['outline']};
            }}
        """)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))


class SecondaryButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {C['surf_low']}; color: {C['on_surface']};
                border: none; border-radius: 8px;
                padding: 9px 18px; font-size: 12px; font-weight: 600;
                font-family: "Segoe UI";
            }}
            QPushButton:hover   {{ background: {C['surf_high']}; }}
            QPushButton:pressed {{ background: {C['outline_var']}; }}
        """)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))


class SectionTitle(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"font-size:24px;font-weight:800;color:{C['primary']};background:transparent;"
        )


class SubTitle(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"font-size:13px;color:{C['on_surf_var']};background:transparent;"
        )


class StatCard(QFrame):
    """
    Carte KPI avec référence directe au QLabel valeur.
    Utilise set_value() depuis les slots — jamais lay.itemAt(N).widget().
    """
    def __init__(self, icon: str, label: str, value: str,
                 trend: str = "", up: bool = True, parent=None):
        super().__init__(parent)
        self._dead = False
        self.setStyleSheet(f"""
            QFrame {{
                background: {C['surf_lowest']};
                border-radius: 12px; border: none;
            }}
        """)
        self._shadow_eff = QGraphicsDropShadowEffect()
        self._shadow_eff.setBlurRadius(16)
        self._shadow_eff.setOffset(0, 3)
        c_col = QColor(C["primary"]); c_col.setAlpha(8)
        self._shadow_eff.setColor(c_col)
        self.setGraphicsEffect(self._shadow_eff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        top = QHBoxLayout()
        ic  = QLabel(icon)
        ic.setStyleSheet(
            f"font-size:11px;font-weight:700;color:{C['on_surf_var']};"
            f"background:transparent;letter-spacing:1px;"
        )
        top.addWidget(ic)
        top.addStretch()
        if trend:
            tc = C["secondary"] if up else C["error"]
            tl = QLabel(f"{'+'if up else'-'} {trend}")
            tl.setStyleSheet(
                f"font-size:11px;font-weight:600;color:{tc};background:transparent;"
            )
            top.addWidget(tl)
        lay.addLayout(top)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"font-size:10px;font-weight:600;color:{C['on_surf_var']};"
            f"background:transparent;letter-spacing:0.8px;"
        )
        lay.addWidget(lbl)

        # Référence directe — PAS d'accès via itemAt()
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"font-size:18px;font-weight:800;color:{C['on_surface']};background:transparent;"
        )
        lay.addWidget(self._val)

    def enterEvent(self, e):
        self._animate_shadow(24)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_shadow(16)
        super().leaveEvent(e)

    def _animate_shadow(self, target_blur: int):
        anim = QPropertyAnimation(self._shadow_eff, b"blurRadius")
        anim.setDuration(180)
        anim.setStartValue(self._shadow_eff.blurRadius())
        anim.setEndValue(target_blur)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Keep reference so it isn't GC'd mid-animation
        self._shadow_anim = anim
        anim.start()

    def set_value(self, text: str) -> None:
        """Mise à jour sûre depuis n'importe quel slot Qt."""
        if self._dead:
            return
        try:
            self._val.setText(text)
        except RuntimeError:
            self._dead = True

    def deleteLater(self):
        self._dead = True
        super().deleteLater()


class Badge(QLabel):
    _STYLES = {
        "success": ("#e8f5e9", "#1b6d24"),
        "error":   ("#fce4ec", "#b3261e"),
        "neutral": ("#e8eaf6", "#000666"),
        "warning": ("#fff8e1", "#f57c00"),
        "info":    ("#e3f2fd", "#1565c0"),
    }

    def __init__(self, text: str, style: str = "neutral", parent=None):
        super().__init__(text, parent)
        bg, fg = self._STYLES.get(style, self._STYLES["neutral"])
        self.setStyleSheet(f"""
            background:{bg}; color:{fg}; border-radius:6px;
            padding:2px 10px; font-size:10px; font-weight:700;
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class Toast(QFrame):
    """
    Notification temporaire style Material/Android.
    Usage : Toast.show(parent_widget, "Message", "success")
    Types : success | error | info | warning
    """
    _STYLES = {
        "success": ("#1b6d24", "#e8f5e9"),
        "error":   ("#b3261e", "#fce4ec"),
        "info":    ("#1565c0", "#e3f2fd"),
        "warning": ("#f57c00", "#fff8e1"),
    }

    def __init__(self, parent: QWidget, message: str, kind: str = "info"):
        super().__init__(parent)
        fg, bg = self._STYLES.get(kind, self._STYLES["info"])
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-radius: 10px;
                border: 1.5px solid {fg};
            }}
        """)
        shadow(self, blur=20, y=6, color=fg, alpha=40)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)

        dot = QLabel("●")
        dot.setStyleSheet(f"color:{fg};background:transparent;font-size:10px;")
        lay.addWidget(dot)

        lbl = QLabel(message)
        lbl.setStyleSheet(f"color:{fg};background:transparent;font-size:13px;font-weight:600;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self.adjustSize()
        self.setFixedWidth(min(360, max(220, self.sizeHint().width())))
        self.setFixedHeight(max(44, self.sizeHint().height()))

        # Position : coin bas-droit du parent
        self._reposition()
        self.raise_()
        QFrame.show(self)  # appel explicite QFrame.show pour éviter conflit avec Toast.show

        # Slide-in depuis la droite
        start = QPoint(parent.width(), self.y())
        end   = QPoint(self.x(), self.y())
        self._anim_in = QPropertyAnimation(self, b"pos")
        self._anim_in.setDuration(220)
        self._anim_in.setStartValue(start)
        self._anim_in.setEndValue(end)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in.start()

        # Auto-dismiss après 3 s
        QTimer.singleShot(3000, self._dismiss)

    def _reposition(self):
        p = self.parent()
        if p:
            margin = 16
            x = p.width()  - self.width()  - margin
            y = p.height() - self.height() - margin
            self.move(x, y)

    def _dismiss(self):
        end = QPoint(self.parent().width() if self.parent() else self.x() + 400, self.y())
        self._anim_out = QPropertyAnimation(self, b"pos")
        self._anim_out.setDuration(200)
        self._anim_out.setStartValue(self.pos())
        self._anim_out.setEndValue(end)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self.deleteLater)
        self._anim_out.start()

    @staticmethod
    def show(parent: QWidget, message: str, kind: str = "info") -> "Toast":
        """Crée et affiche un toast sur le widget parent."""
        return Toast(parent, message, kind)


class LoadingSpinner(QLabel):
    """
    Spinner animé braille qui tourne toutes les 80 ms.
    Usage : spinner = LoadingSpinner(parent)
            spinner.start()   # démarre l'animation
            spinner.stop()    # arrête et cache
    """
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, parent=None, size: int = 14, color: str | None = None):
        super().__init__(parent)
        self._idx   = 0
        self._color = color or C["primary"]
        self.setStyleSheet(
            f"font-size:{size}px;color:{self._color};background:transparent;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self):
        self._idx = 0
        self.setText(self._FRAMES[0])
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self.setText(self._FRAMES[self._idx])
