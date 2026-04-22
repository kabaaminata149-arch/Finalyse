
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QProgressBar,
    QFileDialog, QLineEdit, QSpinBox, QComboBox,
    QSizePolicy, QAbstractSpinBox, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QColor, QCursor
from theme import C, PrimaryButton, SecondaryButton, SectionTitle, SubTitle, shadow, Toast


# ════════════════════════════════════════════════════════════════════════
# POPUP NOM DU LOT
# ════════════════════════════════════════════════════════════════════════

class LotDialog(QDialog):

    def __init__(self, nb_files: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nommer ce lot de factures")
        self.setFixedSize(460, 210)
        self.setStyleSheet(f"background:{C['surface']};")
        self.lot_nom = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        t = QLabel("Nommer ce lot de factures")
        t.setStyleSheet(
            f"font-size:17px;font-weight:800;color:{C['primary']};background:transparent;"
        )
        lay.addWidget(t)

        desc = QLabel(
            f"{nb_files} fichier(s) selectionne(s). "

        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size:12px;color:{C['on_surf_var']};background:transparent;"
        )
        lay.addWidget(desc)

        self._inp = QLineEdit()
        self._inp.setText(datetime.now().strftime("Lot %d/%m/%Y %H:%M"))
        self._inp.selectAll()
        self._inp.setFixedHeight(42)
        self._inp.setStyleSheet(f"""
            QLineEdit{{
                background:white;
                border:1.5px solid {C['primary']};
                border-radius:8px;
                padding:0 14px;
                font-size:13px;
                color:{C['on_surface']};
            }}
        """)
        lay.addWidget(self._inp)

        btns = QHBoxLayout()
        cancel = SecondaryButton("Annuler")
        cancel.setFixedHeight(40)
        cancel.clicked.connect(self.reject)

        ok = PrimaryButton("Lancer l'analyse")
        ok.setFixedHeight(40)
        ok.clicked.connect(self._accept)
        shadow(ok, blur=10, y=3, color=C["primary"], alpha=28)

        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

        self._inp.returnPressed.connect(self._accept)

    def _accept(self):
        name = self._inp.text().strip()
        if not name:
            name = datetime.now().strftime("Lot %d/%m/%Y %H:%M")
        self.lot_nom = name
        self.accept()


# ════════════════════════════════════════════════════════════════════════
# ZONE DRAG & DROP
# ════════════════════════════════════════════════════════════════════════

class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self._base = f"""
            QFrame{{
                background:{C['surf_lowest']};
                border:2.5px dashed {C['outline_var']};
                border-radius:14px;
            }}
        """
        self._over = f"""
            QFrame{{
                background:{C['primary_fixed']};
                border:2.5px dashed {C['primary']};
                border-radius:14px;
            }}
        """
        self._ok = f"""
            QFrame{{
                background:{C['ok_bg']};
                border:2.5px dashed {C['ok_fg']};
                border-radius:14px;
            }}
        """
        self.setStyleSheet(self._base)
        shadow(self, blur=16, y=4, color=C["primary"], alpha=8)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)

        self._icon = QLabel("[ PDF  PNG  JPG  XLSX ]")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(
            f"font-size:11px;font-weight:700;color:{C['outline']};background:transparent;letter-spacing:3px;"
        )
        lay.addWidget(self._icon)

        self._title = QLabel("Glissez vos factures ici")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(
            f"font-size:15px;font-weight:700;color:{C['on_surface']};background:transparent;"
        )
        lay.addWidget(self._title)

        sub = QLabel("PDF, PNG, JPG, XLSX, XLS  —  plusieurs fichiers a la fois")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size:12px;color:{C['on_surf_var']};background:transparent;"
        )
        lay.addWidget(sub)

        self.browse_btn = QPushButton("Parcourir les fichiers")
        self.browse_btn.setMinimumWidth(160)
        self.browse_btn.setMaximumWidth(280)
        self.browse_btn.setFixedHeight(42)
        self.browse_btn.setStyleSheet(f"""
            QPushButton{{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {C['primary']},stop:1 {C['primary_c']});
                color:white;border:none;border-radius:9px;
                font-size:13px;font-weight:700;
            }}
            QPushButton:hover{{background:{C['accent']};}}
        """)
        self.browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        shadow(self.browse_btn, blur=12, y=3, color=C["primary"], alpha=25)
        lay.addWidget(self.browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(self._over)
            self._title.setText("Deposez ici !")

    def dragLeaveEvent(self, e):
        self.setStyleSheet(self._base)
        self._title.setText("Glissez vos factures ici")

    def dropEvent(self, e):
        self.setStyleSheet(self._base)
        self._title.setText("Glissez vos factures ici")
        paths = [
            u.toLocalFile() for u in e.mimeData().urls()
            if os.path.isfile(u.toLocalFile())
            and os.path.splitext(u.toLocalFile())[1].lower()
            in {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls"}
        ]
        if paths:
            self._flash_ok()
            self.files_dropped.emit(paths)

    def _flash_ok(self):
        """Briefly flash green to confirm files were accepted."""
        self.setStyleSheet(self._ok)
        QTimer.singleShot(600, lambda: self.setStyleSheet(self._base))


# ════════════════════════════════════════════════════════════════════════
# WORKER UPLOAD + POLL
# ════════════════════════════════════════════════════════════════════════

class UploadWorker(QThread):
    # (nom_fichier)
    file_debut   = pyqtSignal(str)
    # (nom_fichier, ok, msg, fid)
    file_upload  = pyqtSignal(str, bool, str, int)
    # (fid, statut, pct, meta)
    poll_update  = pyqtSignal(int, str, int, dict)
    # progression globale réelle (done, total, current_file)
    progress_update = pyqtSignal(int, int, str)
    # (nb_ok, nb_err)
    tout_fini    = pyqtSignal(int, int)
    error        = pyqtSignal(str)

    def __init__(self, paths: list, year: int, month,
                 lot_nom: str = ""):
        super().__init__()
        self._paths   = paths
        self._year    = year
        self._month   = month
        self._lot_nom = lot_nom

    def run(self):
        ok = err = 0
        total = len(self._paths)
        done  = 0
        try:
            from api_client import api, ApiError
            import time

            # Créer le dossier avec le nom du lot
            dossier_id = None
            if self._lot_nom:
                try:
                    r = api.create_dossier(
                        self._lot_nom,
                        desc=self._lot_nom,
                        annee=self._year,
                        mois=self._month,
                    )
                    dossier_id = r.get("id")
                except Exception:
                    pass

            for path in self._paths:
                nom = os.path.basename(path)
                self.file_debut.emit(nom)
                self.progress_update.emit(done, total, nom)
                try:
                    r = api.upload(
                        [path],
                        dossier_id  = dossier_id,
                        dossier_nom = None,
                        annee       = self._year,
                        mois        = self._month,
                    )
                    if r.get("importees", 0) > 0:
                        fid = r["factures"][0]["id"]
                        self.file_upload.emit(nom, True, "", fid)
                        # Polling jusqu'à fin réelle
                        self._poll(api, nom, fid)
                        ok += 1
                    else:
                        errs = r.get("erreurs", [])
                        msg  = errs[0].get("raison", "Refusé") if errs else "Refusé"
                        self.file_upload.emit(nom, False, msg, 0)
                        err += 1
                except ApiError as e:
                    self.file_upload.emit(nom, False, str(e), 0)
                    err += 1

                # Progression réelle : +1 fichier terminé
                done += 1
                self.progress_update.emit(done, total, "")

            self.tout_fini.emit(ok, err)
        except Exception as e:
            self.error.emit(str(e))

    def _poll(self, api, nom: str, fid: int, max_wait: int = 120):
        import time
        for step in range(max_wait // 3):
            try:
                f  = api.get_facture(fid)
                st = f.get("statut", "")
                # Progression interne du fichier (30% → 99% pendant le polling)
                pct = 30 + min(step * 10, 69)

                analyse = f.get("analyse_ia", "")
                if st == "erreur" and "non reconnu" in analyse.lower():
                    st = "non_facture"

                meta = {
                    "fournisseur": f.get("fournisseur", ""),
                    "montant_ttc": f.get("montant_ttc", 0),
                    "date":        f.get("date_facture", ""),
                    "anomalies":   len(f.get("anomalies", [])),
                    "statut":      st,
                    "analyse_ia":  analyse,
                }
                self.poll_update.emit(fid, st, pct, meta)
                if st in ("traite", "erreur", "non_facture"):
                    self.poll_update.emit(fid, st, 100, meta)
                    return
            except Exception:
                pass
            time.sleep(3)
        self.poll_update.emit(fid, "en_cours", 90, {})


# ════════════════════════════════════════════════════════════════════════
# COULEURS STATUT
# ════════════════════════════════════════════════════════════════════════

_STATUT_COLORS = {
    "en_attente":  (C["primary_fixed"],  C["primary"],   "En attente"),
    "en_cours":    (C["warn_bg"],         C["warn_fg"],   "En cours"),
    "traite":      (C["ok_bg"],           C["ok_fg"],     "Termine"),
    "erreur":      (C["err_container"],   C["error"],     "Echec"),
    "non_facture": ("#fff3e0",            "#e65100",      "Non-facture"),
}

_COL_NOM   = 0
_COL_LOT   = 1
_COL_STAT  = 2
_COL_PROG  = 3


# ════════════════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ════════════════════════════════════════════════════════════════════════

class ImportPage(QScrollArea):
    uploads_completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive       = True
        self._files       = []          # chemins selectionnes
        self._is_analyzing = False      # verrou local — une seule analyse à la fois
        self._fid_map     = {}          # fid -> row index
        self._workers     = []
        self._lot_nom = ""

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"background:{C['surface']};")

        c = QWidget()
        c.setStyleSheet(f"background:{C['surface']};")
        root = QVBoxLayout(c)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(20)

        # En-tete
        root.addWidget(SectionTitle("Import de Factures"))
        root.addWidget(SubTitle("Glissez vos fichiers, nommez le lot et lancez l'analyse IA"))

        # Parametres date
        params = QHBoxLayout(); params.setSpacing(12)
        params.addWidget(self._build_year_box())
        params.addWidget(self._build_month_box())
        params.addStretch()
        root.addLayout(params)

        # Zone drag & drop
        self._drop = DropZone()
        self._drop.files_dropped.connect(self._add_files)
        self._drop.browse_btn.clicked.connect(self._on_browse)
        root.addWidget(self._drop)

        # Barre de progression globale
        self._global_prog = QProgressBar()
        self._global_prog.setTextVisible(False)
        self._global_prog.setFixedHeight(5)
        self._global_prog.setStyleSheet(f"""
            QProgressBar{{background:{C['surf_low']};border-radius:3px;border:none;}}
            QProgressBar::chunk{{background:{C['primary']};border-radius:3px;}}
        """)
        self._global_prog.hide()
        root.addWidget(self._global_prog)

        # Statut message
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"font-size:12px;color:{C['on_surf_var']};background:transparent;"
        )
        root.addWidget(self._status)

        # Boutons action
        arow = QHBoxLayout()
        self._cnt = QLabel("0 fichier(s) selectionne(s)")
        self._cnt.setStyleSheet(
            f"font-size:12px;font-weight:600;color:{C['primary']};background:transparent;"
        )
        arow.addWidget(self._cnt); arow.addStretch()

        clear_btn = SecondaryButton("Vider la liste")
        clear_btn.setFixedHeight(40)
        clear_btn.clicked.connect(self._clear)
        arow.addWidget(clear_btn)

        self._send_btn = PrimaryButton("Envoyer et analyser")
        self._send_btn.setFixedHeight(40)
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._ask_lot_then_send)
        shadow(self._send_btn, blur=14, y=4, color=C["primary"], alpha=28)
        arow.addWidget(self._send_btn)
        root.addLayout(arow)

        # Legende statuts
        leg = QHBoxLayout(); leg.setSpacing(10)
        for bg, fg, lbl in [
            (C["primary_fixed"],  C["primary"],  "En attente"),
            (C["warn_bg"],        C["warn_fg"],  "En cours"),
            (C["ok_bg"],          C["ok_fg"],    "Termine"),
            (C["err_container"],  C["error"],    "Echec"),
            ("#fff3e0",           "#e65100",     "Non-facture"),
        ]:
            b = QLabel(lbl)
            b.setStyleSheet(
                f"font-size:10px;font-weight:700;color:{fg};background:{bg};"
                f"border-radius:6px;padding:3px 10px;"
            )
            leg.addWidget(b)
        leg.addStretch()
        root.addLayout(leg)

        # Tableau des fichiers
        self._table = self._build_table()
        root.addWidget(self._table)

        self.setWidget(c)

    # ── Tableau ───────────────────────────────────────────────────────────

    def _build_table(self) -> QTableWidget:
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["Fichier", "Lot", "Statut", "Progression"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        t.setColumnWidth(3, 160)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.setMinimumHeight(200)
        t.setStyleSheet(f"""
            QTableWidget{{
                background:{C['surf_lowest']};border-radius:12px;border:none;
                gridline-color:{C['outline_var']};font-size:12px;
            }}
            QTableWidget::item{{padding:6px 10px;}}
            QHeaderView::section{{
                background:{C['primary']};color:white;
                font-size:11px;font-weight:700;padding:8px 10px;
                border:none;letter-spacing:0.5px;
            }}
            QTableWidget::item:alternate{{background:{C['surf_low']};}}
            QTableWidget::item:selected{{background:{C['primary_fixed']};color:{C['primary']};}}
        """)
        shadow(t, blur=12, y=3, color=C["primary"], alpha=8)
        return t

    def _table_add_row(self, path: str, lot: str = "") -> int:
        nom = os.path.basename(path)
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setRowHeight(row, 40)

        # Nom
        item_nom = QTableWidgetItem(nom)
        item_nom.setData(Qt.ItemDataRole.UserRole, path)
        self._table.setItem(row, _COL_NOM, item_nom)

        # Lot
        item_lot = QTableWidgetItem(lot or "—")
        item_lot.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, _COL_LOT, item_lot)

        # Statut initial
        self._set_row_statut(row, "en_attente")

        # Progression
        prog = QProgressBar()
        prog.setRange(0, 100); prog.setValue(0)
        prog.setTextVisible(False)
        prog.setFixedHeight(6)
        prog.setStyleSheet(f"""
            QProgressBar{{background:{C['surf_low']};border-radius:3px;border:none;}}
            QProgressBar::chunk{{background:{C['primary']};border-radius:3px;}}
        """)
        self._table.setCellWidget(row, _COL_PROG, prog)
        return row

    def _set_row_statut(self, row: int, statut: str):
        bg, fg, lbl = _STATUT_COLORS.get(statut, (C["surf_low"], C["on_surface"], statut))
        item = QTableWidgetItem(lbl)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        item.setBackground(QColor(bg))
        item.setForeground(QColor(fg))
        self._table.setItem(row, _COL_STAT, item)

    def _find_row_by_path(self, path: str) -> int:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_NOM)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                return row
        return -1

    def _find_row_by_fid(self, fid: int) -> int:
        return self._fid_map.get(fid, -1)

    # ── Parametres ────────────────────────────────────────────────────────

    def _build_year_box(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"background:{C['surf_lowest']};border-radius:10px;border:none;")
        shadow(f, blur=10, y=2, color=C["primary"], alpha=7)
        hl = QHBoxLayout(f); hl.setContentsMargins(14,10,14,10); hl.setSpacing(8)
        lbl = QLabel("Annee *")
        lbl.setStyleSheet(f"font-size:11px;font-weight:700;color:{C['primary']};background:transparent;")
        hl.addWidget(lbl)
        self._year = QSpinBox()
        self._year.setRange(2000, 2099)
        self._year.setValue(datetime.now().year)
        self._year.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._year.setStyleSheet(
            f"QSpinBox{{background:{C['surf_low']};border:none;border-radius:6px;"
            f"padding:4px 10px;font-size:14px;font-weight:700;color:{C['primary']};min-width:70px;}}"
        )
        hl.addWidget(self._year); return f

    def _build_month_box(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"background:{C['surf_lowest']};border-radius:10px;border:none;")
        shadow(f, blur=10, y=2, color=C["primary"], alpha=7)
        hl = QHBoxLayout(f); hl.setContentsMargins(14,10,14,10); hl.setSpacing(8)
        lbl = QLabel("Mois")
        lbl.setStyleSheet(f"font-size:11px;font-weight:600;color:{C['on_surf_var']};background:transparent;")
        hl.addWidget(lbl)
        self._month = QComboBox()
        self._month.addItem("(tous)", None)
        import calendar
        for i in range(1, 13):
            self._month.addItem(calendar.month_name[i][:3], i)
        self._month.setStyleSheet(
            f"QComboBox{{background:{C['surf_low']};border:none;border-radius:6px;"
            f"padding:4px 10px;font-size:12px;font-weight:600;color:{C['on_surface']};min-width:70px;}}"
            f"QComboBox::drop-down{{border:none;}}"
        )
        hl.addWidget(self._month); return f

    # ── Gestion fichiers ──────────────────────────────────────────────────

    def _on_browse(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Selectionner des factures", "",
            "Factures (*.pdf *.png *.jpg *.jpeg *.xlsx *.xls)",
        )
        if files:
            self._add_files(files)

    def _add_files(self, paths: list):
        added = 0
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                self._table_add_row(p)
                added += 1
        self._upd()
        if added:
            self._drop._flash_ok()
            Toast.show(self, f"{added} fichier(s) ajouté(s). Cliquez 'Envoyer et analyser'.", "success")

    def _clear(self):
        if any(w.isRunning() for w in self._workers):
            return
        self._files.clear()
        self._fid_map.clear()
        self._table.setRowCount(0)
        self._upd()
        self._status.setText("")

    def _upd(self):
        n = len(self._files)
        self._cnt.setText(f"{n} fichier(s) selectionne(s)")
        self._send_btn.setEnabled(
            n > 0 and not any(w.isRunning() for w in self._workers)
        )

    # ── Envoi avec popup lot ──────────────────────────────────────────────

    def _ask_lot_then_send(self):
        if not self._files: return

        # Vérifier connexion
        try:
            from api_client import api
            if not api.ok:
                self._status.setText("Non connecté. Vérifiez que GO.py est lancé.")
                return
        except Exception:
            self._status.setText("Serveur inaccessible.")
            return

        # Verrou local — bloquer si une analyse est déjà en cours
        if self._is_analyzing:
            self._show_analyzing_popup()
            return

        # Popup nom du lot
        dlg = LotDialog(len(self._files), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._lot_nom = dlg.lot_nom

        # Mettre à jour la colonne Lot dans le tableau
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_LOT)
            if item:
                item.setText(self._lot_nom)

        self._send()

    def _show_analyzing_popup(self):
        """Affiche un popup professionnel indiquant qu'une analyse est en cours."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Analyse en cours")
        dlg.setFixedSize(420, 200)
        dlg.setStyleSheet(f"background:{C['surface']};")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        # Icône + titre
        title = QLabel("Analyse en cours")
        title.setStyleSheet(
            f"font-size:16px;font-weight:800;color:{C['primary']};background:transparent;"
        )
        lay.addWidget(title)

        msg = QLabel(
            "Une analyse est déjà en cours.\n"
            "Veuillez attendre sa fin avant de lancer une nouvelle analyse."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"font-size:13px;color:{C['on_surface']};background:{C['warn_bg']};"
            f"border-radius:8px;padding:12px 14px;"
        )
        lay.addWidget(msg)

        lay.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        ok_btn = PrimaryButton("Compris")
        ok_btn.setFixedHeight(40)
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(ok_btn)
        lay.addLayout(btns)
        dlg.exec()

    def _send(self):
        year  = self._year.value()
        month = self._month.currentData()

        # Activer le verrou
        self._is_analyzing = True
        self._send_btn.setEnabled(False)
        self._send_btn.setText("Analyse en cours...")
        self._drop.browse_btn.setEnabled(False)  # bloquer aussi le parcourir
        n = len(self._files)
        self._global_prog.setMaximum(n)
        self._global_prog.setValue(0)
        self._global_prog.show()
        self._status.setText(
            f"Lot : '{self._lot_nom}' — envoi de {n} fichier(s)..."
        )

        # Reset statut tableau
        for row in range(self._table.rowCount()):
            self._set_row_statut(row, "en_attente")
            prog = self._table.cellWidget(row, _COL_PROG)
            if prog: prog.setValue(0)

        w = UploadWorker(
            list(self._files), year, month, lot_nom=self._lot_nom
        )
        w.file_debut.connect(self._on_debut)
        w.file_upload.connect(self._on_upload)
        w.poll_update.connect(self._on_poll)
        w.progress_update.connect(self._on_progress_update)
        w.tout_fini.connect(self._on_tout_fini)
        w.error.connect(self._on_err)
        self._workers.append(w); w.start()

    # ── Slots ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_debut(self, nom: str):
        if not self._alive: return
        for p in self._files:
            if os.path.basename(p) == nom:
                row = self._find_row_by_path(p)
                if row >= 0:
                    self._set_row_statut(row, "en_cours")
                    prog = self._table.cellWidget(row, _COL_PROG)
                    if prog: prog.setValue(10)
                break

    @pyqtSlot(str, bool, str, int)
    def _on_upload(self, nom: str, ok: bool, msg: str, fid: int):
        if not self._alive: return
        for p in self._files:
            if os.path.basename(p) == nom:
                row = self._find_row_by_path(p)
                if row >= 0:
                    if ok and fid:
                        self._fid_map[fid] = row
                        self._set_row_statut(row, "en_cours")
                        prog = self._table.cellWidget(row, _COL_PROG)
                        if prog: prog.setValue(20)
                    else:
                        self._set_row_statut(row, "erreur")
                        prog = self._table.cellWidget(row, _COL_PROG)
                        if prog: prog.setValue(100)
                        # Afficher msg comme tooltip
                        item = self._table.item(row, _COL_NOM)
                        if item: item.setToolTip(msg)
                break

    @pyqtSlot(int, str, int, dict)
    def _on_poll(self, fid: int, statut: str, pct: int, meta: dict):
        if not self._alive: return
        row = self._find_row_by_fid(fid)
        if row < 0: return

        prog = self._table.cellWidget(row, _COL_PROG)
        if prog: prog.setValue(pct)

        if statut in ("traite", "erreur", "non_facture"):
            self._set_row_statut(row, statut)
            if prog: prog.setValue(100)
            # Mise a jour globale
            self._global_prog.setValue(self._global_prog.value() + 1)
            # Info supplementaire dans tooltip
            if meta:
                fourn = meta.get("fournisseur", "")
                mont  = meta.get("montant_ttc", 0)
                anom  = meta.get("anomalies", 0)
                tip   = f"Fournisseur: {fourn}\nMontant: {mont:,.0f} FCFA"
                if anom: tip += f"\nAnomalies: {anom}"
                if statut == "non_facture":
                    tip = f"Document non reconnu comme facture\n{meta.get('analyse_ia','')[:120]}"
                item = self._table.item(row, _COL_NOM)
                if item: item.setToolTip(tip)

    @pyqtSlot(int, int, str)
    def _on_progress_update(self, done: int, total: int, current_file: str):
        """Mise à jour de la barre de progression globale basée sur les fichiers réellement traités."""
        if not self._alive: return
        self._global_prog.setMaximum(total)
        self._global_prog.setValue(done)
        if current_file:
            pct = int(done / total * 100) if total > 0 else 0
            self._status.setText(
                f"Analyse en cours : {done}/{total} fichiers ({pct}%) — {current_file}"
            )

    @pyqtSlot(int, int)
    def _on_tout_fini(self, ok: int, err: int):
        if not self._alive: return
        # Libérer le verrou
        self._is_analyzing = False
        self._drop.browse_btn.setEnabled(True)
        self._global_prog.setValue(self._global_prog.maximum())
        QTimer.singleShot(800, self._global_prog.hide)
        self._send_btn.setEnabled(len(self._files) > 0)
        self._send_btn.setText("Envoyer et analyser")
        msg = f"Analyse terminée — {ok} réussi(s)"
        if err: msg += f"  |  {err} échec(s)"
        self._status.setText(msg)
        kind = "success" if not err else "warning"
        Toast.show(self, msg, kind)
        self.uploads_completed.emit()

    @pyqtSlot(str)
    def _on_err(self, msg: str):
        if not self._alive: return
        # Libérer le verrou
        self._is_analyzing = False
        self._drop.browse_btn.setEnabled(True)
        self._global_prog.hide()
        self._send_btn.setEnabled(len(self._files) > 0)
        self._send_btn.setText("Envoyer et analyser")
        self._status.setText(f"Erreur : {msg}")
        Toast.show(self, f"Erreur : {msg}", "error")

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)
