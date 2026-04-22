"""
services/processor.py — Finalyse
Extraction réelle des données de factures :
  1. Regex sur le texte extrait (PDF natif ou OCR)
  2. Ollama si disponible (meilleure précision)
  3. DeepSeek API si internet + clé configurée
"""
import os, re, json, traceback, logging, hashlib
from typing import Optional

import database.db as db

log = logging.getLogger("processor")

OLLAMA_TEXT_TIMEOUT   = float(os.getenv("OLLAMA_TEXT_TIMEOUT",   "90"))
OLLAMA_VISION_TIMEOUT = float(os.getenv("OLLAMA_VISION_TIMEOUT", "120"))

# ── Cache doublon ─────────────────────────────────────────────────────────────
_HASH_CACHE: set = set()

def _hash_facture(data: dict) -> str:
    base = f"{data.get('fournisseur')}-{data.get('montant_ttc')}-{data.get('date_facture')}"
    return hashlib.md5(base.encode()).hexdigest()

def detect_duplicate(fid: int, data: dict) -> bool:
    h = _hash_facture(data)
    if h in _HASH_CACHE:
        return True
    _HASH_CACHE.add(h)
    return False


# ── Lecture PDF ───────────────────────────────────────────────────────────────

def _read_pdf_text(path: str) -> str:
    try:
        import pdfplumber
        out = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:6]:
                t = page.extract_text()
                if t:
                    out.append(t)
        raw = "\n".join(out)
        return _clean_ocr_text(raw)
    except Exception:
        return ""


# ── Lecture Excel ─────────────────────────────────────────────────────────────

