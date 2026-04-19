"""
services/detector.py — Détection automatique ENTRANTE / SORTANTE
Analyse le texte d'une facture pour déterminer son sens.
"""
import re

# ── Mots-clés SORTANTE (émise PAR l'entreprise VERS un client) ────────────
KW_SORTANTE = [
    "facture émise", "facturé à", "client", "destinataire",
    "votre référence", "à l'attention de", "à l'ordre de",
    "vendu à", "livré à", "expédié à", "bon de commande client",
    "devis accepté", "prestation fournie à", "honoraires facturés à",
    "notre client", "votre entreprise", "votre société",
    "invoice to", "bill to", "sold to", "ship to",
]

# ── Mots-clés ENTRANTE (reçue D'un fournisseur) ───────────────────────────
KW_ENTRANTE = [
    "facture fournisseur", "facturé par", "fournisseur", "émetteur",
    "nous vous facturons", "veuillez régler", "règlement à",
    "bon de livraison", "bon de commande", "notre référence",
    "notre société", "notre entreprise", "prestation réalisée par",
    "facture de", "invoice from", "from:", "remise par",
    "à payer", "net à payer", "montant dû",
    "orange", "mtn", "moov", "cie", "senelec", "sodeci",
    "eneo", "canal+", "total petroleum", "shell",
]

# ── Patterns structurels ──────────────────────────────────────────────────
RE_EMIS_PAR   = re.compile(
    r"(?:émis?\s*par|issued\s*by|de\s*:)\s*(.{3,60})", re.I
)
RE_EMIS_A     = re.compile(
    r"(?:émis?\s*[àa]|factur[eé]\s*[àa]|bill(?:ed)?\s*to|to\s*:)\s*(.{3,60})", re.I
)
RE_TVA_EMETTEUR = re.compile(
    r"(?:notre|mon)\s+n[°o]?\s*(?:tva|siret|rcs|ife)", re.I
)


def detect_type(texte: str, nom_fichier: str = "") -> dict:
    """
    Retourne :
    {
        "type":       "entrante" | "sortante" | "inconnue",
        "confiance":  0.0 - 1.0,
        "raison":     "explication courte",
        "emetteur":   "nom extrait",
        "recepteur":  "nom extrait",
    }
    """
    t = texte.lower()
    score_entrant  = 0
    score_sortant  = 0
    raisons        = []

    # ── Score mots-clés ───────────────────────────────────────────────────
    for kw in KW_ENTRANTE:
        if kw in t:
            score_entrant += 1

    for kw in KW_SORTANTE:
        if kw in t:
            score_sortant += 1

    # ── Score nom de fichier ──────────────────────────────────────────────
    fn = nom_fichier.lower()
    if any(w in fn for w in ["entrant", "recu", "reçu", "fournisseur", "achat"]):
        score_entrant += 3
        raisons.append("nom de fichier suggère entrant")
    if any(w in fn for w in ["sortant", "emis", "émis", "client", "vente"]):
        score_sortant += 3
        raisons.append("nom de fichier suggère sortant")

    # ── Extraire émetteur / récepteur ─────────────────────────────────────
    emetteur  = ""
    recepteur = ""

    m = RE_EMIS_PAR.search(texte)
    if m:
        emetteur = m.group(1).strip()[:80]
        score_entrant += 2

    m = RE_EMIS_A.search(texte)
    if m:
        recepteur = m.group(1).strip()[:80]

    # ── Si émetteur trouvé → facture entrante (reçue DE quelqu'un) ────────
    if emetteur:
        score_entrant += 1
        raisons.append(f"émetteur identifié: {emetteur[:30]}")

    # ── Déterminer le type ────────────────────────────────────────────────
    total = score_entrant + score_sortant or 1
    if score_entrant > score_sortant:
        typ      = "entrante"
        confiance = min(score_entrant / total, 0.95)
        raisons.append(f"score entrant {score_entrant} > sortant {score_sortant}")
    elif score_sortant > score_entrant:
        typ       = "sortante"
        confiance = min(score_sortant / total, 0.95)
        raisons.append(f"score sortant {score_sortant} > entrant {score_entrant}")
    else:
        # Égalité → entrante par défaut (cas le plus fréquent)
        typ       = "entrante"
        confiance = 0.45
        raisons.append("score égal → entrante par défaut")

    return {
        "type":      typ,
        "confiance": round(confiance, 2),
        "raison":    " · ".join(raisons)[:200],
        "emetteur":  emetteur,
        "recepteur": recepteur,
    }


def check_year_coherence(date_str: str, expected_year: int) -> dict:
    """
    Vérifie que la date de la facture correspond à l'année attendue.
    Retourne {"ok": bool, "annee_facture": int|None, "message": str}
    """
    if not date_str or not expected_year:
        return {"ok": True, "annee_facture": None,
                "message": "Aucune vérification d'année effectuée."}

    # Chercher l'année dans la date (formats JJ/MM/AAAA, AAAA-MM-JJ, etc.)
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", date_str)
    if not years:
        return {"ok": True, "annee_facture": None,
                "message": "Année non détectable dans la date."}

    annee = int(years[0])
    if annee == expected_year:
        return {"ok": True, "annee_facture": annee,
                "message": f"Facture de {annee} ✓"}
    else:
        return {
            "ok":            False,
            "annee_facture": annee,
            "message":       (
                f"⚠ Facture de {annee} mais année sélectionnée : "
                f"{expected_year}"
            )
        }
