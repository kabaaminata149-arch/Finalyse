"""pages/login.py — Connexion / Inscription / Reinitialisation — Finalyse"""
import os, re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QDialog, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QLinearGradient, QColor, QPainter, QBrush, QCursor, QPixmap
from theme import C, StyledLineEdit, PrimaryButton, SecondaryButton, shadow

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.svg")

# ── Validation ────────────────────────────────────────────────────────────

_RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

def _valid_email(email: str) -> bool:
    return bool(_RE_EMAIL.match(email.strip()))

def _pwd_strength(pwd: str) -> tuple:
    """Retourne (score 0-4, message, couleur)."""
    if len(pwd) == 0:
        return 0, "", C["outline_var"]
    issues = []
    if len(pwd) < 8:
        issues.append("8 caracteres min")
    if not re.search(r"[A-Z]", pwd):
        issues.append("1 majuscule")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", pwd):
        issues.append("1 caractere special")
    if not re.search(r"\d", pwd):
        issues.append("1 chiffre")
    score = 4 - len(issues)
    if score <= 1:
        return score, "Faible — manque : " + ", ".join(issues), C["error"]
    elif score == 2:
        return score, "Moyen — manque : " + ", ".join(issues), C["warn_fg"]
    elif score == 3:
        return score, "Bon — manque : " + ", ".join(issues), "#f59e0b"
    else:
        return score, "Mot de passe fort", C["secondary"]

def _validate_pwd(pwd: str) -> str:
    """Retourne un message d erreur ou chaine vide si OK."""
    if len(pwd) < 8:
        return "Minimum 8 caracteres."
    if not re.search(r"[A-Z]", pwd):
        return "Au moins une lettre majuscule requise."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", pwd):
        return "Au moins un caractere special requis (!@#$%...)."
    if not re.search(r"\d", pwd):
        return "Au moins un chiffre requis."
    return ""


# ── Champ mot de passe avec bouton afficher/masquer ───────────────────────

class PasswordField(QFrame):
    """QLineEdit mot de passe avec bouton oeil."""
    returnPressed = pyqtSignal()

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self._inp = StyledLineEdit(placeholder)
        self._inp.setEchoMode(QLineEdit.EchoMode.Password)
        self._inp.setFixedHeight(46)
        self._inp.returnPressed.connect(self.returnPressed.emit)
        lay.addWidget(self._inp)
        self._btn = QPushButton("Voir")
        self._btn.setFixedSize(52, 46)
        self._btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn.setCheckable(True)
        self._btn.setStyleSheet(f"""
            QPushButton{{background:{C['surf_low']};border:none;border-radius:0 8px 8px 0;
                font-size:11px;font-weight:600;color:{C['on_surf_var']};}}
            QPushButton:checked{{background:{C['primary_fixed']};color:{C['primary']};}}
            QPushButton:hover{{background:{C['surf_high']};}}
        """)
        self._btn.clicked.connect(self._toggle)
        lay.addWidget(self._btn)

    def _toggle(self, checked):
        self._inp.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self._btn.setText("Cacher" if checked else "Voir")

    def text(self) -> str:
        return self._inp.text()

    def setPlaceholderText(self, t: str):
        self._inp.setPlaceholderText(t)


# ── Indicateur force mot de passe ─────────────────────────────────────────

class StrengthBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(3)
        bar_row = QHBoxLayout(); bar_row.setSpacing(4)
        self._bars = []
        for _ in range(4):
            b = QFrame(); b.setFixedHeight(4); b.setStyleSheet(f"background:{C['outline_var']};border-radius:2px;")
            bar_row.addWidget(b); self._bars.append(b)
        lay.addLayout(bar_row)
        self._lbl = QLabel("")
        self._lbl.setStyleSheet(f"font-size:10px;color:{C['on_surf_var']};background:transparent;")
        lay.addWidget(self._lbl)

    def update_strength(self, pwd: str):
        score, msg, color = _pwd_strength(pwd)
        for i, b in enumerate(self._bars):
            bg = color if i < score else C["outline_var"]
            b.setStyleSheet(f"background:{bg};border-radius:2px;")
        self._lbl.setText(msg)
        self._lbl.setStyleSheet(f"font-size:10px;color:{color};background:transparent;")


# ── Workers ───────────────────────────────────────────────────────────────