def _read_excel_text(path: str) -> str:
    """
    Extrait le texte d'un fichier Excel (.xlsx ou .xls).
    Convertit toutes les cellules non vides en texte brut ligne par ligne.
    Chaque feuille est traitée, les colonnes séparées par des tabulations.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        lines = []
        for sheet in wb.worksheets:
            lines.append(f"[Feuille: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                # Filtrer les lignes entièrement vides
                cells = [str(c).strip() if c is not None else "" for c in row]
                non_empty = [c for c in cells if c]
                if non_empty:
                    lines.append("\t".join(cells))
        wb.close()
        return _clean_ocr_text("\n".join(lines))
    except Exception as e:
        log.warning("[EXCEL] openpyxl failed: %s — tentative xlrd", e)

    # Fallback pour .xls (ancien format)
    try:
        import xlrd
        wb = xlrd.open_workbook(path)
        lines = []
        for sheet in wb.sheets():
            lines.append(f"[Feuille: {sheet.name}]")
            for row_idx in range(sheet.nrows):
                cells = [str(sheet.cell_value(row_idx, col)).strip()
                         for col in range(sheet.ncols)]
                non_empty = [c for c in cells if c]
                if non_empty:
                    lines.append("\t".join(cells))
        return _clean_ocr_text("\n".join(lines))
    except Exception as e:
        log.warning("[EXCEL] xlrd failed: %s", e)

    return ""


def _clean_ocr_text(text: str) -> str:
    """Nettoie le texte OCR — supprime les caractères parasites non-latins."""
    import unicodedata
    lines = []
    for line in text.split("\n"):
        # Ignorer les lignes qui ressemblent à des numéros de série/commande longs
        # (plus de 10 chiffres consécutifs = probablement un code-barres ou N° commande)
        if re.search(r"\d{11,}", line):
            # Garder quand même si la ligne contient "total", "montant", etc.
            if not re.search(r"total|montant|amount|summe|pay|prix", line, re.I):
                continue
        # Garder seulement les lignes avec au moins 40% de caractères latins/chiffres
        latin_chars = sum(1 for c in line if c.isascii() or unicodedata.category(c) in ('Ll','Lu','Nd','Po','Sc','Sm'))
        total_chars = len(line.strip())
        if total_chars == 0:
            continue
        ratio = latin_chars / total_chars
        if ratio >= 0.4 or total_chars < 8:
            cleaned = ""
            for c in line:
                if c.isascii() or c in "€£¥°àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ":
                    cleaned += c
                elif unicodedata.category(c) == 'Nd':
                    cleaned += str(unicodedata.digit(c, c))
                else:
                    cleaned += " "
            lines.append(cleaned.strip())
    return "\n".join(l for l in lines if l)


# ── OCR image — délégué à vision.py (point d'entrée unique) ──────────────────

def _to_image_bytes(path: str) -> bytes:
    from services.vision import to_image_bytes
    return to_image_bytes(path)

def _opencv_boost(image_bytes: bytes) -> bytes:
    from services.vision import opencv_boost
    return opencv_boost(image_bytes)


# ── Extraction par regex ──────────────────────────────────────────────────────

def _extract_regex(texte: str) -> dict:
    """
    Extrait les champs clés d'une facture par regex.
    Fonctionne en français, anglais ET allemand.
    """
    t = texte

    # ── Montant TTC ───────────────────────────────────────────────────────────
    montant_ttc = 0.0
    patterns_ttc = [
        # Français — avec TTC explicite
        r"(?:total\s*(?:ttc|toutes?\s*taxes?|montant\s*d[uû]))\s*[:\-]?\s*([\d\s.,]+)",
        r"(?:net\s*[àa]\s*payer|montant\s*(?:total|ttc|d[uû]))\s*[:\-]?\s*([\d\s.,]+)",
        # Anglais — avec label explicite
        r"(?:total\s*(?:amount|due|payable|invoice\s*total|general|grand\s*total))\s*[:\-]?\s*([\d\s.,]+[€$£e]?)",
        r"(?:amount\s*(?:due|payable|total)|total\s*(?:due|payable)|balance\s*due)\s*[:\-]?\s*([\d\s.,]+)",
        # Allemand
        r"(?:summe|gesamtbetrag|gesamtsumme|rechnungsbetrag|zu\s*zahlen|betrag)\s*[:\-]?\s*([\d\s.,]+[€]?)",
        # Ticket de caisse — "Total" seul sur une ligne suivi du montant
        r"^total\s+([\d]+[.,][\d]{2})\s*[€e$£]?\s*$",
        r"^total\s*[:\-]?\s*([\d]+[.,][\d]{2})\s*[€e$£]?",
        # Montant avec symbole € ou e (OCR) : 22.40 € ou 22,40e
        r"([\d]+[.,][\d]{2})\s*[€e]\s*(?:\n|$)",
        r"([\d]+[.,][\d]{2})\s*€",
        # Five Guys / tickets US : "Elec. Pay. EUR 24.75"
        r"(?:pay(?:ment)?|elec\.?\s*pay\.?)\s*(?:eur|usd|gbp|xof|fcfa)?\s*([\d]+[.,][\d]{2})",
        # Ticket avec "Total (EURO)" ou "Total (EUR)"
        r"total\s*\(?\s*(?:euro?|eur|usd|fcfa|xof)\s*\)?\s*([\d]+[.,][\d]{2})",
    ]
    for pat in patterns_ttc:
        for m in re.finditer(pat, t, re.I | re.M):
            v = _parse_amount(m.group(1))
            if v > montant_ttc:
                montant_ttc = v
        if montant_ttc > 0:
            break

    # Si toujours 0 — chercher le plus grand montant numérique sur une ligne "Total"
    if montant_ttc == 0:
        for line in t.split("\n"):
            line_s = line.strip().lower()
            if line_s.startswith("total") or "total" in line_s[:15]:
                nums = re.findall(r"[\d]+[.,][\d]{2}", line)
                for n in nums:
                    v = _parse_amount(n)
                    # Ignorer les montants > 10000 (probablement faux positif)
                    if 0 < v < 10000 and v > montant_ttc:
                        montant_ttc = v

    # Fallback final — patterns de paiement électronique
    if montant_ttc == 0:
        pay_patterns = [
            # "E1eC. Pay. EUR 24.75" ou "Elec. Pay. EUR 24.75"
            r"(?:e\d*ec|elec|electronic|card|pay(?:ment)?|paid|paye|bancontact)\s*\.?\s*(?:pay\.?)?\s*(?:eur|usd|gbp|€|e)\s*([\d]+[.,][\d]{2})",
            # "EUR 24.75" seul en fin de ligne
            r"(?:eur|usd|gbp)\s+([\d]+[.,][\d]{2})\s*$",
            # "24.75 EUR" 
            r"([\d]+[.,][\d]{2})\s*(?:eur|usd|gbp)\b",
        ]
        for pat in pay_patterns:
            m = re.search(pat, t, re.I | re.M)
            if m:
                v = _parse_amount(m.group(1))
                if 0 < v < 10000:
                    montant_ttc = v
                    break

    # Sanity check — si montant > 50000 et pas de devise FCFA explicite, probablement faux
    if montant_ttc > 50000:
        # Vérifier si c'est vraiment en FCFA ou un faux positif
        has_fcfa = bool(re.search(r"fcfa|xof|cfa", t, re.I))
        if not has_fcfa:
            # Chercher un montant plus petit et raisonnable
            all_amounts = [_parse_amount(m) for m in re.findall(r"[\d]+[.,][\d]{2}", t)]
            reasonable = [v for v in all_amounts if 0.5 < v < 10000]
            if reasonable:
                # Prendre le plus grand montant raisonnable
                montant_ttc = max(reasonable)

    # ── Montant HT ────────────────────────────────────────────────────────────
    montant_ht = 0.0
    patterns_ht = [
        # Français
        r"(?:total\s*(?:ht|hors\s*taxes?)|montant\s*ht|base\s*(?:ht|imposable))\s*[:\-]?\s*([\d\s.,]+)",
        # Anglais
        r"(?:subtotal|sub\s*total|net\s*amount|amount\s*before\s*tax)\s*[:\-]?\s*([\d\s.,]+)",
        # Allemand
        r"(?:nettobetrag|netto|zzgl\.?\s*mwst\.?|ohne\s*mwst\.?)\s*[:\-]?\s*([\d\s.,]+[€]?)",
    ]
    for pat in patterns_ht:
        m = re.search(pat, t, re.I)
        if m:
            v = _parse_amount(m.group(1))
            if v > 0:
                montant_ht = v; break

    # ── TVA ───────────────────────────────────────────────────────────────────
    tva = 0.0
    patterns_tva = [
        # Français
        r"(?:tva|taxe\s*(?:sur\s*la\s*valeur\s*ajout[ée]e?)?)\s*[:\-]?\s*(?:\d+\s*%\s*[:\-]?\s*)?([\d\s.,]+)",
        # Anglais
        r"(?:vat|tax(?:es?)?|gst|hst|sales\s*tax)\s*[:\-]?\s*(?:\d+\s*%\s*[:\-]?\s*)?([\d\s.,]+)",
        # Allemand : MwSt, Mehrwertsteuer
        r"(?:mwst\.?|mehrwertsteuer|ust\.?)\s*(?:\(?\s*[A-Z]\s*\)?\s*)?\d*\s*%?\s*[:\-]?\s*([\d\s.,]+[€]?)",
        r"mwst\s*\([a-z]\)\s*\d+%\s*([\d\s.,]+)",
    ]
    for pat in patterns_tva:
        m = re.search(pat, t, re.I)
        if m:
            v = _parse_amount(m.group(1))
            if v > 0:
                tva = v; break
            if tva > 0:
                break

    # Si on a TTC et HT mais pas TVA → calculer
    if tva == 0 and montant_ttc > 0 and montant_ht > 0:
        tva = round(montant_ttc - montant_ht, 2)

    # Si on a TTC mais pas HT → estimer HT (TVA 18% par défaut Afrique)
    if montant_ht == 0 and montant_ttc > 0:
        montant_ht = round(montant_ttc / 1.18, 2)
        if tva == 0:
            tva = round(montant_ttc - montant_ht, 2)

    # ── Date ──────────────────────────────────────────────────────────────────
    date_facture = ""
    patterns_date = [
        # Avec label explicite (FR/EN/DE)
        r"(?:date\s*(?:de\s*(?:la\s*)?facture|d['\']?[ée]mission|invoice|issued?|du\s*document|datum)?)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        r"(?:invoice\s*date|date\s*issued?|bill\s*date|rechnungsdatum|ausstellungsdatum)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        # Datum allemand : "Datum 17.11.2017"
        r"(?:datum|date)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        # Format texte anglais
        r"(\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})",
        r"((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4})",
        # Format texte français
        r"(\d{1,2}\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+\d{4})",
        # Format texte allemand
        r"(\d{1,2}\s+(?:januar|februar|m[äa]rz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4})",
        # ISO
        r"(\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})",
        # Fallback : toute date DD.MM.YYYY ou DD/MM/YYYY
        r"(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{4})",
    ]
    for pat in patterns_date:
        m = re.search(pat, t, re.I)
        if m:
            date_facture = m.group(1).strip()
            break

    # ── Référence facture ─────────────────────────────────────────────────────
    ref_facture = ""
    patterns_ref = [
        r"(?:(?:n[°o]?\s*(?:de\s*)?)?facture|invoice\s*(?:no?\.?|number|#|num(?:ber)?)|bill\s*(?:no?\.?|number|#))\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/\.]{2,30})",
        r"(?:ref(?:erence)?|r[ée]f\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/\.]{2,30})",
        r"(?:order\s*(?:no?\.?|number|#)|bon\s*de\s*commande)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/\.]{2,30})",
    ]
    for pat in patterns_ref:
        m = re.search(pat, t, re.I)
        if m:
            ref_facture = m.group(1).strip()
            break

    # ── Fournisseur / Émetteur ────────────────────────────────────────────────
    fournisseur = ""
    patterns_fourn = [
        r"(?:from|de\s*:|émis?\s*par|issued?\s*by|vendor|supplier|billed?\s*from|absender|rechnungssteller)\s*[:\-]?\s*([A-Z][^\n]{2,50})",
        r"(?:company|société|entreprise|raison\s*sociale|firma|unternehmen)\s*[:\-]?\s*([A-Z][^\n]{2,50})",
    ]
    for pat in patterns_fourn:
        m = re.search(pat, t, re.I)
        if m:
            fournisseur = m.group(1).strip()[:60]
            break

    # Fallback : première ligne non vide qui ressemble à un nom d'entreprise
    if not fournisseur:
        for line in t.split("\n")[:8]:
            line = line.strip()
            if (len(line) > 3 and len(line) < 60
                    and not re.match(r"^\d", line)
                    and not re.search(r"(?:invoice|facture|date|total|page|ticket|online|receipt|bon\s*de|www\.|http)", line, re.I)):
                fournisseur = line
                break

    # Nettoyage fournisseur
    if fournisseur:
        # Supprimer les adresses et numéros de téléphone
        fournisseur = re.sub(r"\s*[-–]\s*(?:tel|tél|phone|fax).*", "", fournisseur, flags=re.I)
        fournisseur = re.sub(r"\s*,\s*\d{5}.*", "", fournisseur)  # code postal
        fournisseur = fournisseur.strip()[:60]

    # ── Devise ────────────────────────────────────────────────────────────────
    # Détecter la devise pour normaliser les montants
    devise_detected = "FCFA"
    if re.search(r"€|eur(?:o)?", t, re.I):
        devise_detected = "EUR"
        # Convertir EUR → FCFA (1 EUR ≈ 655.957 FCFA)
        if montant_ttc > 0 and montant_ttc < 100000:  # probablement en EUR
            montant_ttc = round(montant_ttc * 655.957, 0)
            montant_ht  = round(montant_ht  * 655.957, 0)
            tva         = round(tva          * 655.957, 0)
    elif re.search(r"\$|usd|dollar", t, re.I):
        devise_detected = "USD"
        if montant_ttc > 0 and montant_ttc < 100000:
            montant_ttc = round(montant_ttc * 600, 0)
            montant_ht  = round(montant_ht  * 600, 0)
            tva         = round(tva          * 600, 0)

    # ── Catégorie ─────────────────────────────────────────────────────────────
    categorie = _detect_categorie(t)

    return {
        "fournisseur":  fournisseur[:60] if fournisseur else "",
        "montant_ttc":  round(montant_ttc, 2),
        "montant_ht":   round(montant_ht, 2),
        "tva":          round(tva, 2),
        "date_facture": date_facture,
        "ref_facture":  ref_facture,
        "categorie":    categorie,
    }


def _parse_amount(s: str) -> float:
    """Convertit une chaîne de montant en float. Gère 1.234,56 et 1,234.56 et symboles €/e/$"""
    # Nettoyer les symboles monétaires et espaces
    s = re.sub(r"[€$£e\s]", "", s.strip()) if not re.search(r"\d", s.replace("e","")) else re.sub(r"[€$£\s]", "", s.strip())
    s = re.sub(r"[^\d.,]", "", s.strip())
    if not s:
        return 0.0
    # Format européen : 1.234,56
    if re.search(r"\d\.\d{3},\d{2}$", s):
        s = s.replace(".", "").replace(",", ".")
    # Format US : 1,234.56
    elif re.search(r"\d,\d{3}\.\d{2}$", s):
        s = s.replace(",", "")
    # Virgule seule comme décimale : 1234,56
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    # Point seul comme décimale : 1234.56
    elif "." in s and "," not in s:
        pass
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _detect_categorie(texte: str) -> str:
    """Détecte la catégorie de la facture par mots-clés (FR/EN/DE)."""
    t = texte.lower()
    categories = {
        "Transport":    ["transport", "taxi", "uber", "livraison", "delivery", "shipping",
                         "freight", "logistique", "bahn", "sncf", "train", "ice ", "tgv",
                         "fahrkarte", "ticket", "flug", "airline", "air france", "lufthansa",
                         "bus", "metro", "tram", "ratp", "transports"],
        "Telecom":      ["orange", "mtn", "moov", "telecom", "mobile", "internet", "phone",
                         "airtel", "wifi", "telekom", "vodafone", "sfr", "bouygues"],
        "Energie":      ["electricite", "electricity", "eneo", "cie", "senelec", "sodeci",
                         "energie", "energy", "fuel", "carburant", "essence", "gasoil",
                         "strom", "gas", "wasser"],
        "Informatique": ["informatique", "software", "hardware", "ordinateur", "computer",
                         "licence", "license", "microsoft", "google", "aws", "cloud",
                         "hosting", "saas"],
        "Fournitures":  ["fourniture", "papeterie", "bureau", "office", "supplies",
                         "stationery", "burobedarf"],
        "Alimentation": ["restaurant", "alimentation", "food", "repas", "meal", "catering",
                         "traiteur", "supermarche", "carrefour", "jumia", "five guys",
                         "fiveguys", "lebensmittel", "backer", "cafe"],
        "Loyer":        ["loyer", "rent", "bail", "location", "lease", "immobilier",
                         "miete", "mietvertrag"],
        "Assurance":    ["assurance", "insurance", "prime", "cotisation", "versicherung"],
        "Banque":       ["banque", "bank", "frais bancaires", "commission", "virement",
                         "gebuhren", "bankgebuhr"],
        "Consulting":   ["consulting", "conseil", "prestation", "service", "honoraires",
                         "fees", "beratung"],
        "Ventes":       ["vente", "sale", "revenue", "chiffre d'affaires"],
        "Sante":        ["pharmacie", "medecin", "hopital", "clinique", "sante", "health",
                         "apotheke", "arzt", "krankenhaus"],
        "Hotellerie":   ["hotel", "airbnb", "booking", "hebergement", "nuit", "chambre",
                         "unterkunft", "ubernachtung"],
    }
    for cat, keywords in categories.items():
        if any(kw in t for kw in keywords):
            return cat
    return "Autres"



def _extract_ollama_sync(texte: str) -> Optional[dict]:
    """Version synchrone de l'extraction Ollama — utilise urllib (pas httpx async)."""
    try:
        import urllib.request
        from dotenv import load_dotenv
        _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        load_dotenv(_env, override=True)

        ollama_url   = os.getenv("OLLAMA_URL",   "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

        # Vérifier disponibilité Ollama
        try:
            req_check = urllib.request.Request(f"{ollama_url}/api/tags")
            with urllib.request.urlopen(req_check, timeout=3) as r:
                if r.status != 200:
                    return None
        except Exception:
            
            return None

        prompt = f"""Analyse cette facture et extrais les informations en JSON.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après.

Facture :
{texte[:3000]}

JSON attendu (utilise null si non trouvé) :
{{
  "fournisseur": "nom de l'entreprise émettrice",
  "montant_ttc": 0.00,
  "montant_ht": 0.00,
  "tva": 0.00,
  "date_facture": "JJ/MM/AAAA",
  "ref_facture": "numéro de facture",
  "categorie": "Telecom|Energie|Transport|Informatique|Fournitures|Alimentation|Loyer|Assurance|Banque|Consulting|Ventes|Autres"
}}"""

        payload = json.dumps({
            "model":  ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 512},
        }).encode()

        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TEXT_TIMEOUT) as r:
            raw = json.loads(r.read()).get("response", "")
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return _clean_ollama_result(json.loads(m.group()))
    except Exception as e:
        log.warning("[OLLAMA SYNC] %s", e)
    return None


