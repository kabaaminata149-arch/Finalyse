"""
export_service.py — Finalyse PDF/CSV Report Generator
Generates professional PDF reports using ReportLab for invoice analysis.
"""

import os
import csv
import io
from datetime import datetime

from config import EXPORT_DIR

# ── Color palette ──────────────────────────────────────────────────────────────
PRIMARY   = "#000666"   # deep blue
SECONDARY = "#1b6d24"   # green
ERROR_C   = "#b3261e"   # red
WARN_C    = "#f57c00"   # orange

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fcfa(val):
    """Format a number as FCFA with thousands separator."""
    try:
        return f"{int(float(val)):,} FCFA".replace(",", " ")
    except (ValueError, TypeError):
        return "0 FCFA"


def _hex(h):
    """Convert hex color string to ReportLab Color."""
    from reportlab.lib.colors import HexColor
    return HexColor(h)


def _action_recommandee(titre: str) -> str:
    """Return a recommended action string based on anomaly title keywords."""
    t = (titre or "").lower()
    if any(k in t for k in ("doublon", "duplicate")):
        return "Vérifier et supprimer les doublons dans le système comptable."
    if any(k in t for k in ("montant", "incohérent", "incorrect")):
        return "Contacter le fournisseur pour correction et émission d'un avoir."
    if any(k in t for k in ("tva", "taxe")):
        return "Soumettre à la direction financière pour validation fiscale."
    if any(k in t for k in ("date", "échéance", "expir")):
        return "Relancer le fournisseur et mettre à jour les délais de paiement."
    if any(k in t for k in ("manquant", "absent", "incomplet")):
        return "Demander les documents manquants au fournisseur."
    if any(k in t for k in ("fraude", "suspect")):
        return "Escalader immédiatement au responsable conformité."
    return "Examiner manuellement et prendre les mesures appropriées."


# ── CSV Export ─────────────────────────────────────────────────────────────────

