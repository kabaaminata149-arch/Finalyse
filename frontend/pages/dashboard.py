
from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from theme import C, PrimaryButton, SecondaryButton, SectionTitle, SubTitle, StatCard, Badge, Divider, shadow


class _DashWorker(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)
    def run(self):
        try:
            from api_client import api
            self.done.emit(api.dashboard())
        except Exception as e:
            self.error.emit(str(e))


class _AnalyseWorker(QThread):
    done  = pyqtSignal(dict, list)
    error = pyqtSignal(str)
    def run(self):
        try:
            from api_client import api
            s = api.analyse_stats()
            a = api.anomalies().get("factures", [])
            self.done.emit(s, a)
        except Exception as e:
            self.error.emit(str(e))


class DashboardPage(QScrollArea):
    navigate_to = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive = True
        self._ws    = []
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"background:{C['surface']};")

        c = QWidget(); c.setStyleSheet(f"background:{C['surface']};")
        root = QVBoxLayout(c)
        root.setContentsMargins(32, 32, 32, 32); root.setSpacing(28)

        # ── En-tête ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(4)
        col.addWidget(SectionTitle("Tableau de Bord"))
        col.addWidget(SubTitle("Vue d'ensemble de votre activité financière"))
        hdr.addLayout(col); hdr.addStretch()
        ref = SecondaryButton("Actualiser"); ref.clicked.connect(self._load)
        hdr.addWidget(ref)
        btn = PrimaryButton("Importer des factures")
        btn.clicked.connect(lambda: self.navigate_to.emit(1))
        shadow(btn, blur=14, y=4, color=C["primary"], alpha=30)
        hdr.addWidget(btn)
        root.addLayout(hdr)

        # ── KPIs ──────────────────────────────────────────────────────────
        grid = QHBoxLayout(); grid.setSpacing(16)
        self._kpis: list[StatCard] = []
        for i, (icon, label, val) in enumerate([
            ("FCFA", "Dépenses Totales", "— FCFA"),
            ("DOC",  "Factures",         "—"),
            ("ERR",  "Anomalies",        "—"),
            ("OK",   "Traitées",         "—"),
        ]):
            card = StatCard(icon, label, val)
            self._kpis.append(card); grid.addWidget(card, 1)
        root.addLayout(grid)

        # ── Transactions récentes ─────────────────────────────────────────
        self._tx_card = self._make_card("Transactions Récentes")
        root.addWidget(self._tx_card)

        # ── Séparateur Analyse ────────────────────────────────────────────
        sep = QHBoxLayout(); sep.setSpacing(12)
        l1 = QFrame(); l1.setFrameShape(QFrame.Shape.HLine); l1.setStyleSheet(f"color:{C['outline_var']};")
        ls = QLabel("Analyse IA")
        ls.setStyleSheet(f"font-size:13px;font-weight:700;color:{C['on_surf_var']};background:transparent;white-space:nowrap;")
        l2 = QFrame(); l2.setFrameShape(QFrame.Shape.HLine); l2.setStyleSheet(f"color:{C['outline_var']};")
        sep.addWidget(l1, 1); sep.addWidget(ls); sep.addWidget(l2, 1)
        root.addLayout(sep)

        # ── KPIs Analyse ──────────────────────────────────────────────────
        agrid = QHBoxLayout(); agrid.setSpacing(14)
        self._akpis: list[StatCard] = []
        for icon, label, val in [
            ("NB",  "Factures Analysées",  "—"),
            ("ERR", "Anomalies Détectées", "—"),
        ]:
            k = StatCard(icon, label, val)
            self._akpis.append(k); agrid.addWidget(k)
        agrid.addStretch()
        root.addLayout(agrid)

        # ── Split anomalies / détail ──────────────────────────────────────
        split = QHBoxLayout(); split.setSpacing(16)

        self._list_card = QFrame()
        self._list_card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
        shadow(self._list_card, blur=16, y=4, color=C["primary"], alpha=10)
        self._list_lay = QVBoxLayout(self._list_card)
        self._list_lay.setContentsMargins(20, 16, 20, 16); self._list_lay.setSpacing(8)
        t = QLabel("Factures avec Anomalies")
        t.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['on_surface']};background:transparent;")
        self._list_lay.addWidget(t)
        self._empty = QLabel("Aucune anomalie détectée.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f"font-size:13px;color:{C['on_surf_var']};background:transparent;padding:32px 0;")
        self._list_lay.addWidget(self._empty)
        split.addWidget(self._list_card, 3)

        self._detail_card = QFrame()
        self._detail_card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
        shadow(self._detail_card, blur=16, y=4, color=C["primary"], alpha=10)
        self._detail_lay = QVBoxLayout(self._detail_card)
        self._detail_lay.setContentsMargins(20, 16, 20, 16); self._detail_lay.setSpacing(10)
        dt = QLabel("Détails de la Facture")
        dt.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['primary']};background:transparent;")
        self._detail_lay.addWidget(dt)
        ph = QLabel("Sélectionnez une facture\npour voir ses détails.")
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph.setStyleSheet(f"font-size:13px;color:{C['on_surf_var']};background:transparent;padding:24px;")
        self._detail_lay.addWidget(ph); self._detail_lay.addStretch()
        split.addWidget(self._detail_card, 2)
        root.addLayout(split)

        self.setWidget(c)
        self._loading_count = 0   # how many workers are still running
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(400)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_step = 0
        self._load()

    def _make_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background:{C['surf_lowest']};border-radius:14px;border:none;")
        shadow(card, blur=16, y=4, color=C["primary"], alpha=10)
        lay = QVBoxLayout(card); lay.setContentsMargins(20, 16, 20, 16)
        t = QLabel(title)
        t.setStyleSheet(f"font-size:14px;font-weight:700;color:{C['on_surface']};background:transparent;")
        lay.addWidget(t)
        return card

    def _load(self):
        if not self._alive: return
        self._set_loading(True)
        w1 = _DashWorker(); w1.done.connect(self._on_dash); w1.error.connect(lambda e: self._set_loading(False))
        self._ws.append(w1); w1.start()
        w2 = _AnalyseWorker(); w2.done.connect(self._on_analyse); w2.error.connect(lambda e: self._set_loading(False))
        self._ws.append(w2); w2.start()

    @pyqtSlot(dict)
    def _on_dash(self, stats: dict):
        if not self._alive: return
        self._set_loading(False)
        tot = stats.get("totaux", {})
        for card, val in zip(self._kpis, [
            f"{tot.get('total_ttc', 0):,.0f} FCFA",
            str(tot.get("nb_total", 0)),
            str(stats.get("nb_anomalies_total", stats.get("nb_anomalies", 0))),
            str(tot.get("nb_traites", 0)),
        ]):
            card.set_value(val)
        self._draw_transactions(stats.get("dernieres", []))

    @pyqtSlot(dict, list)
    def _on_analyse(self, stats: dict, anomalies: list):
        if not self._alive: return
        self._set_loading(False)
        for card, val in zip(self._akpis, [
            str(stats.get("nb_traites", 0)),
            str(stats.get("nb_anomalies", 0)),
        ]):
            card.set_value(val)

        while self._list_lay.count() > 1:
            it = self._list_lay.takeAt(1)
            if it:
                w = it.widget()
                if w and w is not self._empty:
                    try: w.deleteLater()
                    except RuntimeError: pass

        if not anomalies:
            self._list_lay.addWidget(self._empty); self._empty.show()
        else:
            self._empty.setParent(None); self._empty.hide()
            for f in anomalies: self._list_lay.addWidget(self._make_row(f))
            self._list_lay.addStretch()

    def _draw_transactions(self, factures: list):
        if not self._alive: return
        lay = self._tx_card.layout()
        while lay.count() > 1:
            it = lay.takeAt(1)
            if it and it.widget():
                try: it.widget().deleteLater()
                except RuntimeError: pass

        if not factures:
            empty = QWidget()
            el = QVBoxLayout(empty); el.setAlignment(Qt.AlignmentFlag.AlignCenter); el.setSpacing(6)
            icon = QLabel("📄")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet("font-size:32px;background:transparent;")
            el.addWidget(icon)
            lbl = QLabel("Aucune transaction pour l'instant.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:13px;font-weight:600;color:{C['on_surf_var']};background:transparent;")
            el.addWidget(lbl)
            hint = QLabel("Importez vos premières factures pour commencer.")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(f"font-size:12px;color:{C['outline']};background:transparent;")
            el.addWidget(hint)
            lay.addWidget(empty)
            return

        for f in factures[:5]:
            lay.addWidget(self._tx_row(f))
        voir = QPushButton("Voir tout l'historique")
        voir.setStyleSheet(f"background:transparent;border:none;color:{C['primary']};font-size:12px;font-weight:600;")
        voir.setCursor(Qt.CursorShape.PointingHandCursor)
        voir.clicked.connect(lambda: self.navigate_to.emit(3))
        lay.addWidget(voir, alignment=Qt.AlignmentFlag.AlignRight)

    def _make_row(self, f: dict) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame{{background:{C['surf_low']};border-radius:10px;border:none;}}"
            f"QFrame:hover{{background:{C['primary_fixed']};}}"
        )
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QHBoxLayout(row); rl.setContentsMargins(12, 10, 12, 10); rl.setSpacing(10)
        info = QVBoxLayout(); info.setSpacing(2)
        n = QLabel(f.get("fournisseur", "—") or f.get("nom_fichier", "—"))
        n.setStyleSheet(f"font-size:12px;font-weight:600;color:{C['on_surface']};background:transparent;")
        r = QLabel(f.get("ref_facture", "") or "—")
        r.setStyleSheet(f"font-size:10px;color:{C['on_surf_var']};background:transparent;")
        info.addWidget(n); info.addWidget(r); rl.addLayout(info); rl.addStretch()
        nb_a = len(f.get("anomalies", []))
        rl.addWidget(Badge(f"{nb_a} anomalie(s)", "error" if nb_a > 0 else "success"))
        row.mousePressEvent = lambda e, ff=f: self._show_detail(ff)
        return row

    def _show_detail(self, f: dict):
        if not self._alive: return

        # Supprimer l'ancien contenu (tout sauf le titre index 0)
        # On utilise un widget conteneur pour éviter les layouts fantômes
        while self._detail_lay.count() > 1:
            it = self._detail_lay.takeAt(1)
            if it and it.widget():
                try: it.widget().deleteLater()
                except RuntimeError: pass

        # Conteneur scrollable pour le détail
        from PyQt6.QtWidgets import QScrollArea as _SA
        scroll = _SA()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none;")

        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(inner); lay.setContentsMargins(0, 0, 8, 0); lay.setSpacing(8)

        def add_row(lbl, val, color=None):
            r = QHBoxLayout()
            l = QLabel(lbl); l.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
            v = QLabel(str(val)); v.setStyleSheet(f"font-size:12px;font-weight:600;color:{color or C['on_surface']};background:transparent;")
            r.addWidget(l); r.addStretch(); r.addWidget(v)
            lay.addLayout(r)

        add_row("Fournisseur", f.get("fournisseur", "—"))
        add_row("Date",        f.get("date_facture", "—"))
        add_row("Référence",   f.get("ref_facture", "—"))
        add_row("Montant HT",  f"{f.get('montant_ht', 0):,.0f} FCFA")
        add_row("TVA",         f"{f.get('tva', 0):,.0f} FCFA",
                C["error"] if f.get("tva", 0) == 0 else None)
        add_row("Montant TTC", f"{f.get('montant_ttc', 0):,.0f} FCFA")
        add_row("Confiance IA",f"{f.get('confiance', 0):.0%}")
        lay.addWidget(Divider())

        anom_lbl = QLabel("ANOMALIES DÉTECTÉES")
        anom_lbl.setStyleSheet(f"font-size:9px;font-weight:700;letter-spacing:1.5px;color:{C['error']};background:transparent;")
        lay.addWidget(anom_lbl)

        anomalies = f.get("anomalies", [])
        if not anomalies:
            na = QLabel("Aucune anomalie.")
            na.setStyleSheet(f"font-size:12px;color:{C['on_surf_var']};background:transparent;")
            lay.addWidget(na)
        else:
            for a in anomalies:
                card = QFrame()
                card.setStyleSheet(f"background:{C['err_container']};border-radius:8px;border:none;")
                cl = QVBoxLayout(card); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(4)
                title = QLabel(a.get("titre", "—"))
                title.setStyleSheet(f"font-size:12px;font-weight:700;color:{C['error']};background:transparent;")
                desc = QLabel(a.get("desc", a.get("description", "")))
                desc.setWordWrap(True)
                desc.setStyleSheet(f"font-size:11px;color:{C['on_surface']};background:transparent;")
                cl.addWidget(title); cl.addWidget(desc)
                lay.addWidget(card)

        lay.addStretch()
        scroll.setWidget(inner)
        self._detail_lay.addWidget(scroll)

    @staticmethod
    def _tx_row(f: dict) -> QFrame:
        row = QFrame()
        row.setStyleSheet(f"QFrame{{background:transparent;border-radius:8px;}}QFrame:hover{{background:{C['surf_low']};}}")
        rl = QHBoxLayout(row); rl.setContentsMargins(8, 8, 8, 8); rl.setSpacing(10)
        info = QVBoxLayout(); info.setSpacing(2)
        n = QLabel(f.get("fournisseur", "—") or f.get("nom_fichier", "—"))
        n.setStyleSheet(f"font-size:12px;font-weight:600;color:{C['on_surface']};background:transparent;")
        r = QLabel(f.get("ref_facture", "") or f.get("date_facture", "") or "—")
        r.setStyleSheet(f"font-size:10px;color:{C['on_surf_var']};background:transparent;")
        info.addWidget(n); info.addWidget(r); rl.addLayout(info); rl.addStretch()
        amt = QLabel(f"{f.get('montant_ttc', 0):,.0f} FCFA")
        amt.setStyleSheet(f"font-size:12px;font-weight:700;color:{C['on_surface']};background:transparent;")
        rl.addWidget(amt)
        st = f.get("statut", "")
        bst = "success" if st in ("traite", "valide") else "error" if st == "erreur" else "neutral"
        lbl_map = {"traite": "Traité", "valide": "Validé", "erreur": "Erreur", "en_attente": "En attente", "en_cours": "En cours"}
        rl.addWidget(Badge(lbl_map.get(st, st), bst))
        return row

    def _set_loading(self, loading: bool) -> None:
        """Show animated dots on KPI cards while data is loading."""
        if not self._alive:
            return
        if loading:
            self._loading_count += 1
            if self._loading_count == 1:
                self._dot_step = 0
                for card in self._kpis + self._akpis:
                    card.set_value(".")
                self._dot_timer.start()
        else:
            self._loading_count = max(0, self._loading_count - 1)
            if self._loading_count == 0:
                self._dot_timer.stop()

    def _tick_dots(self) -> None:
        """Cycle dots animation: . → .. → ... → ."""
        if not self._alive:
            self._dot_timer.stop()
            return
        self._dot_step = (self._dot_step + 1) % 3
        dots = "." * (self._dot_step + 1)
        for card in self._kpis + self._akpis:
            card.set_value(dots)

    def refresh(self):
        if self._alive: self._load()

    def closeEvent(self, e):
        self._alive = False; super().closeEvent(e)
