"""pages/backup.py — Sauvegarde Cloud Finalyse (manuelle uniquement)"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QPushButton, QDialog, QScrollArea,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCursor
from theme import C, PrimaryButton, SecondaryButton, SectionTitle, shadow, Toast, Divider


class _BackupWorker(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, action: str):
        super().__init__()
        self._action = action

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self.error.emit(str(e))

    def _execute(self):
        uid, email = _decode_token()
        if not email:
            self.error.emit("Non connecté. Reconnectez-vous.")
            return

        import sys
        here    = os.path.dirname(os.path.abspath(__file__))
        backend = os.path.normpath(os.path.join(here, "..", "..", "backend"))
        if backend not in sys.path:
            sys.path.insert(0, backend)

        from dotenv import load_dotenv
        load_dotenv(os.path.join(backend, ".env"), override=True)

        if self._action == "info":
            from services.cloud_backup import get_backup_info
            mongo_uri = os.getenv("MONGODB_URI", "").strip()
            if not mongo_uri:
                self.done.emit({"configured": False})
                return
            self.done.emit(get_backup_info(email))

        elif self._action == "save":
            import database.db as db
            db.init()
            from services.cloud_backup import backup_user
            self.done.emit(backup_user(uid, email))

        elif self._action == "restore":
            import database.db as db
            db.init()
            from services.cloud_backup import restore_user
            self.done.emit(restore_user(uid, email))


def _decode_token() -> tuple:
    try:
        from api_client import api
        token = api._token
        if not token:
            return 0, ""
        import base64, json as _j
        parts = token.split(".")
        if len(parts) != 3:
            return 0, ""
        pad     = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = _j.loads(base64.urlsafe_b64decode(pad))
        return int(payload.get("sub", 0)), payload.get("email", "")
    except Exception:
        return 0, ""


class RestoreDialog(QDialog):
    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restaurer depuis le cloud")
        self.setFixedSize(460, 280)
        self.setStyleSheet(f"background:{C['surface']};")
        lay = QVBoxLayout(self); lay.setContentsMargins(28, 24, 28, 24); lay.setSpacing(16)

        h = QLabel("Restaurer depuis la sauvegarde cloud ?")
        h.setStyleSheet(f"font-size:16px;font-weight:800;color:{C['primary']};background:transparent;")
        lay.addWidget(h)

        ts   = info.get("timestamp", "")[:19].replace("T", " à ")
        nb_f = info.get("nb_factures", 0)
        nb_d = info.get("nb_dossiers", 0)

        details = QFrame()
        details.setStyleSheet(f"background:{C['primary_fixed']};border-radius:10px;border:none;")
        dl = QVBoxLayout(details); dl.setContentsMargins(16, 12, 16, 12); dl.setSpacing(6)
        for lbl, val in [
            ("Dernière sauvegarde",   ts),
            ("Factures sauvegardées", str(nb_f)),
            ("Dossiers sauvegardés",  str(nb_d)),
        ]:
            row = QHBoxLayout()
            l = QLabel(lbl); l.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
            v = QLabel(val); v.setStyleSheet(f"font-size:12px;font-weight:700;color:{C['primary']};background:transparent;")
            row.addWidget(l); row.addStretch(); row.addWidget(v)
            dl.addLayout(row)
        lay.addWidget(details)

        warn = QLabel("Les données actuelles sont conservées. Les données restaurées s'ajouteront.")
        warn.setWordWrap(True)
        warn.setStyleSheet(f"font-size:11px;color:{C['warn_fg']};background:{C['warn_bg']};border-radius:8px;padding:8px 12px;")
        lay.addWidget(warn)

        btns = QHBoxLayout()
        cancel = SecondaryButton("Annuler"); cancel.clicked.connect(self.reject)
        ok = PrimaryButton("Restaurer maintenant"); ok.clicked.connect(self.accept)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(ok)
        lay.addLayout(btns)


class BackupPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive = True
        self._ws: list = []
        self._info: dict = {}

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"background:{C['surface']};")

        c = QWidget(); c.setStyleSheet(f"background:{C['surface']};")
        root = QVBoxLayout(c); root.setContentsMargins(32, 32, 32, 32); root.setSpacing(24)

        # ── En-tête ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(4)
        col.addWidget(SectionTitle("Sauvegarde Cloud"))
        hdr.addLayout(col); hdr.addStretch()
        root.addLayout(hdr)

        # ── Statut ────────────────────────────────────────────────────────
        self._status_card = QFrame()
        self._status_card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
        shadow(self._status_card, blur=16, y=4, color=C["primary"], alpha=10)
        sl = QVBoxLayout(self._status_card); sl.setContentsMargins(24, 20, 24, 20); sl.setSpacing(12)

        sh = QHBoxLayout()
        self._status_icon  = QLabel("☁")
        self._status_icon.setStyleSheet("font-size:28px;background:transparent;")
        sh.addWidget(self._status_icon)
        sc = QVBoxLayout(); sc.setSpacing(2)
        self._status_title = QLabel("Vérification...")
        self._status_title.setStyleSheet(f"font-size:15px;font-weight:700;color:{C['on_surface']};background:transparent;")
        self._status_sub   = QLabel("")
        self._status_sub.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        sc.addWidget(self._status_title); sc.addWidget(self._status_sub)
        sh.addLayout(sc); sh.addStretch()
        sl.addLayout(sh)
        sl.addWidget(Divider())
        self._info_lay = QVBoxLayout(); self._info_lay.setSpacing(6)
        sl.addLayout(self._info_lay)
        root.addWidget(self._status_card)

        # ── Actions ───────────────────────────────────────────────────────
        actions_card = QFrame()
        actions_card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
        shadow(actions_card, blur=16, y=4, color=C["primary"], alpha=10)
        al = QVBoxLayout(actions_card); al.setContentsMargins(24, 20, 24, 20); al.setSpacing(16)

        # Sauvegarder
        save_row = QHBoxLayout()
        save_info = QVBoxLayout(); save_info.setSpacing(4)
        save_title = QLabel("Sauvegarder maintenant")
        save_title.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['on_surface']};background:transparent;")
        save_desc = QLabel("Envoie toutes vos données vers le cloud MongoDB")
        save_desc.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        save_info.addWidget(save_title); save_info.addWidget(save_desc)
        save_row.addLayout(save_info); save_row.addStretch()
        self._save_btn = PrimaryButton("Sauvegarder")
        self._save_btn.setFixedHeight(40)
        self._save_btn.clicked.connect(self._do_save)
        shadow(self._save_btn, blur=10, y=3, color=C["primary"], alpha=25)
        save_row.addWidget(self._save_btn)
        al.addLayout(save_row)

        al.addWidget(Divider())

        # Restaurer
        restore_row = QHBoxLayout()
        restore_info = QVBoxLayout(); restore_info.setSpacing(4)
        restore_title = QLabel("Restaurer depuis le cloud")
        restore_title.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['on_surface']};background:transparent;")
        restore_desc = QLabel("Récupère toutes vos données depuis la dernière sauvegarde")
        restore_desc.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        restore_info.addWidget(restore_title); restore_info.addWidget(restore_desc)
        restore_row.addLayout(restore_info); restore_row.addStretch()
        self._restore_btn = SecondaryButton("Restaurer")
        self._restore_btn.setFixedHeight(40)
        self._restore_btn.clicked.connect(self._do_restore)
        restore_row.addWidget(self._restore_btn)
        al.addLayout(restore_row)
        root.addWidget(actions_card)

        # ── Config MongoDB (affiché seulement si non configuré) ───────────
        self._config_card = QFrame()
        self._config_card.setStyleSheet(f"background:{C['warn_bg']};border-radius:14px;border:none;")
        cl = QVBoxLayout(self._config_card); cl.setContentsMargins(24, 20, 24, 20); cl.setSpacing(8)
        ct = QLabel("Sauvegarde cloud non configurée")
        ct.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['warn_fg']};background:transparent;")
        cl.addWidget(ct)
        config_text = QLabel(
            "Pour activer la sauvegarde cloud, contactez votre administrateur\n"
            "ou configurez MongoDB Atlas dans les paramètres système."
        )
        config_text.setWordWrap(True)
        config_text.setStyleSheet(f"font-size:12px;color:{C['on_surface']};background:transparent;")
        cl.addWidget(config_text)
        root.addWidget(self._config_card)

        root.addStretch()
        self.setWidget(c)
        self._load_info()

    def _load_info(self):
        if not self._alive: return
        w = _BackupWorker("info")
        w.done.connect(self._on_info)
        w.error.connect(lambda e: None)
        self._ws.append(w); w.start()

    @pyqtSlot(dict)
    def _on_info(self, info: dict):
        if not self._alive: return
        self._info = info

        while self._info_lay.count():
            it = self._info_lay.takeAt(0)
            if it and it.widget():
                try: it.widget().deleteLater()
                except: pass

        if not info.get("configured"):
            self._status_icon.setText("⚠")
            self._status_title.setText("Cloud non configuré")
            self._status_sub.setText("La sauvegarde cloud n'est pas disponible")
            self._save_btn.setEnabled(False)
            self._restore_btn.setEnabled(False)
            self._config_card.setVisible(True)
            return

        self._config_card.setVisible(False)

        if not info.get("has_backup"):
            self._status_icon.setText("☁")
            self._status_title.setText("Aucune sauvegarde")
            self._status_sub.setText("Effectuez votre première sauvegarde")
            self._restore_btn.setEnabled(False)
        else:
            ts   = info.get("timestamp", "")[:19].replace("T", " à ")
            nb_f = info.get("nb_factures", 0)
            nb_d = info.get("nb_dossiers", 0)
            self._status_icon.setText("✅")
            self._status_title.setText("Sauvegarde disponible")
            self._status_sub.setText(f"Dernière sauvegarde : {ts}")
            self._restore_btn.setEnabled(True)

            for lbl, val in [
                ("Factures sauvegardées", str(nb_f)),
                ("Dossiers sauvegardés",  str(nb_d)),
            ]:
                row = QFrame(); row.setStyleSheet("background:transparent;border:none;")
                rl = QHBoxLayout(row); rl.setContentsMargins(0, 2, 0, 2)
                l = QLabel(lbl); l.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
                v = QLabel(val); v.setStyleSheet(f"font-size:13px;font-weight:700;color:{C['primary']};background:transparent;")
                rl.addWidget(l); rl.addStretch(); rl.addWidget(v)
                self._info_lay.addWidget(row)

    def _do_save(self):
        if not self._alive: return
        self._save_btn.setEnabled(False); self._save_btn.setText("Sauvegarde...")
        w = _BackupWorker("save")
        w.done.connect(self._on_save_done)
        w.error.connect(self._on_save_err)
        self._ws.append(w); w.start()

    @pyqtSlot(dict)
    def _on_save_done(self, result: dict):
        if not self._alive: return
        try:
            self._save_btn.setEnabled(True); self._save_btn.setText("Sauvegarder")
            if result.get("ok"):
                nb = result.get("nb_factures", 0)
                Toast.show(self, f"Sauvegarde réussie — {nb} factures", "success")
                self._load_info()
            else:
                Toast.show(self, "La sauvegarde a échoué. Vérifiez votre connexion.", "error")
        except RuntimeError:
            pass

    @pyqtSlot(str)
    def _on_save_err(self, msg: str):
        if not self._alive: return
        try:
            self._save_btn.setEnabled(True); self._save_btn.setText("Sauvegarder")
            Toast.show(self, "Sauvegarde impossible. Vérifiez votre connexion.", "error")
        except RuntimeError:
            pass

    def _do_restore(self):
        if not self._alive or not self._info.get("has_backup"): return
        dial = RestoreDialog(self._info, self)
        if dial.exec() != QDialog.DialogCode.Accepted: return
        self._restore_btn.setEnabled(False); self._restore_btn.setText("Restauration...")
        w = _BackupWorker("restore")
        w.done.connect(self._on_restore_done)
        w.error.connect(self._on_restore_err)
        self._ws.append(w); w.start()

    @pyqtSlot(str)
    def _on_restore_err(self, msg: str):
        if not self._alive: return
        self._restore_btn.setEnabled(True); self._restore_btn.setText("Restaurer")
        Toast.show(self, "Restauration impossible. Vérifiez votre connexion.", "error")

    @pyqtSlot(dict)
    def _on_restore_done(self, result: dict):
        if not self._alive: return
        self._restore_btn.setEnabled(True); self._restore_btn.setText("Restaurer")
        if result.get("ok"):
            nb = result.get("nb_factures", 0)
            Toast.show(self, f"Restauration réussie — {nb} factures récupérées", "success")
        else:
            Toast.show(self, "Restauration impossible. Aucune donnée trouvée.", "error")

    def closeEvent(self, e):
        self._alive = False
        for w in self._ws:
            if w.isRunning():
                w.quit(); w.wait(2000)
        super().closeEvent(e)