class AuthWorker(QThread):
    success = pyqtSignal(dict)
    error   = pyqtSignal(str)
    def __init__(self, mode, **kw):
        super().__init__(); self._mode=mode; self._kw=kw
    def run(self):
        try:
            from api_client import api
            r = api.login(self._kw["email"], self._kw["pwd"]) if self._mode == "login" \
                else api.register(self._kw["email"], self._kw["pwd"], self._kw.get("nom",""))
            self.success.emit(r)
        except Exception as e:
            self.error.emit(str(e))


class PingWorker(QThread):
    result = pyqtSignal(bool)
    def run(self):
        try:
            from api_client import api; self.result.emit(api.ping(retries=3))
        except Exception:
            self.result.emit(False)


# ── Dialog reinitialisation ───────────────────────────────────────────────

class ForgotDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reinitialiser le mot de passe")
        self.setFixedSize(440, 380); self.setStyleSheet(f"background:{C['surface']};")
        self._token = ""
        lay = QVBoxLayout(self); lay.setContentsMargins(28,24,28,24); lay.setSpacing(14)
        t = QLabel("Reinitialiser le mot de passe")
        t.setStyleSheet(f"font-size:16px;font-weight:800;color:{C['primary']};background:transparent;")
        lay.addWidget(t)
        d = QLabel("Saisissez votre email pour recevoir un code.")
        d.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        lay.addWidget(d)
        self._email_in = QLineEdit(); self._email_in.setPlaceholderText("votre@email.com")
        self._email_in.setStyleSheet(self._inp()); lay.addWidget(self._email_in)
        self._msg = QLabel(""); self._msg.setWordWrap(True)
        self._msg.setStyleSheet(f"font-size:12px;color:{C['secondary']};background:transparent;")
        self._msg.hide(); lay.addWidget(self._msg)
        self._token_in = QLineEdit(); self._token_in.setPlaceholderText("Code a 6 chiffres recu par email")
        self._token_in.setStyleSheet(self._inp()); self._token_in.hide(); lay.addWidget(self._token_in)
        self._pwd_in = PasswordField("Nouveau mot de passe (8+ car., maj., special)")
        self._pwd_in.hide(); lay.addWidget(self._pwd_in)
        btns = QHBoxLayout()
        self._cancel = SecondaryButton("Annuler"); self._cancel.clicked.connect(self.reject)
        self._main   = PrimaryButton("Envoyer");   self._main.clicked.connect(self._step1)
        btns.addWidget(self._cancel); btns.addWidget(self._main); lay.addLayout(btns)

    def _step1(self):
        email = self._email_in.text().strip()
        if not email: self._show("Email obligatoire.", error=True); return
        if not _valid_email(email): self._show("Email invalide.", error=True); return
        try:
            from api_client import api
            r = api.forgot_password(email)
            if r.get("email_sent"):
                self._show(f"Code envoye a {email}. Verifiez votre boite mail.")
            else:
                # Mode dev : token retourne directement
                t = r.get("reset_token", "")
                if t:
                    self._token = t
                    self._token_in.setText(t)
                    self._show(f"Mode dev — code : {t}", error=False)
                else:
                    self._show(r.get("message", "Demande envoyee."))
            self._token_in.show(); self._pwd_in.show()
            self._main.clicked.disconnect(); self._main.clicked.connect(self._step2)
            self._main.setText("Confirmer")
        except Exception as e: self._show(str(e), error=True)

    def _step2(self):
        token = self._token_in.text().strip() or self._token
        pwd   = self._pwd_in.text()
        err   = _validate_pwd(pwd)
        if err: self._show(err, error=True); return
        try:
            from api_client import api
            r = api.reset_password(token, pwd)
            self._show(r.get("message","Mot de passe mis a jour."))
            self._main.setText("Fermer"); self._main.clicked.disconnect()
            self._main.clicked.connect(self.accept)
        except Exception as e: self._show(str(e), error=True)

    def _show(self, msg, error=False):
        c = C["error"] if error else C["secondary"]
        self._msg.setStyleSheet(f"font-size:12px;color:{c};background:transparent;")
        self._msg.setText(msg); self._msg.show()

    @staticmethod
    def _inp():
        return (f"background:{C['surf_low']};border:none;border-radius:8px;"
                f"padding:10px 14px;font-size:13px;color:{C['on_surface']};")


# ── Banniere hors ligne ───────────────────────────────────────────────────

