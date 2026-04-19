
from datetime import datetime
from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QLineEdit, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from theme import C, SectionTitle, SubTitle, StatCard, Badge, SecondaryButton, shadow, Divider, Toast, LoadingSpinner

MOIS_NOMS = ["Tous les mois","Janvier","Fevrier","Mars","Avril","Mai","Juin",
             "Juillet","Aout","Septembre","Octobre","Novembre","Decembre"]


class _W(QThread):
    done  = pyqtSignal(list, dict)
    error = pyqtSignal(str)
    def __init__(self, annee=None, mois=None):
        super().__init__()
        self._annee = annee
        self._mois  = mois
    def run(self):
        try:
            from api_client import api
            kw = {"limit": 500}
            if self._annee: kw["annee"] = self._annee
            if self._mois:  kw["mois"]  = self._mois
            f = api.get_factures(**kw).get("factures", [])
            t = api.dashboard().get("totaux", {})
            self.done.emit(f, t)
        except Exception as e:
            self.error.emit(str(e))


class HistoriquePage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive = True
        self._all   = []
        self._ws    = []
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"background:{C['surface']};")

        c = QWidget(); c.setStyleSheet(f"background:{C['surface']};")
        root = QVBoxLayout(c)
        root.setContentsMargins(32, 32, 32, 32); root.setSpacing(24)

        # ── En-tête ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(4)
        col.addWidget(SectionTitle("Historique des Factures"))
        col.addWidget(SubTitle("Filtrez par mois et annee"))
        hdr.addLayout(col); hdr.addStretch()

        # Filtre Mois
        self._mois_cb = QComboBox()
        self._mois_cb.addItems(MOIS_NOMS)
        self._mois_cb.setFixedHeight(36)
        self._mois_cb.setStyleSheet(self._cb_style())
        self._mois_cb.currentIndexChanged.connect(self._on_filter)
        hdr.addWidget(self._mois_cb)

        # Filtre Année
        self._annee_cb = QComboBox()
        current_year = datetime.now().year
        self._annee_cb.addItem("Toutes les annees", 0)
        for y in range(current_year, current_year - 6, -1):
            self._annee_cb.addItem(str(y), y)
        self._annee_cb.setFixedHeight(36)
        self._annee_cb.setStyleSheet(self._cb_style())
        self._annee_cb.currentIndexChanged.connect(self._on_filter)
        hdr.addWidget(self._annee_cb)

        # Recherche texte
        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher fournisseur...")
        self._search.setMinimumWidth(150); self._search.setMaximumWidth(300)
        self._search.setFixedHeight(36)
        self._search.setStyleSheet(
            f"background:{C['surf_lowest']};border:1px solid {C['outline_var']};"
            f"border-radius:8px;padding:0 12px;font-size:13px;"
        )
        self._search.textChanged.connect(self._filter_text)
        hdr.addWidget(self._search)

        ref = SecondaryButton("Actualiser"); ref.clicked.connect(self._load)
        hdr.addWidget(ref)

        # Spinner de chargement
        self._spinner = LoadingSpinner(size=16, color=C["primary"])
        hdr.addWidget(self._spinner)

        root.addLayout(hdr)

        # ── KPIs ──────────────────────────────────────────────────────────
        grid = QHBoxLayout(); grid.setSpacing(16)
        self._kpis: list[StatCard] = []
        for icon, label, val in [
            ("ALL", "Total Factures", "—"),
            ("OK",  "Traitees",       "—"),
            ("ATT", "En Attente",     "—"),
            ("FCFA","Total TTC",      "— FCFA"),
        ]:
            k = StatCard(icon, label, val)
            self._kpis.append(k); grid.addWidget(k)
        root.addLayout(grid)

        # ── Tableau ───────────────────────────────────────────────────────
        table_card = QFrame()
        table_card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
        shadow(table_card, blur=16, y=4, color=C["primary"], alpha=10)
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(20, 16, 20, 16); tl.setSpacing(6)

        h_row = QHBoxLayout()
        for lbl, w in [("FOURNISSEUR",3),("DATE",1),("MONTANT TTC",2),("CATEGORIE",1),("TYPE",1),("STATUT",1)]:
            l = QLabel(lbl)
            l.setStyleSheet(
                f"font-size:9px;font-weight:700;letter-spacing:0.8px;"
                f"color:{C['on_surf_var']};background:transparent;"
            )
            h_row.addWidget(l, w)
        tl.addLayout(h_row); tl.addWidget(Divider())
        self._rows_lay = QVBoxLayout(); self._rows_lay.setSpacing(2)
        tl.addLayout(self._rows_lay)
        root.addWidget(table_card)
        self.setWidget(c)
        self._load()

    def _cb_style(self):
        return f"""
            QComboBox{{background:{C['surf_lowest']};border:1px solid {C['outline_var']};
                border-radius:8px;padding:0 12px;font-size:12px;font-weight:600;min-width:130px;}}
            QComboBox::drop-down{{border:none;width:20px;}}
        """

    def _get_filters(self):
        mois  = self._mois_cb.currentIndex()   # 0 = tous
        annee = self._annee_cb.currentData()   # 0 = toutes
        return (annee if annee else None), (mois if mois > 0 else None)

    def _on_filter(self):
        if not self._alive: return
        self._load()

    def _load(self):
        if not self._alive: return
        self._spinner.start()
        annee, mois = self._get_filters()
        w = _W(annee, mois)
        w.done.connect(self._on_data)
        w.error.connect(lambda e: (self._spinner.stop(), Toast.show(self, f"Erreur : {e}", "error")))
        self._ws.append(w); w.start()

    @pyqtSlot(list, dict)
    def _on_data(self, factures: list, totaux: dict):
        if not self._alive: return
        self._spinner.stop()
        self._all = factures
        total_ttc = sum(f.get("montant_ttc", 0) for f in factures)
        nb_traites = sum(1 for f in factures if f.get("statut") == "traite")
        nb_attente = sum(1 for f in factures if f.get("statut") == "en_attente")
        for card, val in zip(self._kpis, [
            str(len(factures)),
            str(nb_traites),
            str(nb_attente),
            f"{total_ttc:,.0f} FCFA",
        ]):
            card.set_value(val)
        self._render(factures)

    def _filter_text(self, q: str):
        if not self._alive: return
        q = q.lower()
        filtered = [
            f for f in self._all
            if q in (f.get("fournisseur","") + " " +
                     f.get("ref_facture","") + " " +
                     f.get("nom_fichier","")).lower()
        ] if q else self._all
        self._render(filtered)

    def _render(self, factures: list):
        if not self._alive: return
        while self._rows_lay.count():
            it = self._rows_lay.takeAt(0)
            if it and it.widget(): it.widget().deleteLater()

        if not factures:
            empty_w = QWidget()
            el = QVBoxLayout(empty_w); el.setAlignment(Qt.AlignmentFlag.AlignCenter); el.setSpacing(8)
            icon_lbl = QLabel("📄")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("font-size:32px;background:transparent;")
            el.addWidget(icon_lbl)
            lbl = QLabel("Aucun résultat pour cette période.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:13px;color:{C['on_surf_var']};background:transparent;padding:4px 0;")
            el.addWidget(lbl)
            self._rows_lay.addWidget(empty_w); return

        for f in factures[:200]:
            self._rows_lay.addWidget(self._make_row(f))

    def _make_row(self, f: dict) -> QFrame:
        row = QFrame()
        row.setFixedHeight(44)
        row.setStyleSheet(
            f"QFrame{{background:transparent;border-radius:8px;}}"
            f"QFrame:hover{{background:{C['surf_low']};}}"
        )
        rl = QHBoxLayout(row); rl.setContentsMargins(8,0,8,0); rl.setSpacing(8)

        def cell(text, bold=False, color=None):
            l = QLabel(str(text) if text else "—")
            l.setStyleSheet(
                f"font-size:12px;font-weight:{'600'if bold else'400'};"
                f"color:{color or C['on_surface']};background:transparent;"
            )
            l.setMaximumWidth(300); return l

        fourn = f.get("fournisseur","") or f.get("nom_fichier","—")
        rl.addWidget(cell(fourn[:28], bold=True), 3)
        rl.addWidget(cell(f.get("date_facture","—")), 1)
        rl.addWidget(cell(f"{f.get('montant_ttc',0):,.0f} FCFA", bold=True, color=C["primary"]), 2)
        rl.addWidget(cell(f.get("categorie","—")), 1)
        # Type entrante/sortante
        typ = f.get("type_facture","")
        typ_color = C["error"] if typ == "entrante" else C["secondary"]
        typ_lbl = "Charge" if typ == "entrante" else ("Produit" if typ == "sortante" else "—")
        rl.addWidget(cell(typ_lbl, color=typ_color), 1)
        # Statut
        st = f.get("statut","")
        bst = "success" if st in ("traite","valide") else "error" if st=="erreur" else "neutral"
        lbl_map = {"traite":"Traite","valide":"Valide","erreur":"Erreur",
                   "en_attente":"Attente","en_cours":"En cours"}
        rl.addWidget(Badge(lbl_map.get(st, st), bst), 1)
        return row

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)
