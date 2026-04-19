"""pages/rapports.py — Rapport Financier Professionnel Finalyse"""
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QComboBox, QDialog, QLineEdit,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QBrush, QFont, QPen
from theme import C, PrimaryButton, SecondaryButton, SectionTitle, SubTitle, StatCard, Divider, shadow, Toast


# ── Workers ────────────────────────────────────────────────────────────────

class _StatsWorker(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)
    def __init__(self, annee=None, mois=None):
        super().__init__()
        self._annee = annee
        self._mois  = mois
    def run(self):
        try:
            from api_client import api
            self.done.emit(api.dashboard(annee=self._annee, mois=self._mois))
        except Exception as e:
            self.error.emit(str(e))


class _ExportWorker(QThread):
    done  = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, mode, save_path, periode="", email_data=None,
                 annee=0, mois=0):
        super().__init__()
        self._mode    = mode
        self._path    = save_path  # chemin absolu
        self._periode = periode
        self._email   = email_data
        self._annee   = annee
        self._mois    = mois

    def run(self):
        try:
            from api_client import api
            import urllib.request, urllib.parse
            print(f"[WORKER] mode={self._mode} path={self._path!r} token={bool(api._token)}")

            if self._mode in ("csv", "pdf"):
                if self._mode == "csv":
                    url = "http://127.0.0.1:8000/api/export/csv"
                else:
                    params = []
                    if self._periode:
                        params.append(f"periode={urllib.parse.quote(self._periode)}")
                    if self._annee:
                        params.append(f"annee={self._annee}")
                    if self._mois:
                        params.append(f"mois={self._mois}")
                    qs  = ("?" + "&".join(params)) if params else ""
                    url = f"http://127.0.0.1:8000/api/export/pdf{qs}"

                print(f"[WORKER] GET {url}")
                req = urllib.request.Request(url)
                req.add_header("Authorization", f"Bearer {api._token}")

                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                print(f"[WORKER] recu {len(data)} bytes")

                with open(self._path, "wb") as f:
                    f.write(data)
                print(f"[WORKER] ecrit dans {self._path}")
                print(f"[WORKER] existe={os.path.exists(self._path)} taille={os.path.getsize(self._path)}")

                self.done.emit(self._mode, self._path)

            elif self._mode == "email" and self._email:
                print(f"[WORKER] email vers {self._email.get('to_email')}")
                r = api.send_report(
                    to_email=self._email.get("to_email", ""),
                    to_name =self._email.get("to_name",  ""),
                    periode =self._periode,
                    message =self._email.get("message",  ""),
                )
                print(f"[WORKER] email result={r}")
                self.done.emit("email", r.get("message", "Envoyé"))

        except Exception as e:
            import traceback
            print(f"[WORKER ERROR] {e}")
            traceback.print_exc()
            self.error.emit(str(e))


# ── Dialog email ──────────────────────────────────────────────────────────

class EmailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Envoyer le rapport par email")
        self.setMinimumSize(520, 420); self.resize(520, 420)
        self.setStyleSheet(f"background:{C['surface']};")
        self.result_data = None
        lay = QVBoxLayout(self); lay.setContentsMargins(32, 28, 32, 28); lay.setSpacing(16)

        h = QLabel("Envoyer le rapport par email")
        h.setStyleSheet(f"font-size:17px;font-weight:800;color:{C['primary']};background:transparent;")
        lay.addWidget(h)

        sub = QLabel("Le rapport PDF sera généré et envoyé automatiquement.")
        sub.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
        lay.addWidget(sub)

        lay.addSpacing(4)

        field_style = (
            f"QLineEdit{{"
            f"background:{C['surf_low']};"
            f"border:1.5px solid {C['outline_var']};"
            f"border-radius:10px;"
            f"padding:12px 16px;"
            f"font-size:13px;"
            f"color:{C['on_surface']};"
            f"}}"
            f"QLineEdit:focus{{"
            f"border:1.5px solid {C['primary']};"
            f"}}"
        )

        for attr, lbl, ph in [
            ("_to",  "Email destinataire *", "destinataire@email.com"),
            ("_nom", "Nom destinataire",     "Prénom Nom"),
            ("_msg", "Message (optionnel)",  "Veuillez trouver ci-joint le rapport..."),
        ]:
            lb = QLabel(lbl)
            lb.setStyleSheet(f"font-size:13px;font-weight:600;color:{C['on_surface']};background:transparent;")
            lay.addWidget(lb)
            w = QLineEdit()
            w.setPlaceholderText(ph)
            w.setFixedHeight(46)
            w.setStyleSheet(field_style)
            setattr(self, attr, w)
            lay.addWidget(w)

        lay.addStretch()

        btns = QHBoxLayout(); btns.setSpacing(12)
        cancel = SecondaryButton("Annuler")
        cancel.setFixedHeight(44); cancel.clicked.connect(self.reject)
        send = PrimaryButton("Envoyer le rapport")
        send.setFixedHeight(44); send.clicked.connect(self._ok)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(send)
        lay.addLayout(btns)

    def _ok(self):
        if not self._to.text().strip():
            self._to.setStyleSheet(
                f"QLineEdit{{background:{C['surf_low']};border:2px solid {C['error']};"
                f"border-radius:10px;padding:12px 16px;font-size:13px;}}"
            )
            return
        self.result_data = {
            "to_email": self._to.text().strip(),
            "to_name":  self._nom.text().strip(),
            "message":  self._msg.text().strip()
        }
        self.accept()