class OfflineBanner(QFrame):
    retry_clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#fff3e0;border-radius:8px;border:1px solid #ffb74d;")
        lay = QHBoxLayout(self); lay.setContentsMargins(12,8,12,8); lay.setSpacing(10)
        ic = QLabel("[!]")
        ic.setStyleSheet("font-size:13px;font-weight:700;color:#e65100;background:transparent;")
        lay.addWidget(ic)
        msg = QLabel("Le serveur ne repond pas. Assurez-vous que GO.py est lance.")
        msg.setWordWrap(True)
        msg.setStyleSheet("font-size:11px;color:#e65100;background:transparent;")
        lay.addWidget(msg, 1)
        self._btn = QPushButton("Reessayer")
        self._btn.setFixedHeight(32)
        self._btn.setStyleSheet(
            f"background:{C['primary']};color:white;border:none;border-radius:6px;"
            f"font-size:11px;font-weight:700;padding:0 12px;"
        )
        self._btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn.clicked.connect(self.retry_clicked.emit); lay.addWidget(self._btn)
        self.hide()
    def set_checking(self): self._btn.setText("Verification...")
    def set_retry(self):    self._btn.setText("Reessayer")


# ── Page Connexion ────────────────────────────────────────────────────────

class LoginPage(QWidget):
    auth_success = pyqtSignal(dict)
    go_register  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive=True; self._w=None; self._ping_w=None
        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        left = _Panel()
        left.setMinimumWidth(280); left.setMaximumWidth(520)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        root.addWidget(left, 35)
        right = QFrame()
        right.setStyleSheet(f"background:{C['surface']};border:none;")
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rl = QVBoxLayout(right); rl.setContentsMargins(48,0,48,0); rl.setSpacing(0)
        rl.addStretch(2)
        rl.addWidget(self._h("Bon retour", 28)); rl.addSpacing(4)
        rl.addWidget(self._h("Connectez-vous pour acceder a votre tableau de bord.", 13, var=True))
        rl.addSpacing(20)
        root.addWidget(right, 65)
        self._banner = OfflineBanner(); self._banner.retry_clicked.connect(self._check_backend)
        rl.addWidget(self._banner); rl.addSpacing(6)
        self._err = QLabel(); self._err.setWordWrap(True)
        self._err.setStyleSheet(
            f"background:#fce4ec;color:{C['error']};border-radius:8px;"
            f"padding:10px 14px;font-size:12px;font-weight:600;"
        )
        self._err.hide(); rl.addWidget(self._err); rl.addSpacing(6)

        # Email
        rl.addWidget(self._lbl("Email"))
        self._email = StyledLineEdit("nom@entreprise.com"); self._email.setFixedHeight(46)
        rl.addWidget(self._email); rl.addSpacing(12)

        # Mot de passe + lien oublie
        row = QHBoxLayout(); row.addWidget(self._lbl("Mot de passe")); row.addStretch()
        fp = QPushButton("Mot de passe oublie ?")
        fp.setStyleSheet(f"background:transparent;border:none;color:{C['primary']};font-size:12px;")
        fp.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        fp.clicked.connect(lambda: ForgotDialog(self).exec()); row.addWidget(fp)
        rl.addLayout(row)
        self._pwd = PasswordField("Votre mot de passe")
        self._pwd.returnPressed.connect(self._go)
        rl.addWidget(self._pwd); rl.addSpacing(20)

        self._btn = PrimaryButton("Se connecter", size="lg"); self._btn.setFixedHeight(50)
        self._btn.clicked.connect(self._go)
        shadow(self._btn, blur=16, y=4, color=C["primary"], alpha=35)
        rl.addWidget(self._btn); rl.addSpacing(28)
        r2 = QHBoxLayout(); r2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r2.addWidget(self._h("Pas encore de compte ?  ", 13, var=True))
        lnk = QPushButton("Creer un compte")
        lnk.setStyleSheet(
            f"background:transparent;border:none;color:{C['primary']};font-size:13px;font-weight:700;"
        )
        lnk.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); lnk.clicked.connect(self.go_register.emit)
        r2.addWidget(lnk); rl.addLayout(r2); rl.addStretch(3)
        self._check_backend()

    def _check_backend(self):
        self._banner.hide(); self._banner.set_checking()
        self._ping_w = PingWorker(); self._ping_w.result.connect(self._on_ping); self._ping_w.start()

    @pyqtSlot(bool)
    def _on_ping(self, ok: bool):
        if not self._alive: return
        if ok: self._banner.hide()
        else:  self._banner.show(); self._banner.set_retry()

    def _go(self):
        e = self._email.text().strip()
        p = self._pwd.text()
        if not e or not p:
            self._show_err("Veuillez remplir tous les champs."); return
        if not _valid_email(e):
            self._show_err("Adresse email invalide (ex: nom@domaine.com)."); return
        self._btn.setEnabled(False); self._btn.setText("Connexion..."); self._err.hide()
        self._w = AuthWorker("login", email=e, pwd=p)
        self._w.success.connect(self._ok); self._w.error.connect(self._ko); self._w.start()

    @pyqtSlot(dict)
    def _ok(self, r):
        if not self._alive: return
        self._btn.setEnabled(True); self._btn.setText("Se connecter"); self.auth_success.emit(r)

    @pyqtSlot(str)
    def _ko(self, msg):
        if not self._alive: return
        self._btn.setEnabled(True); self._btn.setText("Se connecter"); self._show_err(msg)

    def _show_err(self, msg):
        self._err.setText(f"  {msg}"); self._err.show()

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)

    @staticmethod
    def _h(text, size=14, bold=True, var=False):
        l = QLabel(text); c = C["on_surf_var"] if var else C["on_surface"]
        w = "800" if bold and not var else "400"
        l.setStyleSheet(f"font-size:{size}px;font-weight:{w};color:{c};background:transparent;")
        return l

    @staticmethod
    def _lbl(text):
        l = QLabel(text)
        l.setStyleSheet(
            f"font-size:12px;font-weight:600;color:{C['on_surface']};"
            f"background:transparent;margin-bottom:4px;"
        )
        return l