def export_csv(factures: list, uid: int) -> str:
    """Generate a CSV file for the given invoices and return the file path."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORT_DIR, f"export_{uid}_{ts}.csv")

    fieldnames = [
        "id", "fournisseur", "reference", "date_facture",
        "montant_ht", "tva", "montant_ttc", "categorie", "statut", "confiance"
    ]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for fac in factures:
            writer.writerow({
                "id":           fac.get("id", ""),
                "fournisseur":  fac.get("fournisseur", ""),
                "reference":    fac.get("reference", ""),
                "date_facture": fac.get("date_facture", ""),
                "montant_ht":   fac.get("montant_ht", 0),
                "tva":          fac.get("tva", 0),
                "montant_ttc":  fac.get("montant_ttc", 0),
                "categorie":    fac.get("categorie", ""),
                "statut":       fac.get("statut", ""),
                "confiance":    fac.get("confiance", ""),
            })
    return path


# ── AI Text Generators ─────────────────────────────────────────────────────────

def _gen_resume(dep, rec, solde, nb_t, nb_total, nb_anom, top_fourn,
                top_cat, top_cat_pct, periode) -> str:
    """Generate executive summary text via DeepSeek API or fallback template."""
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        load_dotenv(env_path, override=True)
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise ValueError("No DEEPSEEK_API_KEY")

        import urllib.request, json as _json
        prompt = (
            f"Rédige un résumé exécutif professionnel en français (5-7 phrases) pour un rapport "
            f"d'analyse de factures Finalyse. Période: {periode}. "
            f"Dépenses TTC: {_fcfa(dep)}. Recettes TTC: {_fcfa(rec)}. Solde net: {_fcfa(solde)}. "
            f"Factures traitées: {nb_t}/{nb_total}. Anomalies: {nb_anom}. "
            f"Fournisseur principal: {top_fourn}. Catégorie dominante: {top_cat} ({top_cat_pct:.1f}%). "
            "Sois concis, analytique et orienté décision."
        )
        payload = _json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 400,
            "temperature": 0.4,
        }).encode()
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        pass

    # Fallback template
    signe = "excédentaire" if solde >= 0 else "déficitaire"
    return (
        f"Ce rapport présente l'analyse financière des factures pour la période {periode}. "
        f"Sur {nb_total} documents soumis, {nb_t} ont été traités avec succès par le système Finalyse. "
        f"Les dépenses totales TTC s'élèvent à {_fcfa(dep)}, tandis que les recettes atteignent {_fcfa(rec)}, "
        f"dégageant un solde net {signe} de {_fcfa(abs(solde))}. "
        f"Le fournisseur principal est {top_fourn or 'N/A'}, et la catégorie dominante est "
        f"{top_cat or 'N/A'} représentant {top_cat_pct:.1f}% des dépenses. "
        f"{nb_anom} anomalie(s) ont été détectées et nécessitent une attention particulière. "
        "Ce rapport a été généré automatiquement par l'intelligence artificielle Finalyse."
    )


def _gen_bilan_ia(dep, rec, solde, nb_t, nb_anom, top_fourn,
                  top_cat, top_cat_pct, conf_moy, periode) -> str:
    """Generate AI assessment text via DeepSeek API or fallback template."""
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        load_dotenv(env_path, override=True)
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise ValueError("No DEEPSEEK_API_KEY")

        import urllib.request, json as _json
        prompt = (
            f"Rédige un bilan analytique IA détaillé en français (8-10 phrases) pour un rapport "
            f"Finalyse. Période: {periode}. Dépenses: {_fcfa(dep)}. Recettes: {_fcfa(rec)}. "
            f"Solde: {_fcfa(solde)}. Factures traitées: {nb_t}. Anomalies: {nb_anom}. "
            f"Fournisseur principal: {top_fourn}. Catégorie dominante: {top_cat} ({top_cat_pct:.1f}%). "
            f"Confiance IA moyenne: {conf_moy:.1f}%. "
            "Inclure: performance IA, risques identifiés, recommandations stratégiques, perspectives."
        )
        payload = _json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600,
            "temperature": 0.4,
        }).encode()
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        pass

    # Fallback template
    perf = "excellente" if conf_moy >= 85 else ("bonne" if conf_moy >= 70 else "acceptable")
    return (
        f"Le système d'intelligence artificielle Finalyse a démontré une performance {perf} "
        f"sur la période {periode}, avec un taux de confiance moyen de {conf_moy:.1f}%. "
        f"L'analyse automatisée a permis de traiter {nb_t} facture(s) et d'identifier "
        f"{nb_anom} anomalie(s) potentielle(s) nécessitant une revue humaine. "
        f"Les dépenses totales de {_fcfa(dep)} sont principalement concentrées dans la catégorie "
        f"{top_cat or 'N/A'} ({top_cat_pct:.1f}%), ce qui suggère une opportunité d'optimisation "
        "des achats dans ce segment. "
        f"Le fournisseur {top_fourn or 'N/A'} représente le partenaire commercial le plus actif "
        "sur la période analysée. "
        f"Le solde net de {_fcfa(solde)} reflète la position financière globale de l'entreprise. "
        "Il est recommandé de maintenir une surveillance continue des anomalies détectées et "
        "d'engager des actions correctives dans les meilleurs délais. "
        "La fiabilité du modèle IA peut être améliorée en enrichissant la base de données "
        "de référence avec des factures validées supplémentaires."
    )


# ── Fallback plain-text export ─────────────────────────────────────────────────

def _pdf_fallback(factures: list, uid: int, periode: str) -> str:
    """Simple text file fallback when ReportLab is not available."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORT_DIR, f"rapport_{uid}_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("       FINALYSE — RAPPORT D'ANALYSE DES FACTURES\n")
        f.write("=" * 60 + "\n")
        f.write(f"Période  : {periode}\n")
        f.write(f"Généré le: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")
        f.write(f"{'#':<4} {'Fournisseur':<25} {'Date':<12} {'TTC':>15} {'Statut':<12}\n")
        f.write("-" * 70 + "\n")
        for i, fac in enumerate(factures, 1):
            f.write(
                f"{i:<4} {str(fac.get('fournisseur',''))[:24]:<25} "
                f"{str(fac.get('date_facture','')):<12} "
                f"{_fcfa(fac.get('montant_ttc',0)):>15} "
                f"{str(fac.get('statut','')):<12}\n"
            )
        f.write("\n[ReportLab non disponible — rapport texte généré en remplacement]\n")
    return path


# ── Main PDF builder ───────────────────────────────────────────────────────────