def _clean_ollama_result(data: dict) -> dict:
    """Nettoie et valide le résultat Ollama."""
    def safe_float(v):
        if v is None: return 0.0
        try: return float(str(v).replace(",", ".").replace(" ", ""))
        except: return 0.0

    return {
        "fournisseur":  str(data.get("fournisseur") or "")[:60],
        "montant_ttc":  safe_float(data.get("montant_ttc")),
        "montant_ht":   safe_float(data.get("montant_ht")),
        "tva":          safe_float(data.get("tva")),
        "date_facture": str(data.get("date_facture") or ""),
        "ref_facture":  str(data.get("ref_facture") or ""),
        "categorie":    str(data.get("categorie") or "Autres"),
    }


# ── Extraction via DeepSeek API ───────────────────────────────────────────────

def _extract_deepseek(texte: str) -> Optional[dict]:
    """Extraction via DeepSeek API (internet requis)."""
    try:
        from dotenv import load_dotenv
        _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        load_dotenv(_env, override=True)
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None

        import urllib.request
        prompt = f"""Extract invoice data as JSON only. No text before or after.

Invoice text:
{texte[:3000]}

Return this exact JSON structure:
{{
  "fournisseur": "company name that issued the invoice",
  "montant_ttc": 0.00,
  "montant_ht": 0.00,
  "tva": 0.00,
  "date_facture": "DD/MM/YYYY",
  "ref_facture": "invoice number",
  "categorie": "Telecom|Energie|Transport|Informatique|Fournitures|Alimentation|Loyer|Assurance|Banque|Consulting|Ventes|Autres"
}}"""

        payload = json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.1,
        }).encode()

        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=payload, method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            raw = resp["choices"][0]["message"]["content"].strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return _clean_ollama_result(json.loads(m.group()))
    except Exception as e:
        log.warning("[DEEPSEEK EXTRACT] %s", e)
    return None