# ── Page Inscription ──────────────────────────────────────────────────────

class RegisterPage(QWidget):
    auth_success = pyqtSignal(dict)
    go_login     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive=True; self._w=None; self._ping_w=None
        root = QHBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        left = _Panel(title="L'intelligence\nartificielle au\nservice de votre\ncomptabilite.")
        left.setMinimumWidth(280); left.setMaximumWidth(520)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        root.addWidget(left, 35)
        right = QFrame()
        right.setStyleSheet(f"background:{C['surface']};border:none;")
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rl = QVBoxLayout(right); rl.setContentsMargins(48,0,48,0); rl.setSpacing(0)
        rl.addStretch(1)
        rl.addWidget(LoginPage._h("Creer un compte", 26)); rl.addSpacing(4)
        rl.addWidget(LoginPage._h("Quelques secondes pour commencer.", 13, var=True))
        rl.addSpacing(16)
        self._banner = OfflineBanner(); self._banner.retry_clicked.connect(self._check_backend)
        rl.addWidget(self._banner); rl.addSpacing(4)
        self._err = QLabel(); self._err.setWordWrap(True)
        self._err.setStyleSheet(
            f"background:#fce4ec;color:{C['error']};border-radius:8px;"
            f"padding:10px 14px;font-size:12px;font-weight:600;"
        )
        self._err.hide(); rl.addWidget(self._err); rl.addSpacing(4)

        # Nom
        rl.addWidget(LoginPage._lbl("Nom complet"))
        self._nom = StyledLineEdit("Kouassi brahima"); self._nom.setFixedHeight(46)
        rl.addWidget(self._nom); rl.addSpacing(10)

        # Email
        rl.addWidget(LoginPage._lbl("Email"))
        self._email = StyledLineEdit("nom@entreprise.com"); self._email.setFixedHeight(46)
        self._email.textChanged.connect(self._check_email_live)
        rl.addWidget(self._email)
        self._email_hint = QLabel("")
        self._email_hint.setStyleSheet(f"font-size:10px;color:{C['error']};background:transparent;")
        rl.addWidget(self._email_hint); rl.addSpacing(10)

        # Mot de passe
        rl.addWidget(LoginPage._lbl("Mot de passe (8+ car., 1 maj., 1 special, 1 chiffre)"))
        self._pwd = PasswordField("Votre mot de passe")
        self._pwd._inp.textChanged.connect(self._check_pwd_live)
        rl.addWidget(self._pwd)
        self._strength = StrengthBar()
        rl.addWidget(self._strength); rl.addSpacing(10)

        # Confirmation
        rl.addWidget(LoginPage._lbl("Confirmer le mot de passe"))
        self._pwd2 = PasswordField("Repetez le mot de passe")
        self._pwd2._inp.textChanged.connect(self._check_confirm_live)
        rl.addWidget(self._pwd2)
        self._confirm_hint = QLabel("")
        self._confirm_hint.setStyleSheet(f"font-size:10px;color:{C['error']};background:transparent;")
        rl.addWidget(self._confirm_hint); rl.addSpacing(14)

        self._btn = PrimaryButton("S'inscrire", size="lg"); self._btn.setFixedHeight(50)
        self._btn.clicked.connect(self._go)
        shadow(self._btn, blur=16, y=4, color=C["primary"], alpha=35)
        rl.addWidget(self._btn); rl.addSpacing(20)
        r2 = QHBoxLayout(); r2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r2.addWidget(LoginPage._h("Deja un compte ?  ", 13, var=True))
        lnk = QPushButton("Se connecter")
        lnk.setStyleSheet(
            f"background:transparent;border:none;color:{C['primary']};font-size:13px;font-weight:700;"
        )
        lnk.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)); lnk.clicked.connect(self.go_login.emit)
        r2.addWidget(lnk); rl.addLayout(r2); rl.addStretch(1); root.addWidget(right, 65)
        self._check_backend()

    # ── Validation en temps reel ──────────────────────────────────────────

    def _check_email_live(self, text: str):
        if text and not _valid_email(text):
            self._email_hint.setText("Email invalide (ex: nom@domaine.com)")
        else:
            self._email_hint.setText("")

    def _check_pwd_live(self, text: str):
        self._strength.update_strength(text)

    def _check_confirm_live(self, text: str):
        pwd = self._pwd.text()
        if text and text != pwd:
            self._confirm_hint.setText("Les mots de passe ne correspondent pas.")
        else:
            self._confirm_hint.setText("")

    # ── Soumission ────────────────────────────────────────────────────────

    def _go(self):
        e   = self._email.text().strip()
        p   = self._pwd.text()
        p2  = self._pwd2.text()
        nom = self._nom.text().strip()

        if not e or not p:
            self._show_err("Email et mot de passe obligatoires."); return
        if not _valid_email(e):
            self._show_err("Adresse email invalide (ex: nom@domaine.com)."); return
        err = _validate_pwd(p)
        if err:
            self._show_err(err); return
        if p != p2:
            self._show_err("Les mots de passe ne correspondent pas."); return

        self._btn.setEnabled(False); self._btn.setText("Creation..."); self._err.hide()
        self._w = AuthWorker("register", email=e, pwd=p, nom=nom)
        self._w.success.connect(self._ok); self._w.error.connect(self._ko); self._w.start()

    @pyqtSlot(dict)
    def _ok(self, r):
        if not self._alive: return
        self._btn.setEnabled(True); self._btn.setText("S'inscrire"); self.auth_success.emit(r)

    @pyqtSlot(str)
    def _ko(self, msg):
        if not self._alive: return
        self._btn.setEnabled(True); self._btn.setText("S'inscrire"); self._show_err(msg)

    def _show_err(self, msg):
        self._err.setText(f"  {msg}"); self._err.show()

    def _check_backend(self):
        self._banner.hide(); self._banner.set_checking()
        self._ping_w = PingWorker(); self._ping_w.result.connect(self._on_ping); self._ping_w.start()

    @pyqtSlot(bool)
    def _on_ping(self, ok):
        if not self._alive: return
        if ok: self._banner.hide()
        else:  self._banner.show(); self._banner.set_retry()

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)