def _build_pdf(factures: list, uid: int, periode: str,
               stats: dict, entreprise: str) -> str:
    """Build a full professional PDF report using ReportLab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white, black, Color
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, KeepTogether
    )

    os.makedirs(EXPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORT_DIR, f"rapport_{uid}_{ts}.pdf")

    W, H = A4
    COL_PRIMARY   = HexColor(PRIMARY)
    COL_SECONDARY = HexColor(SECONDARY)
    COL_ERROR     = HexColor(ERROR_C)
    COL_WARN      = HexColor(WARN_C)
    COL_LIGHT     = HexColor("#e8eaf6")
    COL_LIGHT2    = HexColor("#f1f8e9")
    COL_GREY      = HexColor("#757575")
    COL_DARKGREY  = HexColor("#424242")

    # ── Compute stats ──────────────────────────────────────────────────────────
    traitees   = [f for f in factures if f.get("statut") not in ("rejeté", "non_reconnu", "rejected")]
    rejetees   = [f for f in factures if f.get("statut") in ("rejeté", "non_reconnu", "rejected")]
    # Anomalies = factures traitées avec le champ anomalies non vide
    anomalies  = [f for f in traitees
                  if f.get("anomalies") and f["anomalies"] not in ([], "[]", "", None)]

    dep = sum(float(f.get("montant_ttc", 0) or 0)
              for f in traitees if float(f.get("montant_ttc", 0) or 0) < 0
              or f.get("type") in ("sortante", "dépense"))
    rec = sum(float(f.get("montant_ttc", 0) or 0)
              for f in traitees if float(f.get("montant_ttc", 0) or 0) >= 0
              and f.get("type") not in ("sortante", "dépense"))

    # Use stats dict if provided
    dep       = abs(stats.get("total_depenses", dep))
    rec       = abs(stats.get("total_recettes", rec))
    solde     = stats.get("solde_net", rec - dep)
    total_ht  = stats.get("total_ht",  sum(float(f.get("montant_ht", 0) or 0) for f in traitees))
    total_tva = stats.get("total_tva", sum(float(f.get("tva", 0) or 0) for f in traitees))
    nb_total  = len(factures)
    nb_t      = stats.get("nb_traitees", len(traitees))
    nb_anom   = stats.get("nb_anomalies", len(anomalies))

    # Top fournisseur
    fourn_count: dict = {}
    for f in traitees:
        fn = f.get("fournisseur") or "Inconnu"
        fourn_count[fn] = fourn_count.get(fn, 0) + float(f.get("montant_ttc", 0) or 0)
    top_fourn = max(fourn_count, key=fourn_count.get) if fourn_count else "N/A"

    # Top catégorie
    cat_count: dict = {}
    for f in traitees:
        c = f.get("categorie") or "Autre"
        cat_count[c] = cat_count.get(c, 0) + float(f.get("montant_ttc", 0) or 0)
    top_cat     = max(cat_count, key=cat_count.get) if cat_count else "N/A"
    top_cat_ttc = cat_count.get(top_cat, 0)
    top_cat_pct = (top_cat_ttc / dep * 100) if dep > 0 else 0

    # Confiance IA moyenne
    confs = [float(f.get("confiance", 0) or 0) for f in traitees if f.get("confiance")]
    conf_moy = (sum(confs) / len(confs)) if confs else 0.0

    # Évolution mensuelle (6 derniers mois)
    from collections import defaultdict
    monthly: dict = defaultdict(float)
    for f in traitees:
        d = f.get("date_facture", "")
        if d and len(str(d)) >= 7:
            key = str(d)[:7]
            monthly[key] += float(f.get("montant_ttc", 0) or 0)
    sorted_months = sorted(monthly.keys())[-6:]

    # ── Styles ─────────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, **kw)

    S_TITLE    = ps("S_TITLE",    fontSize=26, textColor=white,      alignment=TA_CENTER,
                    fontName="Helvetica-Bold", leading=32)
    S_SUBTITLE = ps("S_SUBTITLE", fontSize=13, textColor=HexColor("#c5cae9"), alignment=TA_CENTER,
                    fontName="Helvetica", leading=18)
    S_COVER_CO = ps("S_COVER_CO", fontSize=11, textColor=white,      alignment=TA_CENTER,
                    fontName="Helvetica-Oblique", leading=16)
    S_H1       = ps("S_H1",       fontSize=14, textColor=COL_PRIMARY, fontName="Helvetica-Bold",
                    leading=20, spaceBefore=14, spaceAfter=6)
    S_H2       = ps("S_H2",       fontSize=11, textColor=COL_SECONDARY, fontName="Helvetica-Bold",
                    leading=16, spaceBefore=10, spaceAfter=4)
    S_BODY     = ps("S_BODY",     fontSize=9,  textColor=COL_DARKGREY, fontName="Helvetica",
                    leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
    S_SMALL    = ps("S_SMALL",    fontSize=8,  textColor=COL_GREY,    fontName="Helvetica",
                    leading=12)
    S_CENTER   = ps("S_CENTER",   fontSize=9,  textColor=COL_DARKGREY, fontName="Helvetica",
                    leading=13, alignment=TA_CENTER)
    S_BOLD     = ps("S_BOLD",     fontSize=9,  textColor=COL_DARKGREY, fontName="Helvetica-Bold",
                    leading=13)
    S_LABEL    = ps("S_LABEL",    fontSize=8,  textColor=COL_GREY,    fontName="Helvetica",
                    leading=11, alignment=TA_CENTER)

    # ── Header / Footer callbacks ──────────────────────────────────────────────
    def _on_page(canvas, doc):
        """Draw header and footer on every page except the cover (page 1)."""
        if doc.page == 1:
            return
        canvas.saveState()
        # Header bar
        canvas.setFillColor(COL_PRIMARY)
        canvas.rect(0, H - 1.2 * cm, W, 1.2 * cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(1.5 * cm, H - 0.85 * cm, "FINALYSE")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(W - 1.5 * cm, H - 0.85 * cm, f"Période : {periode}")
        # Footer bar
        canvas.setFillColor(COL_LIGHT)
        canvas.rect(0, 0, W, 0.9 * cm, fill=1, stroke=0)
        canvas.setFillColor(COL_GREY)
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(W / 2, 0.3 * cm, f"Page {doc.page}  •  Rapport généré par Finalyse")
        canvas.restoreState()

    # ── Cover page — dessinée via onFirstPage, pas un Flowable ──────────────
    def _draw_cover(canvas, doc):
        """Page de couverture dessinée directement sur le canvas."""
        canvas.saveState()
        # Fond bleu
        canvas.setFillColor(COL_PRIMARY)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        # Bande verte en bas
        canvas.setFillColor(COL_SECONDARY)
        canvas.rect(0, 0, W, 2.5 * cm, fill=1, stroke=0)
        # Ligne accent haut
        canvas.setFillColor(HexColor("#3949ab"))
        canvas.rect(0, H - 0.4 * cm, W, 0.4 * cm, fill=1, stroke=0)
        # Brand
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 36)
        canvas.drawCentredString(W / 2, H - 5 * cm, "FINALYSE")
        canvas.setFillColor(HexColor("#c5cae9"))
        canvas.setFont("Helvetica", 12)
        canvas.drawCentredString(W / 2, H - 5.9 * cm,
                                 "Systeme d'Analyse Intelligente des Factures")
        # Divider
        canvas.setStrokeColor(HexColor("#3949ab"))
        canvas.setLineWidth(1.5)
        canvas.line(3 * cm, H - 6.6 * cm, W - 3 * cm, H - 6.6 * cm)
        # Titre principal
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 22)
        canvas.drawCentredString(W / 2, H - 8.5 * cm, "Rapport d'Analyse des Factures")
        # Période
        canvas.setFillColor(HexColor("#c5cae9"))
        canvas.setFont("Helvetica", 13)
        canvas.drawCentredString(W / 2, H - 9.5 * cm, f"Periode : {periode}")
        # Date
        canvas.setFont("Helvetica", 11)
        canvas.drawCentredString(W / 2, H - 10.3 * cm,
                                 f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}")
        # Entreprise
        if entreprise:
            canvas.setFillColor(white)
            canvas.setFont("Helvetica-Bold", 13)
            canvas.drawCentredString(W / 2, H - 11.5 * cm, entreprise)
        # Bas
        canvas.setFillColor(white)
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(W / 2, 0.9 * cm, "Confidentiel - Usage interne uniquement")
        canvas.restoreState()

    def _on_first_page(canvas, doc):
        _draw_cover(canvas, doc)

    def _on_later_pages(canvas, doc):
        _on_page(canvas, doc)

    # ── Table style helpers ────────────────────────────────────────────────────
    def _tbl_style_base(header_bg=None):
        hbg = header_bg or COL_PRIMARY
        return TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  hbg),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  white),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0),  8),
            ("ALIGN",        (0, 0), (-1, 0),  "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, COL_LIGHT]),
            ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",     (0, 1), (-1, -1), 8),
            ("ALIGN",        (0, 1), (-1, -1), "LEFT"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",         (0, 0), (-1, -1), 0.4, HexColor("#bdbdbd")),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ])

    def _bar(pct, width=80):
        filled = int(pct / 100 * 10)
        return "█" * filled + "░" * (10 - filled) + f"  {pct:.1f}%"

    # ── Build story ────────────────────────────────────────────────────────────
    story = []

    # Page de couverture = dessinée par onFirstPage, on saute juste à la page suivante
    story.append(PageBreak())

    # ── SECTION 1: Résumé Exécutif ─────────────────────────────────────────────
    story.append(Paragraph("1. Résumé Exécutif", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))
    resume_text = _gen_resume(dep, rec, solde, nb_t, nb_total, nb_anom,
                               top_fourn, top_cat, top_cat_pct, periode)
    for para in resume_text.split("\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), S_BODY))
    story.append(Spacer(1, 0.4 * cm))

    # ── SECTION 2: Tableau de Bord Financier ──────────────────────────────────
    story.append(Paragraph("2. Tableau de Bord Financier", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))

    kpi_data = [
        ["Indicateur", "Valeur"],
        ["Dépenses TTC",          _fcfa(dep)],
        ["Recettes TTC",          _fcfa(rec)],
        ["Solde Net",             _fcfa(solde)],
        ["Total HT",              _fcfa(total_ht)],
        ["Total TVA",             _fcfa(total_tva)],
        ["Nombre de factures",    str(nb_total)],
        ["Factures traitées",     str(nb_t)],
        ["Anomalies détectées",   str(nb_anom)],
        ["Fournisseur principal", top_fourn],
        ["Catégorie dominante",   f"{top_cat} ({top_cat_pct:.1f}%)"],
        ["Confiance IA moyenne",  f"{conf_moy:.1f}%"],
    ]
    kpi_tbl = Table(kpi_data, colWidths=[9 * cm, 8 * cm])
    kpi_style = _tbl_style_base()
    # Highlight solde row
    solde_row = 3
    kpi_style.add("TEXTCOLOR", (1, solde_row), (1, solde_row),
                  COL_SECONDARY if solde >= 0 else COL_ERROR)
    kpi_style.add("FONTNAME",  (1, solde_row), (1, solde_row), "Helvetica-Bold")
    kpi_tbl.setStyle(kpi_style)
    story.append(kpi_tbl)
    story.append(Spacer(1, 0.5 * cm))

    # ── SECTION 3: Analyse des Dépenses ───────────────────────────────────────
    story.append(Paragraph("3. Analyse des Dépenses", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))

    # 3.1 Répartition par catégorie
    story.append(Paragraph("3.1 Répartition par Catégorie", S_H2))
    if cat_count:
        cat_sorted = sorted(cat_count.items(), key=lambda x: x[1], reverse=True)
        cat_data = [["Catégorie", "Montant TTC", "Part (%)", "Visualisation"]]
        for cat, amt in cat_sorted:
            pct = (amt / dep * 100) if dep > 0 else 0
            cat_data.append([cat, _fcfa(amt), f"{pct:.1f}%", _bar(pct)])
        cat_tbl = Table(cat_data, colWidths=[4.5 * cm, 4 * cm, 2.5 * cm, 6 * cm])
        cat_tbl.setStyle(_tbl_style_base(COL_SECONDARY))
        story.append(cat_tbl)
    else:
        story.append(Paragraph("Aucune donnée de catégorie disponible.", S_BODY))
    story.append(Spacer(1, 0.4 * cm))

    # 3.2 Évolution mensuelle
    story.append(Paragraph("3.2 Évolution Mensuelle (6 derniers mois)", S_H2))
    if sorted_months:
        max_m = max(monthly[m] for m in sorted_months) or 1
        month_data = [["Mois", "Montant TTC", "Évolution"]]
        for m in sorted_months:
            amt = monthly[m]
            pct = (amt / max_m * 100)
            month_data.append([m, _fcfa(amt), _bar(pct)])
        m_tbl = Table(month_data, colWidths=[3 * cm, 5 * cm, 9 * cm])
        m_tbl.setStyle(_tbl_style_base())
        story.append(m_tbl)
    else:
        story.append(Paragraph("Aucune donnée mensuelle disponible.", S_BODY))
    story.append(Spacer(1, 0.4 * cm))

    # 3.3 Top 5 fournisseurs
    story.append(Paragraph("3.3 Top 5 Fournisseurs", S_H2))
    top5 = sorted(fourn_count.items(), key=lambda x: x[1], reverse=True)[:5]
    if top5:
        t5_data = [["#", "Fournisseur", "Montant TTC", "Part (%)"]]
        total_fourn = sum(v for _, v in top5)
        for i, (fn, amt) in enumerate(top5, 1):
            pct = (amt / dep * 100) if dep > 0 else 0
            t5_data.append([str(i), fn, _fcfa(amt), f"{pct:.1f}%"])
        t5_tbl = Table(t5_data, colWidths=[1 * cm, 7 * cm, 5 * cm, 4 * cm])
        t5_tbl.setStyle(_tbl_style_base())
        story.append(t5_tbl)
    else:
        story.append(Paragraph("Aucun fournisseur identifié.", S_BODY))
    story.append(Spacer(1, 0.4 * cm))

    # 3.4 Entrantes / Sortantes
    story.append(Paragraph("3.4 Factures Entrantes / Sortantes", S_H2))
    entrantes = [f for f in traitees if f.get("type") not in ("sortante", "dépense")]
    sortantes  = [f for f in traitees if f.get("type") in ("sortante", "dépense")]
    ttc_e = sum(float(f.get("montant_ttc", 0) or 0) for f in entrantes)
    ttc_s = sum(float(f.get("montant_ttc", 0) or 0) for f in sortantes)
    es_data = [
        ["Type",       "Nombre", "Montant TTC"],
        ["Entrantes",  str(len(entrantes)), _fcfa(ttc_e)],
        ["Sortantes",  str(len(sortantes)), _fcfa(ttc_s)],
        ["Total",      str(len(traitees)),  _fcfa(ttc_e + ttc_s)],
    ]
    es_tbl = Table(es_data, colWidths=[5 * cm, 4 * cm, 8 * cm])
    es_style = _tbl_style_base()
    es_style.add("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold")
    es_style.add("BACKGROUND", (0, -1), (-1, -1), COL_LIGHT)
    es_tbl.setStyle(es_style)
    story.append(es_tbl)
    story.append(Spacer(1, 0.5 * cm))

    # ── SECTION 4: Détail des Factures ────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("4. Détail des Factures Traitées", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))

    det_data = [["#", "Fournisseur", "Référence", "Date", "HT", "TVA", "TTC", "Catégorie"]]
    # Exclure les factures avec anomalies du tableau principal
    factures_ok = [f for f in traitees
                   if not f.get("anomalies") or f["anomalies"] in ([], "[]", "", None)]
    for i, fac in enumerate(factures_ok, 1):
        det_data.append([
            str(i),
            str(fac.get("fournisseur", ""))[:20],
            str(fac.get("ref_facture", "") or fac.get("reference", ""))[:14],
            str(fac.get("date_facture", ""))[:10],
            _fcfa(fac.get("montant_ht", 0)),
            _fcfa(fac.get("tva", 0)),
            _fcfa(fac.get("montant_ttc", 0)),
            str(fac.get("categorie", ""))[:14],
        ])

    if len(det_data) > 1:
        col_w = [0.7*cm, 3.8*cm, 2.5*cm, 2.2*cm, 2.8*cm, 2.5*cm, 2.8*cm, 2.7*cm]
        det_tbl = Table(det_data, colWidths=col_w, repeatRows=1)
        det_style = _tbl_style_base()
        det_style.add("FONTSIZE", (0, 0), (-1, -1), 7)
        det_tbl.setStyle(det_style)
        story.append(det_tbl)
    else:
        story.append(Paragraph("Aucune facture sans anomalie à afficher.", S_BODY))
    story.append(Spacer(1, 0.5 * cm))

    # ── SECTION 5: Rapport d'Anomalies ────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("5. Rapport d'Anomalies", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))

    if anomalies:
        for fac in anomalies:
            anom_list = fac.get("anomalies", [])
            if isinstance(anom_list, str):
                import json as _j
                try: anom_list = _j.loads(anom_list)
                except Exception: anom_list = []
            for anom in anom_list:
                titre    = anom.get("titre", "Anomalie")
                desc     = anom.get("description", "Aucune description.")
                severite = "ATTENTION"
                sev_color = COL_WARN
                action   = _action_recommandee(titre)

                anom_data = [
                    ["Fournisseur",        str(fac.get("fournisseur", "N/A"))],
                    ["Type d'anomalie",    titre],
                    ["Description",        desc],
                    ["Sévérité",           severite],
                    ["Action recommandée", action],
                ]
                anom_tbl = Table(anom_data, colWidths=[4.5 * cm, 12.5 * cm])
                anom_style = TableStyle([
                    ("BACKGROUND",   (0, 0), (0, -1),  COL_LIGHT),
                    ("FONTNAME",     (0, 0), (0, -1),  "Helvetica-Bold"),
                    ("FONTSIZE",     (0, 0), (-1, -1), 8),
                    ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                    ("GRID",         (0, 0), (-1, -1), 0.4, HexColor("#bdbdbd")),
                    ("TOPPADDING",   (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                    ("LEFTPADDING",  (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TEXTCOLOR",    (1, 3), (1, 3),   sev_color),
                    ("FONTNAME",     (1, 3), (1, 3),   "Helvetica-Bold"),
                ])
                anom_tbl.setStyle(anom_style)
                story.append(KeepTogether([anom_tbl, Spacer(1, 0.3 * cm)]))
    else:
        story.append(Paragraph("Aucune anomalie détectée sur la période analysée.", S_BODY))
    story.append(Spacer(1, 0.4 * cm))

    # ── SECTION 6: Documents Non Reconnus ─────────────────────────────────────
    story.append(Paragraph("6. Documents Non Reconnus", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))

    if rejetees:
        rej_data = [["#", "Nom du fichier", "Date", "Motif"]]
        for i, fac in enumerate(rejetees, 1):
            rej_data.append([
                str(i),
                str(fac.get("nom_fichier") or fac.get("reference", ""))[:35],
                str(fac.get("date_facture", ""))[:10],
                str(fac.get("commentaire") or "Document non reconnu")[:50],
            ])
        rej_tbl = Table(rej_data, colWidths=[1 * cm, 7 * cm, 3 * cm, 6 * cm])
        rej_style = _tbl_style_base(COL_ERROR)
        rej_tbl.setStyle(rej_style)
        story.append(rej_tbl)
    else:
        story.append(Paragraph("Tous les documents soumis ont été reconnus et traités.", S_BODY))
    story.append(Spacer(1, 0.5 * cm))

    # ── SECTION 7: Bilan IA ───────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("7. Bilan IA", S_H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_PRIMARY, spaceAfter=8))
    bilan_text = _gen_bilan_ia(dep, rec, solde, nb_t, nb_anom,
                                top_fourn, top_cat, top_cat_pct, conf_moy, periode)
    for para in bilan_text.split("\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), S_BODY))
    story.append(Spacer(1, 0.4 * cm))

    # ── Build PDF ──────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.5 * cm,
        title=f"Rapport Finalyse — {periode}",
        author="Finalyse",
        subject="Analyse des Factures",
    )
    doc.build(story, onFirstPage=_on_first_page, onLaterPages=_on_later_pages)
    return path


# ── Public entry point ─────────────────────────────────────────────────────────

def export_pdf(factures: list, uid: int, periode: str,
               stats: dict = None, entreprise: str = "") -> str:
    """
    Main entry point for PDF export.
    Tries full ReportLab build first; falls back to plain text on failure.
    """
    if stats is None:
        stats = {}
    try:
        import reportlab  # noqa: F401 — check availability
        return _build_pdf(factures, uid, periode, stats, entreprise)
    except ImportError:
        return _pdf_fallback(factures, uid, periode)
    except Exception as exc:
        # Log and attempt fallback
        print(f"[export_service] PDF build error: {exc}")
        try:
            return _pdf_fallback(factures, uid, periode)
        except Exception:
            raise