# ── Fusion des résultats ──────────────────────────────────────────────────────

def _merge(base: dict, override: dict) -> dict:
    """Fusionne deux dicts d'extraction — override remplace si valeur non nulle."""
    result = dict(base)
    for k, v in override.items():
        if v and v != 0 and v != 0.0 and v != "":
            result[k] = v
    return result


# ── Pipeline principal ────────────────────────────────────────────────────────

def process_invoice(fid: int, file_path: str, expected_year: Optional[int] = None) -> None:
    nom = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    log.info("[PROC v3-REGEX] START #%d %s", fid, nom)
    db.set_statut(fid, "en_cours")

    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        # ── 1. Extraire le texte ──────────────────────────────────────────
        # Excel → extraction directe des cellules
        if ext in (".xlsx", ".xls"):
            texte = _read_excel_text(file_path)
            log.info("[PROC] #%d Excel: %d chars", fid, len(texte))
        else:
            texte = _read_pdf_text(file_path)

        # OCR si PDF scanné ou image (pas pour Excel)
        if ext not in (".xlsx", ".xls") and len(texte.strip()) < 50:
            log.info("[PROC] #%d texte court (%d chars) — tentative OCR", fid, len(texte))
            image_bytes = _to_image_bytes(file_path)
            image_bytes = _opencv_boost(image_bytes)
            try:
                from services.ocr import extract_text_bytes
                texte_ocr = extract_text_bytes(image_bytes)
                if len(texte_ocr) > len(texte):
                    texte = texte_ocr
                    log.info("[PROC] #%d OCR: %d chars", fid, len(texte))
            except Exception as e:
                log.warning("[PROC] OCR failed: %s", e)

        # ── 2. Détection type entrante/sortante ───────────────────────────
        from services.detector import detect_type, check_year_coherence
        detection    = detect_type(texte, nom)
        type_facture = detection.get("type", "entrante")
        log.info("[PROC] #%d type=%s", fid, type_facture)

        # ── 3. Extraction regex (toujours) ────────────────────────────────
        data = _extract_regex(texte)
        data["type_facture"] = type_facture
        data["texte_brut"]   = texte[:5000]
        data["confiance"]    = 0.6
        log.info("[PROC] #%d regex: fourn=%r ttc=%.2f date=%r ref=%r",
                 fid, data["fournisseur"], data["montant_ttc"],
                 data["date_facture"], data["ref_facture"])

        # ── 4. DeepSeek si montant manquant ou fournisseur inconnu ───────
        needs_ai = (data["montant_ttc"] == 0 or
                    not data.get("fournisseur") or
                    data.get("fournisseur") in ("Inconnu", ""))

        if needs_ai and len(texte) > 30:
            # Essayer DeepSeek d'abord (internet)
            ds_result = _extract_deepseek(texte)
            if ds_result and (ds_result.get("montant_ttc", 0) > 0 or ds_result.get("fournisseur")):
                data = _merge(data, ds_result)
                data["confiance"] = 0.88
                log.info("[PROC] #%d DeepSeek: fourn=%r ttc=%.2f",
                         fid, data["fournisseur"], data["montant_ttc"])
            else:
                # Fallback Ollama local
                ol_result = _extract_ollama_sync(texte)
                if ol_result and (ol_result.get("montant_ttc", 0) > 0 or ol_result.get("fournisseur")):
                    data = _merge(data, ol_result)
                    data["confiance"] = 0.82
                    log.info("[PROC] #%d Ollama: fourn=%r ttc=%.2f",
                             fid, data["fournisseur"], data["montant_ttc"])
        elif data["montant_ttc"] > 0:
            data["confiance"] = 0.75

        # Fallback fournisseur depuis détecteur
        if not data.get("fournisseur"):
            data["fournisseur"] = detection.get("emetteur") or "Inconnu"

        # ── 6. Anomalies ──────────────────────────────────────────────────
        anomalies = []

        # Doublon : fournisseur + montant + date doivent tous être présents et identiques
        fourn_ok = bool(data.get("fournisseur") and data["fournisseur"] not in ("", "Inconnu"))
        mont_ok  = data["montant_ttc"] > 0
        date_ok  = bool(data.get("date_facture"))
        if fourn_ok and mont_ok and date_ok and detect_duplicate(fid, data):
            anomalies.append({
                "titre": "Facture doublon",
                "description": f"Une facture de {data['fournisseur']} pour {data['montant_ttc']:,.0f} FCFA "
                               f"du {data['date_facture']} existe déjà."
            })

        # Montant non extrait
        if data["montant_ttc"] == 0:
            anomalies.append({
                "titre": "Montant non détecté",
                "description": "Le montant TTC n'a pas pu être extrait. Vérifiez le document."
            })

        # TVA manquante — seulement pour les montants significatifs (> 1000 FCFA)
        if data["tva"] == 0 and data["montant_ttc"] > 1000:
            anomalies.append({
                "titre": "TVA manquante",
                "description": "Aucune TVA détectée sur cette facture de montant significatif."
            })

        # Année incohérente
        if expected_year is not None and data.get("date_facture"):
            check = check_year_coherence(data["date_facture"], expected_year)
            if not check["ok"]:
                anomalies.append({
                    "titre": "Année incohérente",
                    "description": check["message"]
                })

        data["anomalies"] = anomalies
        data["statut"]    = "traite"
        data["analyse_ia"] = detection.get("raison", "")

        # ── 7. Persistance en base ────────────────────────────────────────
        db.update_facture(fid, data)
        log.info("[PROC] DONE #%d — ttc=%.2f fourn=%r anom=%d",
                 fid, data["montant_ttc"], data["fournisseur"], len(anomalies))

        # ── 8. Suppression du fichier original (après persistance réussie) ─
        _delete_file_after_processing(fid, file_path)

    except Exception as e:
        log.error("[PROC ERROR] #%d %s", fid, e)
        traceback.print_exc()
        db.update_facture(fid, {"statut": "erreur", "analyse_ia": str(e)[:200]})
        # En cas d'erreur : fichier conservé pour diagnostic