# ── Panel gauche decoratif ────────────────────────────────────────────────

class _Panel(QFrame):
    def __init__(self, title="L'intelligence\nfinanciere\nau service de votre\ncroissance.", parent=None):
        super().__init__(parent)
        self._title = title
        lay = QVBoxLayout(self); lay.setContentsMargins(48,52,48,48); lay.setSpacing(10)
        if os.path.exists(_LOGO_PATH):
            logo_img = QLabel()
            pix = QPixmap(_LOGO_PATH).scaledToHeight(36, Qt.TransformationMode.SmoothTransformation)
            logo_img.setPixmap(pix); logo_img.setStyleSheet("background:transparent;")
            lay.addWidget(logo_img)
        else:
            logo = QLabel("Finalyse")
            logo.setStyleSheet("font-size:22px;font-weight:800;color:white;background:transparent;")
            lay.addWidget(logo)
        lay.addStretch()
        for line in self._title.split("\n"):
            c = C["secondary"] if any(w in line for w in ["croissance","comptabilite","comptabilité"]) else "white"
            l = QLabel(line)
            l.setStyleSheet(f"font-size:28px;font-weight:800;color:{c};background:transparent;")
            lay.addWidget(l)
        lay.addSpacing(16)
        desc = QLabel("Analyse automatique de factures\npar IA locale — 100% securise.")
        desc.setStyleSheet("font-size:13px;color:rgba(255,255,255,0.75);background:transparent;")
        lay.addWidget(desc); lay.addStretch(2)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0,0,self.width(),self.height())
        g.setColorAt(0,QColor(C["primary"])); g.setColorAt(1,QColor(C["primary_c"]))
        p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen); p.drawRect(self.rect())