# ── Camembert ─────────────────────────────────────────────────────────────

class _PieChart(QWidget):
    """Graphique camembert dynamique — données connectées au backend en temps réel."""
    COLORS = ["#000666","#1b6d24","#f59e0b","#6366f1","#ec4899","#06b6d4","#ef4444","#8b5cf6",
              "#14b8a6","#f97316","#84cc16","#a855f7"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cats = []
        self._hover = -1
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_data(self, cats: list):
        """Met à jour les données — appelé automatiquement après chaque chargement."""
        self._cats = [c for c in cats[:10] if c.get("total", 0) > 0]
        self._hover = -1
        self.update()

    def resizeEvent(self, e):
        self.update()
        super().resizeEvent(e)

    def mouseMoveEvent(self, e):
        """Highlight au survol."""
        w, h = self.width(), self.height()
        size = min(w // 2 - 20, h - 40)
        cx, cy = size // 2 + 15, h // 2
        mx, my = e.position().x() - cx, e.position().y() - cy
        import math
        dist = math.sqrt(mx*mx + my*my)
        if dist > size // 2 or dist < 4:
            if self._hover != -1:
                self._hover = -1; self.update()
            return
        angle = math.degrees(math.atan2(-my, mx)) % 360
        total = sum(d.get("total", 0) for d in self._cats) or 1
        cur = 0.0
        for i, cat in enumerate(self._cats):
            span = cat.get("total", 0) / total * 360
            if cur <= angle < cur + span:
                if self._hover != i:
                    self._hover = i; self.update()
                return
            cur += span
        if self._hover != -1:
            self._hover = -1; self.update()

    def leaveEvent(self, e):
        if self._hover != -1:
            self._hover = -1; self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if not self._cats:
            p.setPen(QColor(C["on_surf_var"]))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Aucune donnée disponible\nImportez des factures pour voir la répartition")
            return

        size = min(w // 2 - 20, h - 40)
        cx, cy = size // 2 + 15, h // 2
        total = sum(d.get("total", 0) for d in self._cats) or 1

        # Dessiner les parts
        angle = 0
        for i, cat in enumerate(self._cats):
            span = int(cat.get("total", 0) / total * 5760)
            color = QColor(self.COLORS[i % len(self.COLORS)])
            # Légère expansion au survol
            offset = 6 if i == self._hover else 0
            import math
            mid_angle = math.radians((angle + span / 2) / 16)
            ox = int(offset * math.cos(mid_angle))
            oy = int(-offset * math.sin(mid_angle))
            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor(C["surf_lowest"]), 2))
            p.drawPie(cx - size//2 + ox, cy - size//2 + oy, size, size, angle, span)
            angle += span

        # Légende à droite
        lx = cx + size // 2 + 20
        ly = max(10, cy - len(self._cats) * 20 // 2)
        for i, cat in enumerate(self._cats):
            pct = cat.get("total", 0) / total * 100
            amt = cat.get("total", 0)
            nom = cat.get("categorie", "Autres")[:16]
            color = QColor(self.COLORS[i % len(self.COLORS)])

            # Carré couleur
            p.setBrush(QBrush(color)); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(lx, ly + i * 22, 12, 12, 3, 3)

            # Texte — gras si survolé
            font = QFont("Segoe UI", 9)
            font.setBold(i == self._hover)
            p.setFont(font)
            p.setPen(QColor(C["on_surface"]))
            p.drawText(lx + 18, ly + i * 22 + 10,
                       f"{nom}  {pct:.1f}%")

            # Montant en petit
            if i == self._hover:
                p.setFont(QFont("Segoe UI", 8))
                p.setPen(QColor(C["on_surf_var"]))
                p.drawText(lx + 18, ly + i * 22 + 20,
                           f"{amt:,.0f} FCFA")


# ── Helpers UI ────────────────────────────────────────────────────────────

def _kv(lay, label: str, value: str, value_color: str = None, bold: bool = False):
    """Ajoute une ligne label : valeur — utilise un QFrame widget (pas un layout nu)."""
    row = QFrame(); row.setStyleSheet("background:transparent;border:none;")
    rl = QHBoxLayout(row); rl.setContentsMargins(0, 2, 0, 2); rl.setSpacing(8)
    l = QLabel(label)
    l.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
    v = QLabel(value)
    v.setStyleSheet(
        f"font-size:12px;font-weight:{'700' if bold else '500'};"
        f"color:{value_color or C['on_surface']};background:transparent;"
    )
    rl.addWidget(l); rl.addStretch(); rl.addWidget(v)
    lay.addWidget(row)


def _section_title(lay, text: str, color: str = None):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"font-size:10px;font-weight:700;letter-spacing:1.2px;"
        f"color:{color or C['on_surf_var']};background:transparent;margin-top:6px;"
    )
    lay.addWidget(lbl)


def _make_card(title: str, min_h: int = 0) -> QFrame:
    card = QFrame()
    card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
    shadow(card, blur=16, y=4, color=C["primary"], alpha=10)
    lay = QVBoxLayout(card); lay.setContentsMargins(22, 18, 22, 18); lay.setSpacing(10)
    if min_h: card.setMinimumHeight(min_h)
    t = QLabel(title)
    t.setStyleSheet(f"font-size:13px;font-weight:700;color:{C['primary']};background:transparent;letter-spacing:0.3px;")
    lay.addWidget(t); lay.addWidget(Divider())
    return card


def _clear(lay, keep: int = 2):
    """Vide un layout en profondeur — supprime widgets ET sous-layouts."""
    def _purge(l):
        while l.count():
            it = l.takeAt(0)
            if it.widget():
                try: it.widget().deleteLater()
                except RuntimeError: pass
            elif it.layout():
                _purge(it.layout())
    while lay.count() > keep:
        it = lay.takeAt(keep)
        if it:
            if it.widget():
                try: it.widget().deleteLater()
                except RuntimeError: pass
            elif it.layout():
                _purge(it.layout())


# ── Page principale ────────────────────────────────────────────────────────

class RapportsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive = True
        self._ws: list = []
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"background:{C['surface']};")

        c = QWidget(); c.setStyleSheet(f"background:{C['surface']};")
        root = QVBoxLayout(c); root.setContentsMargins(32, 32, 32, 32); root.setSpacing(22)

        # ── En-tete ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(4)
        col.addWidget(SectionTitle("Rapport Financier"))
        col.addWidget(SubTitle("Compte de resultat  |  Bilan de tresorerie  |  Analyse de sante"))
        hdr.addLayout(col); hdr.addStretch()

        _cb_sty = f"""
            QComboBox{{background:{C['surf_lowest']};border:1px solid {C['outline_var']};
                border-radius:8px;padding:7px 12px;font-size:12px;font-weight:600;min-width:120px;}}
            QComboBox::drop-down{{border:none;width:20px;}}
        """
        # Sélecteur Mois
        self._mois_cb = QComboBox()
        self._mois_cb.addItem("Tous les mois", 0)
        for i, m in enumerate(["Janvier","Fevrier","Mars","Avril","Mai","Juin",
                                "Juillet","Aout","Septembre","Octobre","Novembre","Decembre"], 1):
            self._mois_cb.addItem(m, i)
        self._mois_cb.setCurrentIndex(datetime.now().month)  # mois courant par défaut
        self._mois_cb.setStyleSheet(_cb_sty)
        self._mois_cb.currentIndexChanged.connect(self._load)
        hdr.addWidget(self._mois_cb)

        # Sélecteur Année
        self._annee_cb = QComboBox()
        cur_y = datetime.now().year
        self._annee_cb.addItem("Toutes les annees", 0)
        for y in range(cur_y, cur_y - 6, -1):
            self._annee_cb.addItem(str(y), y)
        self._annee_cb.setCurrentIndex(1)  # année courante par défaut
        self._annee_cb.setStyleSheet(_cb_sty)
        self._annee_cb.currentIndexChanged.connect(self._load)
        hdr.addWidget(self._annee_cb)

        for lbl, slot, primary in [
            ("Exporter CSV",  self._export_csv,  False),
            ("Rapport PDF",   self._export_pdf,  True),
            ("Envoyer Email", self._send_email,  False),
        ]:
            btn = PrimaryButton(lbl) if primary else SecondaryButton(lbl)
            btn.setFixedHeight(40); btn.clicked.connect(slot)
            if primary: shadow(btn, blur=12, y=3, color=C["primary"], alpha=25)
            hdr.addWidget(btn)

        root.addLayout(hdr)

        # ── KPIs principaux ───────────────────────────────────────────────
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(14)
        self._kpis: list[StatCard] = []
        for icon, lbl, val in [
            ("DEP", "Charges (Depenses)", "— FCFA"),
            ("REC", "Produits (Recettes)", "— FCFA"),
            ("SOL", "Resultat Net",        "— FCFA"),
            ("TVA", "TVA Deductible",      "— FCFA"),
        ]:
            k = StatCard(icon, lbl, val); self._kpis.append(k); kpi_row.addWidget(k)
        root.addLayout(kpi_row)

        # ── Ligne 1 : Compte de resultat + Tresorerie ─────────────────────
        row1 = QHBoxLayout(); row1.setSpacing(16)

        self._cr_card = _make_card("Compte de Resultat", min_h=280)
        self._cr_lay  = self._cr_card.layout()
        row1.addWidget(self._cr_card, 1)

        self._tf_card = _make_card("Flux de Tresorerie", min_h=280)
        self._tf_lay  = self._tf_card.layout()
        row1.addWidget(self._tf_card, 1)

        self._sante_card = _make_card("Analyse de Sante", min_h=280)
        self._sante_lay  = self._sante_card.layout()
        row1.addWidget(self._sante_card, 1)
        root.addLayout(row1)

        # ── Ligne 2 : Camembert + Evolution ──────────────────────────────
        row2 = QHBoxLayout(); row2.setSpacing(16)

        pie_card = _make_card("Repartition des Charges par Categorie", min_h=260)
        self._pie = _PieChart()
        pie_card.layout().addWidget(self._pie)
        row2.addWidget(pie_card, 3)

        self._evol_card = _make_card("Evolution Mensuelle", min_h=260)
        self._evol_lay  = self._evol_card.layout()
        row2.addWidget(self._evol_card, 2)
        root.addLayout(row2)

        # ── Ligne 3 : Resume executif (texte narratif) ────────────────────
        self._resume_card = _make_card("Resume Executif")
        self._resume_lay  = self._resume_card.layout()
        root.addWidget(self._resume_card)

        self.setWidget(c)
        self._load()

    # ── Chargement ────────────────────────────────────────────────────────

    def _get_periode(self):
        """Retourne (annee, mois, label) selon les sélecteurs."""
        mois  = self._mois_cb.currentData()   # 0 = tous
        annee = self._annee_cb.currentData()  # 0 = toutes
        mois_nom  = self._mois_cb.currentText()
        annee_nom = self._annee_cb.currentText()
        if annee and mois:
            label = f"{mois_nom} {annee_nom}"
        elif annee:
            label = annee_nom
        elif mois:
            label = mois_nom
        else:
            label = "Toutes les periodes"
        return (annee if annee else None), (mois if mois else None), label

    def _load(self):
        if not self._alive: return
        # Annuler uniquement les workers de stats, pas les workers d'export
        stats_ws = [w for w in self._ws if isinstance(w, _StatsWorker)]
        for w in stats_ws:
            if w.isRunning():
                try: w.disconnect()
                except Exception: pass
            self._ws.remove(w)
        w = _StatsWorker(*self._get_periode()[:2])
        w.done.connect(self._on_data); w.error.connect(lambda e: None)
        self._ws.append(w); w.start()

    @pyqtSlot(dict)
    def _on_data(self, stats: dict):
        if not self._alive: return
        tot   = stats.get("totaux", {})
        flux  = stats.get("flux", {})
        cats  = stats.get("categories", [])
        evol  = stats.get("evolution", [])
        fourn = stats.get("fournisseurs", [])
        anom  = stats.get("nb_anomalies", 0)
        anom_total = stats.get("nb_anomalies_total", anom)
        now   = datetime.now().strftime("%d/%m/%Y")
        per   = self._get_periode()[2]

        # Valeurs clés
        dep_ht   = flux.get("depenses_ht", 0)
        dep_tva  = flux.get("depenses_tva", 0)
        dep_ttc  = flux.get("depenses_ttc", 0)
        rec_ht   = flux.get("recettes_ht", 0)
        rec_tva  = flux.get("recettes_tva", 0)
        rec_ttc  = flux.get("recettes_ttc", 0)
        nb_in    = flux.get("nb_entrantes", 0)
        nb_out   = flux.get("nb_sortantes", 0)
        solde    = flux.get("solde_net", rec_ttc - dep_ttc)
        nb_t     = tot.get("nb_traites", 0)
        nb_total = tot.get("nb_total", 0)
        nb_att   = tot.get("nb_attente", 0)
        nb_err   = tot.get("nb_erreur", 0)

        marge = (solde / rec_ttc * 100) if rec_ttc > 0 else 0
        ratio = (dep_ttc / rec_ttc) if rec_ttc > 0 else None
        taux_trait = (nb_t / nb_total * 100) if nb_total > 0 else 0

        solde_color = C["secondary"] if solde >= 0 else C["error"]

        # ── KPIs ──────────────────────────────────────────────────────────
        for card, val in zip(self._kpis, [
            f"{dep_ttc:,.0f} FCFA",
            f"{rec_ttc:,.0f} FCFA",
            f"{solde:+,.0f} FCFA",
            f"{dep_tva:,.0f} FCFA",
        ]):
            card.set_value(val)

        # ── Camembert ─────────────────────────────────────────────────────
        self._pie.set_data(cats)

        # ── Compte de Resultat ────────────────────────────────────────────
        _clear(self._cr_lay)
        _section_title(self._cr_lay, "Produits (Recettes)", C["secondary"])
        _kv(self._cr_lay, "Chiffre d'affaires HT",  f"{rec_ht:,.0f} FCFA")
        _kv(self._cr_lay, "TVA collectee",           f"{rec_tva:,.0f} FCFA")
        _kv(self._cr_lay, "Total produits TTC",      f"{rec_ttc:,.0f} FCFA", C["secondary"], bold=True)
        self._cr_lay.addWidget(Divider())
        _section_title(self._cr_lay, "Charges (Depenses)", C["error"])
        _kv(self._cr_lay, "Achats et services HT",   f"{dep_ht:,.0f} FCFA")
        _kv(self._cr_lay, "TVA deductible",           f"{dep_tva:,.0f} FCFA")
        _kv(self._cr_lay, "Total charges TTC",        f"{dep_ttc:,.0f} FCFA", C["error"], bold=True)
        self._cr_lay.addWidget(Divider())
        _section_title(self._cr_lay, "Resultat")
        _kv(self._cr_lay, "Resultat net (Prod. - Ch.)", f"{solde:+,.0f} FCFA", solde_color, bold=True)
        if rec_ttc > 0:
            _kv(self._cr_lay, "Marge nette",          f"{marge:.1f}%", solde_color)
        self._cr_lay.addStretch()

        # ── Flux de Tresorerie ────────────────────────────────────────────
        _clear(self._tf_lay)
        _section_title(self._tf_lay, "Entrees de fonds")
        _kv(self._tf_lay, "Encaissements clients",   f"{rec_ttc:,.0f} FCFA", C["secondary"])
        _kv(self._tf_lay, "Nb factures sortantes",   str(nb_out))
        self._tf_lay.addWidget(Divider())
        _section_title(self._tf_lay, "Sorties de fonds")
        _kv(self._tf_lay, "Decaissements fournisseurs", f"{dep_ttc:,.0f} FCFA", C["error"])
        _kv(self._tf_lay, "Nb factures entrantes",   str(nb_in))
        self._tf_lay.addWidget(Divider())
        _section_title(self._tf_lay, "Position de tresorerie")
        _kv(self._tf_lay, "Flux net",                f"{solde:+,.0f} FCFA", solde_color, bold=True)
        if ratio is not None:
            ratio_txt = f"{ratio:.2f}"
            ratio_color = C["secondary"] if ratio <= 1 else C["error"]
            _kv(self._tf_lay, "Ratio charges/recettes", ratio_txt, ratio_color)
        self._tf_lay.addStretch()

        # ── Analyse de Sante ──────────────────────────────────────────────
        _clear(self._sante_lay)

        def _indicateur(label: str, valeur: str, statut: str, detail: str = ""):
            row = QFrame()
            bg = C["ok_bg"] if statut == "ok" else (C["warn_bg"] if statut == "warn" else C["err_container"])
            row.setStyleSheet(f"background:{bg};border-radius:8px;border:none;")
            rl = QVBoxLayout(row); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(2)
            top = QHBoxLayout()
            lbl_w = QLabel(label)
            lbl_w.setStyleSheet(f"font-size:11px;font-weight:600;color:{C['on_surface']};background:transparent;")
            val_w = QLabel(valeur)
            col = C["secondary"] if statut == "ok" else (C["warn_fg"] if statut == "warn" else C["error"])
            val_w.setStyleSheet(f"font-size:12px;font-weight:700;color:{col};background:transparent;")
            top.addWidget(lbl_w); top.addStretch(); top.addWidget(val_w)
            rl.addLayout(top)
            if detail:
                d = QLabel(detail); d.setWordWrap(True)
                d.setStyleSheet(f"font-size:10px;color:{C['on_surf_var']};background:transparent;")
                rl.addWidget(d)
            self._sante_lay.addWidget(row)

        # Rentabilite
        if rec_ttc == 0:
            _indicateur("Rentabilite", "N/A", "warn", "Aucune recette enregistree.")
        elif solde > 0:
            _indicateur("Rentabilite", "Beneficiaire", "ok", f"Marge nette de {marge:.1f}%.")
        elif solde == 0:
            _indicateur("Rentabilite", "A l'equilibre", "warn", "Produits = Charges.")
        else:
            _indicateur("Rentabilite", "Deficitaire", "error", f"Perte de {abs(solde):,.0f} FCFA.")

        # Ratio charges/recettes
        if ratio is not None:
            if ratio <= 0.7:
                _indicateur("Ratio charges/recettes", f"{ratio:.2f}", "ok", "Charges bien maitrisees (< 70%).")
            elif ratio <= 1.0:
                _indicateur("Ratio charges/recettes", f"{ratio:.2f}", "warn", "Charges elevees, surveiller.")
            else:
                _indicateur("Ratio charges/recettes", f"{ratio:.2f}", "error", "Charges superieures aux recettes.")

        # Anomalies
        if anom == 0:
            _indicateur("Anomalies detectees", "Aucune", "ok", "Toutes les factures sont conformes.")
        elif anom <= 2:
            _indicateur("Anomalies detectees", str(anom), "warn", "Verifiez les factures concernees.")
        else:
            _indicateur("Anomalies detectees", str(anom), "error", "Nombre eleve d'anomalies. Action requise.")

        # Taux de traitement
        st = "ok" if taux_trait >= 80 else ("warn" if taux_trait >= 50 else "error")
        _indicateur("Taux de traitement", f"{taux_trait:.0f}%",  st,
                    f"{nb_t}/{nb_total} factures traitees.")

        self._sante_lay.addStretch()

        # ── Evolution mensuelle ───────────────────────────────────────────
        _clear(self._evol_lay)
        if not evol:
            lbl = QLabel("Aucune donnee d'evolution disponible.")
            lbl.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
            self._evol_lay.addWidget(lbl)
        else:
            # En-tete
            hrow = QFrame(); hrow.setStyleSheet("background:transparent;border:none;")
            hl = QHBoxLayout(hrow); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
            for txt, s in [("PERIODE", 2), ("DEPENSES", 2), ("RECETTES", 2), ("SOLDE", 2)]:
                l = QLabel(txt)
                l.setStyleSheet(f"font-size:9px;font-weight:700;letter-spacing:0.8px;color:{C['on_surf_var']};background:transparent;")
                hl.addWidget(l, s)
            self._evol_lay.addWidget(hrow)
            self._evol_lay.addWidget(Divider())
            for m in evol:
                dep = m.get("depenses", 0)
                rec = m.get("recettes", 0)
                sol = rec - dep
                sc = C["secondary"] if sol >= 0 else C["error"]
                mrow = QFrame(); mrow.setStyleSheet("background:transparent;border:none;")
                ml = QHBoxLayout(mrow); ml.setContentsMargins(0, 2, 0, 2); ml.setSpacing(0)
                for txt, s, col in [
                    (m.get("mois", "—"), 2, C["on_surface"]),
                    (f"{dep:,.0f}",       2, C["error"]),
                    (f"{rec:,.0f}",       2, C["secondary"]),
                    (f"{sol:+,.0f}",      2, sc),
                ]:
                    l = QLabel(txt)
                    l.setStyleSheet(f"font-size:11px;font-weight:600;color:{col};background:transparent;")
                    ml.addWidget(l, s)
                self._evol_lay.addWidget(mrow)
        self._evol_lay.addStretch()

        # ── Resume executif + Conseils ────────────────────────────────────
        # Vider proprement — supprimer tout sauf titre(0) et divider(1)
        while self._resume_lay.count() > 2:
            it = self._resume_lay.takeAt(2)
            if it and it.widget():
                try: it.widget().deleteLater()
                except RuntimeError: pass
        top_fourn = fourn[0].get("fournisseur", "—") if fourn else "—"
        top_cat   = cats[0].get("categorie", "—") if cats else "—"

        if solde > 0:
            verdict = f"L'entreprise degage un benefice de {solde:,.0f} FCFA sur la periode, avec une marge nette de {marge:.1f}%."
        elif solde < 0:
            verdict = f"L'entreprise enregistre une perte de {abs(solde):,.0f} FCFA. Les charges depassent les produits de {abs(marge):.1f}%."
        else:
            verdict = "L'entreprise est a l'equilibre : produits et charges sont egaux."

        # Conseils financiers personnalisés selon les données réelles
        conseils = []
        if ratio is not None and ratio > 1:
            conseils.append(("error", "Charges excessives",
                f"Vos charges ({dep_ttc:,.0f} FCFA) depassent vos recettes ({rec_ttc:,.0f} FCFA). "
                "Identifiez les postes de depenses les plus importants et negociez avec vos fournisseurs."))
        elif ratio is not None and ratio > 0.8:
            conseils.append(("warn", "Ratio charges/recettes eleve",
                f"Vos charges representent {ratio*100:.0f}% de vos recettes. "
                "Visez un ratio inferieur a 70% pour une meilleure sante financiere."))

        if anom_total > 0:
            conseils.append(("warn", f"{anom_total} anomalie(s) au total",
                f"Sur l'ensemble de vos factures, {anom_total} anomalie(s) ont ete detectees "
                f"({anom} sur la periode selectionnee). "
                "Verifiez les montants, TVA manquantes et doublons pour eviter des erreurs comptables."))

        if nb_att > 0:
            conseils.append(("info", f"{nb_att} facture(s) en attente",
                "Des factures n'ont pas encore ete analysees. "
                "Relancez le traitement pour obtenir des donnees financieres completes."))

        if fourn and len(fourn) >= 2:
            top2_total = fourn[0].get("total", 0) + fourn[1].get("total", 0)
            if dep_ttc > 0 and top2_total / dep_ttc > 0.6:
                conseils.append(("warn", "Concentration fournisseurs",
                    f"Plus de 60% de vos depenses sont concentrees sur 2 fournisseurs "
                    f"({fourn[0].get('fournisseur','')}, {fourn[1].get('fournisseur','')}). "
                    "Diversifiez vos fournisseurs pour reduire les risques."))

        if solde > 0 and marge > 20:
            conseils.append(("ok", "Excellente rentabilite",
                f"Votre marge nette de {marge:.1f}% est tres bonne. "
                "Considerez de reinvestir une partie des benefices pour accelerer la croissance."))

        if not conseils:
            conseils.append(("ok", "Situation financiere saine",
                "Vos indicateurs financiers sont dans les normes. "
                "Continuez a surveiller regulierement vos flux de tresorerie."))

        # Résumé
        resume_lbl = QLabel(
            f"Rapport du {now}  —  Periode : {per}\n\n"
            f"{verdict}\n\n"
            f"Sur {nb_total} factures importees, {nb_t} traitees ({taux_trait:.0f}%), "
            f"dont {nb_in} charges et {nb_out} produits. "
            f"Anomalies sur la periode : {anom}  |  Total anomalies : {anom_total}\n"
            f"Principal fournisseur : {top_fourn}  |  Categorie dominante : {top_cat}"
        )
        resume_lbl.setWordWrap(True)
        resume_lbl.setStyleSheet(
            f"font-size:13px;color:{C['on_surface']};background:{C['primary_fixed']};"
            f"border-radius:10px;padding:16px;"
        )
        self._resume_lay.addWidget(resume_lbl)

        # Conseils
        if conseils:
            conseils_title = QLabel("CONSEILS FINANCIERS")
            conseils_title.setStyleSheet(
                f"font-size:11px;font-weight:700;letter-spacing:1px;"
                f"color:{C['on_surf_var']};background:transparent;margin-top:8px;"
            )
            self._resume_lay.addWidget(conseils_title)

            for kind, titre, texte in conseils:
                bg_map   = {"ok": C["ok_bg"],  "warn": C["warn_bg"],  "error": C["err_container"], "info": C["primary_fixed"]}
                col_map  = {"ok": C["secondary"], "warn": C["warn_fg"], "error": C["error"],        "info": C["primary"]}
                bg  = bg_map.get(kind, C["surf_low"])
                col = col_map.get(kind, C["on_surface"])
                card = QFrame()
                card.setStyleSheet(f"background:{bg};border-radius:10px;border:none;")
                cl = QVBoxLayout(card); cl.setContentsMargins(14, 10, 14, 10); cl.setSpacing(4)
                t = QLabel(titre)
                t.setStyleSheet(f"font-size:12px;font-weight:700;color:{col};background:transparent;")
                d = QLabel(texte)
                d.setWordWrap(True)
                d.setStyleSheet(f"font-size:11px;color:{C['on_surface']};background:transparent;")
                cl.addWidget(t); cl.addWidget(d)
                self._resume_lay.addWidget(card)

    # ── Exports ───────────────────────────────────────────────────────────

    def _export_csv(self):
        from datetime import datetime
        from PyQt6.QtWidgets import QFileDialog
        # Dossier par défaut = Documents de l'utilisateur (chemin absolu)
        docs    = os.path.join(os.path.expanduser("~"), "Documents")
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        default = os.path.join(docs, f"finalyse_export_{ts}.csv")
        # getSaveFileName avec chemin absolu — fonctionne même avec os.chdir
        path, _ = QFileDialog.getSaveFileName(
            None, "Enregistrer le CSV", default, "CSV (*.csv)"
        )
        if not path:
            return
        self._set_msg("Export CSV en cours...", ok=True)
        w = _ExportWorker("csv", path)
        w.done.connect(self._on_export_done)
        w.error.connect(self._on_export_err)
        w.finished.connect(lambda: self._ws.remove(w) if w in self._ws else None)
        self._ws.append(w); w.start()

    def _export_pdf(self):
        from datetime import datetime
        from PyQt6.QtWidgets import QFileDialog
        docs    = os.path.join(os.path.expanduser("~"), "Documents")
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        default = os.path.join(docs, f"finalyse_rapport_{ts}.pdf")
        path, _ = QFileDialog.getSaveFileName(
            None, "Enregistrer le rapport PDF", default, "PDF (*.pdf)"
        )
        if not path:
            return
        annee, mois, periode = self._get_periode()
        self._set_msg("Génération du rapport en cours...", ok=True)
        w = _ExportWorker("pdf", path, periode, annee=annee or 0, mois=mois or 0)
        w.done.connect(self._on_export_done)
        w.error.connect(self._on_export_err)
        w.finished.connect(lambda: self._ws.remove(w) if w in self._ws else None)
        self._ws.append(w); w.start()

    def _send_email(self):
        from api_client import api
        print(f"[EMAIL] api.ok={api.ok}")
        if not api.ok:
            self._set_msg("Non connecté. Reconnectez-vous.", ok=False)
            return
        dial = EmailDialog(self)
        result = dial.exec()
        print(f"[EMAIL] dialog result={result}, data={dial.result_data}")
        if result != QDialog.DialogCode.Accepted:
            return
        data = dial.result_data
        if not data:
            return
        periode = self._get_periode()[2]
        print(f"[EMAIL] lancement worker email={data.get('to_email')} periode={periode!r}")
        self._set_msg("Envoi du rapport en cours...", ok=True)
        w = _ExportWorker("email", "", periode=periode, email_data=data)
        w.done.connect(self._on_export_done)
        w.error.connect(self._on_export_err)
        w.finished.connect(lambda: self._ws.remove(w) if w in self._ws else None)
        self._ws.append(w); w.start()

    @pyqtSlot(str, str)
    def _on_export_done(self, typ: str, info: str):
        if not self._alive:
            return
        if typ == "csv" and info:
            Toast(self, f"CSV enregistré ✓  —  {os.path.basename(info)}", "success")
            try:
                import subprocess
                subprocess.Popen(["explorer", f"/select,{info}"])
            except Exception:
                pass
        elif typ == "pdf" and info:
            Toast(self, f"Rapport PDF enregistré ✓  —  {os.path.basename(info)}", "success")
            try:
                os.startfile(info)
            except Exception:
                try:
                    import subprocess
                    subprocess.Popen(["explorer", f"/select,{info}"])
                except Exception:
                    pass
        elif typ == "email":
            Toast(self, "Rapport envoyé par email ✓", "success")
        else:
            Toast(self, "Export terminé ✓", "success")

    @pyqtSlot(str)
    def _on_export_err(self, msg: str):
        if not self._alive:
            return
        Toast(self, f"Erreur : {msg[:120]}", "error")

    def _set_msg(self, text: str, ok: bool = True):
        if not self._alive:
            return
        try:
            kind = "success" if ok else "error"
            t = Toast(self, text, kind)
        except Exception:
            pass

    def refresh(self):
        if self._alive: self._load()

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)