def _delete_file_after_processing(fid: int, chemin: str) -> bool:
    """
    Supprime le fichier original après traitement réussi.
    La suppression n'a lieu QUE si la persistance DB a réussi.
    Retourne True si supprimé, False si déjà absent.
    """
    if not chemin:
        return False
    try:
        if os.path.exists(chemin):
            os.remove(chemin)
            log.info("[CLEANUP] Fichier supprimé : %s (fid=%d)", chemin, fid)
            # Nettoyer le répertoire parent s'il est vide
            parent = os.path.dirname(chemin)
            try:
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
            except Exception:
                pass
            # Mettre à jour le chemin en base
            db.clear_file_path(fid)
            return True
        else:
            log.debug("[CLEANUP] Fichier déjà absent : %s (fid=%d)", chemin, fid)
            db.clear_file_path(fid)
            return False
    except Exception as e:
        log.error("[CLEANUP] Erreur suppression fid=%d : %s", fid, e)
        return False


# ── Bilan financier ───────────────────────────────────────────────────────────

def generate_bilan(stats: dict, periode: str = "") -> str:
    tot  = stats.get("totaux", {})
    flux = stats.get("flux", {})
    dep  = flux.get("depenses_ttc", tot.get("total_ttc", 0))
    rec  = flux.get("recettes_ttc", 0)
    solde = flux.get("solde_net", rec - dep)
    nb_t  = tot.get("nb_traites", 0)
    nb_total = tot.get("nb_total", 0)
    nb_anom  = stats.get("nb_anomalies", 0)
    fourn = stats.get("fournisseurs", [])
    top_f = fourn[0].get("fournisseur", "—") if fourn else "—"

    signe = "excédentaire" if solde > 0 else ("déficitaire" if solde < 0 else "équilibré")
    return (
        f"BILAN FINANCIER FINALYSE — {periode or 'Période analysée'}\n"
        f"{'='*50}\n\n"
        f"RÉSUMÉ\n"
        f"  Factures analysées : {nb_t} / {nb_total}\n"
        f"  Anomalies          : {nb_anom}\n\n"
        f"FLUX FINANCIERS\n"
        f"  Dépenses TTC  : {dep:,.0f} FCFA\n"
        f"  Recettes TTC  : {rec:,.0f} FCFA\n"
        f"  Solde net     : {solde:+,.0f} FCFA ({signe})\n\n"
        f"TOP FOURNISSEUR : {top_f}\n"
        f"{'='*50}\n"
        f"Généré par Finalyse IA"
    )
