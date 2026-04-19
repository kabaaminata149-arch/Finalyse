# MEMO TECHNIQUE FINALYSE
## Systeme d Analyse Intelligente de Factures avec extraits de code essentiels

**Version :** 1.0 | **Date :** Avril 2026

---

## 1. Vue Globale du Systeme

Le systeme ingere des fichiers PDF ou image, extrait les donnees financieres par une chaine regex puis LLM, valide la coherence, detecte les anomalies, et persiste en SQLite WAL.

**Flux complet :**

```
Fichier recu -> Sauvegarde disque -> Enregistrement BDD (en_attente)
-> Tache fond -> Extraction texte -> Nettoyage -> Regex -> LLM si besoin
-> Classification flux -> Anomalies -> BDD (traite)
```

**Declenchement du pipeline (routes/factures.py) :**

```python
@router.post("/upload")
async def upload(files, bg: BackgroundTasks, ...):
    for file in files:
        fid = db.create_facture(uid, nom, chemin, taille, ...)
        bg.add_task(process_invoice, fid, chemin, annee)
    return {"status": "processing", "ids": ids}
```

---

## 2. Pipeline Principale de Traitement

### Etape 1 - Ingestion et extraction texte

```python
def process_invoice(fid: int, file_path: str, expected_year=None):
    db.set_statut(fid, "en_cours")

    # Tentative extraction native PDF
    texte = _read_pdf_text(file_path)

    # Si texte insuffisant -> OCR
    if len(texte.strip()) < 50:
        image_bytes = _to_image_bytes(file_path)
        image_bytes = _opencv_boost(image_bytes)
        texte_ocr = extract_text_bytes(image_bytes)
        if len(texte_ocr) > len(texte):
            texte = texte_ocr
```

### Etape 2 - Extraction PDF natif

```python
def _read_pdf_text(path: str) -> str:
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:6]:   # max 6 pages
            t = page.extract_text()
            if t:
                out.append(t)
    return _clean_ocr_text("\n".join(out))
```

### Etape 3 - Pretraitement image (vision.py)

```python
def preprocess(image_bytes: bytes) -> bytes:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Redimensionner si trop petite
    if min(h, w) < 800:
        scale = 1200 / min(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    denoised  = cv2.fastNlMeansDenoising(gray, h=15)
    clahe     = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(denoised)

    # Binarisation Otsu
    _, binary = cv2.threshold(equalized, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ok, buf = cv2.imencode(".png", binary)
    return buf.tobytes()
```

### Etape 4 - OCR Tesseract

```python
def extract_text_bytes(image_bytes: bytes) -> str:
    img  = Image.open(io.BytesIO(image_bytes))
    conf = r"--oem 3 --psm 6 -l fra+eng"
    return pytesseract.image_to_string(img, config=conf).strip()
```

### Etape 5 - Nettoyage du texte

```python
def _clean_ocr_text(text: str) -> str:
    for line in text.split("\n"):
        # Supprimer les codes-barres (>10 chiffres consecutifs)
        if re.search(r"\d{11,}", line):
            if not re.search(r"total|montant|amount|pay|prix", line, re.I):
                continue
        # Garder si >= 40% de caracteres latins
        ratio = latin_chars / len(line.strip())
        if ratio >= 0.4:
            lines.append(cleaned_line)
```

### Etape 6 - Extraction regex (champs financiers)

```python
# Montant TTC - patterns par priorite decroissante
patterns_ttc = [
    r"(?:total\s*(?:ttc|toutes?\s*taxes?))\s*[:\-]?\s*([\d\s.,]+)",
    r"(?:net\s*[aa]\s*payer|montant\s*(?:total|ttc))\s*[:\-]?\s*([\d\s.,]+)",
    r"(?:grand\s*total|total\s*amount)\s*[:\-]?\s*([\d\s.,]+[EUR$e]?)",
    r"(?:summe|gesamtbetrag|zu\s*zahlen)\s*[:\-]?\s*([\d\s.,]+)",
    r"^total\s+([\d]+[.,][\d]{2})\s*$",
]

# Estimation HT si absent
if montant_ht == 0 and montant_ttc > 0:
    montant_ht = round(montant_ttc / 1.18, 2)   # TVA 18% Afrique de l Ouest
    tva        = round(montant_ttc - montant_ht, 2)

# Conversion devise
if re.search(r"EUR|euro", t, re.I):
    montant_ttc = round(montant_ttc * 655.957, 0)  # EUR -> FCFA
```

### Etape 7 - Enrichissement LLM (DeepSeek -> Ollama)

```python
needs_ai = (data["montant_ttc"] == 0 or not data.get("fournisseur"))

if needs_ai:
    # 1. DeepSeek API (internet, confiance 0.88)
    ds_result = _extract_deepseek(texte)
    if ds_result and ds_result.get("montant_ttc", 0) > 0:
        data = _merge(data, ds_result)
        data["confiance"] = 0.88
    else:
        # 2. Ollama local (fallback, confiance 0.82)
        ol_result = _extract_ollama_sync(texte)
        if ol_result:
            data = _merge(data, ol_result)
            data["confiance"] = 0.82

# Scores : regex seul=0.60 | regex+montant=0.75 | Ollama=0.82 | DeepSeek=0.88
```

**Prompt LLM :**

```python
prompt = f"""Analyse cette facture et extrais les informations en JSON.
Reponds UNIQUEMENT avec un objet JSON valide.

Facture : {texte[:3000]}

JSON attendu :
{{
  "fournisseur": "nom entreprise emettrice",
  "montant_ttc": 0.00,
  "montant_ht":  0.00,
  "tva":         0.00,
  "date_facture":"JJ/MM/AAAA",
  "ref_facture": "numero",
  "categorie":   "Telecom|Transport|Energie|..."
}}"""
```

### Etape 8 - Fusion des resultats

```python
def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        # Override remplace seulement si valeur non nulle
        if v and v != 0 and v != 0.0 and v != "":
            result[k] = v
    return result
```

---

## 3. Routines Critiques

### detect_type - Classification entrante/sortante

```python
def detect_type(texte: str, nom_fichier: str = "") -> dict:
    score_entrant = 0
    score_sortant = 0

    for kw in KW_ENTRANTE:   # "fournisseur", "net a payer", "orange"...
        if kw in texte.lower(): score_entrant += 1
    for kw in KW_SORTANTE:   # "client", "bill to", "vendu a"...
        if kw in texte.lower(): score_sortant += 1

    # Bonus nom de fichier (+3 points)
    if any(w in nom_fichier.lower() for w in ["fournisseur", "achat"]):
        score_entrant += 3

    # Pattern structurel "emis par" (+2 points)
    m = RE_EMIS_PAR.search(texte)
    if m:
        score_entrant += 2

    if score_entrant > score_sortant:
        return {"type": "entrante", "confiance": score_entrant/(score_entrant+score_sortant)}
    elif score_sortant > score_entrant:
        return {"type": "sortante", "confiance": score_sortant/(score_entrant+score_sortant)}
    else:
        return {"type": "entrante", "confiance": 0.45}  # defaut
```

### detect_duplicate - Detection doublons

```python
_HASH_CACHE: set = set()   # cache memoire global au processus

def detect_duplicate(fid: int, data: dict) -> bool:
    # Les 3 champs doivent etre presents
    fourn_ok = bool(data.get("fournisseur") and data["fournisseur"] != "Inconnu")
    mont_ok  = data["montant_ttc"] > 0
    date_ok  = bool(data.get("date_facture"))

    if not (fourn_ok and mont_ok and date_ok):
        return False   # pas assez de donnees -> pas de detection

    base = f"{data['fournisseur']}-{data['montant_ttc']}-{data['date_facture']}"
    h = hashlib.md5(base.encode()).hexdigest()
    if h in _HASH_CACHE:
        return True
    _HASH_CACHE.add(h)
    return False
```

### _parse_amount - Normalisation des montants

```python
def _parse_amount(s: str) -> float:
    s = re.sub(r"[EUR$\s]", "", s.strip())
    s = re.sub(r"[^\d.,]", "", s)

    if re.search(r"\d\.\d{3},\d{2}$", s):   # 1.234,56 -> europeen
        s = s.replace(".", "").replace(",", ".")
    elif re.search(r"\d,\d{3}\.\d{2}$", s): # 1,234.56 -> americain
        s = s.replace(",", "")
    elif "," in s and "." not in s:          # 1234,56 -> virgule decimale
        s = s.replace(",", ".")

    return float(s)
```

### get_stats - Agregation financiere

```python
def get_stats(uid: int, annee=None, mois=None) -> dict:
    flux = dict(c.execute(f"""
        SELECT
          SUM(CASE WHEN type_facture='entrante' THEN montant_ttc ELSE 0 END) depenses_ttc,
          SUM(CASE WHEN type_facture='sortante' THEN montant_ttc ELSE 0 END) recettes_ttc,
          COUNT(CASE WHEN type_facture='entrante' THEN 1 END) nb_entrantes,
          COUNT(CASE WHEN type_facture='sortante' THEN 1 END) nb_sortantes
        FROM factures WHERE {base_filter} AND statut='traite'
    """, base_params).fetchone())

    solde_net = flux["recettes_ttc"] - flux["depenses_ttc"]
    return {"flux": {**flux, "solde_net": solde_net}, ...}
```

---

## 4. Pipeline de Detection d Anomalies

```python
anomalies = []

# 1. DOUBLON
if fourn_ok and mont_ok and date_ok and detect_duplicate(fid, data):
    anomalies.append({
        "titre": "Facture doublon",
        "description": f"Facture de {data['fournisseur']} pour "
                       f"{data['montant_ttc']:,.0f} FCFA du {data['date_facture']} deja enregistree."
    })

# 2. MONTANT NON DETECTE
if data["montant_ttc"] == 0:
    anomalies.append({
        "titre": "Montant non detecte",
        "description": "Le montant TTC n a pas pu etre extrait."
    })

# 3. TVA MANQUANTE (seulement si montant > 1000 FCFA)
if data["tva"] == 0 and data["montant_ttc"] > 1000:
    anomalies.append({
        "titre": "TVA manquante",
        "description": "Aucune TVA detectee sur cette facture."
    })

# 4. ANNEE INCOHERENTE
if expected_year and data.get("date_facture"):
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", data["date_facture"])
    if years and int(years[0]) != expected_year:
        anomalies.append({
            "titre": "Annee incoherente",
            "description": f"Facture de {years[0]}, annee attendue : {expected_year}"
        })

data["anomalies"] = anomalies
data["statut"]    = "traite"   # toujours traite, meme avec anomalies
```

---

## 5. Enchainement des Routines

```
upload()
  |-- create_facture()           -> statut: en_attente
  |-- bg.add_task(process_invoice)

process_invoice()
  |-- set_statut("en_cours")
  |-- _read_pdf_text()           -> texte natif
  |   |-- si < 50 chars:
  |       |-- to_image_bytes()
  |       |-- opencv_boost()
  |       |-- extract_text_bytes()   -> OCR Tesseract
  |-- _clean_ocr_text()
  |-- detect_type()              -> entrante | sortante
  |-- _extract_regex()           -> confiance 0.60
  |   |-- si montant==0 ou fournisseur vide:
  |       |-- _extract_deepseek()    -> confiance 0.88
  |       |-- _extract_ollama_sync() -> confiance 0.82
  |-- _merge(regex, llm)
  |-- detect_duplicate()
  |-- [detection anomalies]
  |-- update_facture()           -> statut: traite
      |-- si exception: statut: erreur
```

**Dependances critiques :**
- detect_duplicate depend de _extract_regex (les 3 champs doivent exister)
- DeepSeek/Ollama ne sont appeles que si regex insuffisant
- check_year_coherence depend de date_facture ET de expected_year fourni a l import

---

## 6. Gestion des Erreurs et Cas Limites

### Fichier illisible

```python
try:
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)
    # ... traitement
except Exception as e:
    log.error("[PROC ERROR] #%d %s", fid, e)
    db.update_facture(fid, {
        "statut":     "erreur",
        "analyse_ia": str(e)[:200]
    })
```

### Image non decodable

```python
def preprocess(image_bytes: bytes) -> bytes:
    try:
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            # Fallback PIL
            pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except ImportError:
        return image_bytes   # cv2 absent -> original
    except Exception:
        return image_bytes   # erreur -> original sans crash
```

### Montant aberrant (sanity check)

```python
if montant_ttc > 50000:
    has_fcfa = bool(re.search(r"fcfa|xof|cfa", t, re.I))
    if not has_fcfa:
        all_amounts = [_parse_amount(m) for m in re.findall(r"[\d]+[.,][\d]{2}", t)]
        reasonable  = [v for v in all_amounts if 0.5 < v < 10000]
        if reasonable:
            montant_ttc = max(reasonable)
```

### Resultat LLM invalide

```python
def _clean_ollama_result(data: dict) -> dict:
    def safe_float(v):
        if v is None: return 0.0
        try:
            return float(str(v).replace(",", ".").replace(" ", ""))
        except:
            return 0.0   # jamais de crash sur valeur non numerique

    return {
        "fournisseur": str(data.get("fournisseur") or "")[:60],
        "montant_ttc": safe_float(data.get("montant_ttc")),
        "montant_ht":  safe_float(data.get("montant_ht")),
        "tva":         safe_float(data.get("tva")),
        "date_facture":str(data.get("date_facture") or ""),
        "ref_facture": str(data.get("ref_facture") or ""),
        "categorie":   str(data.get("categorie") or "Autres"),
    }
```

### Tesseract non trouve

```python
def _resolve_tesseract() -> str:
    # 1. Variable .env
    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd and os.path.isfile(cmd): return cmd

    # 2. PATH systeme
    found = shutil.which("tesseract")
    if found: return found

    # 3. Scan AppData tous profils Windows
    for user_dir in os.listdir(parent):
        candidate = os.path.join(parent, user_dir,
            "AppData", "Local", "Programs", "Tesseract-OCR", "tesseract.exe")
        if os.path.isfile(candidate): return candidate

    return "tesseract"   # fallback
```

---

## 7. Cahier d Erreurs et Difficultes

### 7.1 Erreurs liees aux donnees

**Formats differents de factures**

Solution mise en place :
```python
# Patterns multi-langues pour le meme champ
patterns_ttc = [
    r"(?:total\s*ttc|toutes?\s*taxes?)",   # FR
    r"(?:grand\s*total|total\s*amount)",    # EN
    r"(?:summe|gesamtbetrag|zu\s*zahlen)",  # DE
    r"^total\s+([\d]+[.,][\d]{2})\s*$",    # ticket de caisse
]
```

**Donnees bruitees (OCR)**

Solution :
```python
# Filtre ratio caracteres latins
ratio = latin_chars / total_chars
if ratio >= 0.4 or total_chars < 8:
    lines.append(cleaned_line)
# Lignes codes-barres supprimees
if re.search(r"\d{11,}", line) and not re.search(r"total|montant", line, re.I):
    continue
```

### 7.2 Erreurs liees a l extraction

**Confusion HT vs TTC**

Solution : priorite aux labels explicites TTC.
```python
# Priorite 1 : label TTC explicite
r"(?:total\s*ttc|net\s*a\s*payer)",
# Priorite 2 : label generique (risque confusion)
r"^total\s+([\d]+[.,][\d]{2})",
```

**Erreurs sur les montants**

Solution :
```python
if re.search(r"\d\.\d{3},\d{2}$", s):   # 1.234,56 -> format EU
    s = s.replace(".", "").replace(",", ".")
elif re.search(r"\d,\d{3}\.\d{2}$", s): # 1,234.56 -> format US
    s = s.replace(",", "")
```

### 7.3 Erreurs logiques

**Calcul TVA incorrect**

```python
# Probleme : 18% incorrect pour factures europeennes (20% FR, 19% DE)
if montant_ht == 0 and montant_ttc > 0:
    montant_ht = round(montant_ttc / 1.18, 2)   # estimation approximative
# Amelioration future : detecter pays -> taux correct
```

**Cache doublons non persistant**

```python
_HASH_CACHE: set = set()   # perdu au redemarrage du serveur
# Amelioration future : stocker hashes en base SQLite avec index
```

### 7.4 Erreurs systeme

**Lenteur Ollama**

```python
OLLAMA_TEXT_TIMEOUT = float(os.getenv("OLLAMA_TEXT_TIMEOUT", "90"))

# Ping prealable pour eviter d attendre un serveur mort
try:
    with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3) as r:
        if r.status != 200: return None
except Exception:
    return None   # Ollama indisponible -> skip immediat
```

**Concurrence SQLite**

```python
c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA busy_timeout=30000")   # 30s avant BusyError
_local.conn = c   # une connexion par thread
```

---

## 8. Strategies de Correction et Amelioration

| Erreur | Cause | Solution actuelle | Amelioration future |
|--------|-------|-------------------|---------------------|
| TVA incorrecte | Taux fixe 18% | Extraction directe prioritaire | Detecter pays -> taux correct |
| Cache doublons perdu | Set en memoire | Rechargement au demarrage | Hashes en base SQLite |
| Montant ambigu | Formats numeriques mixtes | Detection par structure | Inferer format depuis devise |
| Lenteur Ollama | Modeles lourds | Timeout + ping prealable | Modeles legers (glm-ocr 0.9B) |
| OCR mauvaise qualite | Resolution faible | CLAHE + Otsu | Modele vision dedie documents |

---

## 9. Optimisation et Automatisation

### Pipeline entierement automatise

```python
# Declenchement immediat sans intervention humaine
bg.add_task(process_invoice, fid, chemin, annee)
return {"status": "processing", "ids": [fid]}
```

### Strategie de degradation progressive

```
pdfplumber (natif, < 1s)
  -> si < 50 chars : OpenCV + Tesseract (5-15s)
      -> regex (< 0.1s, confiance 0.60-0.75)
          -> si insuffisant : DeepSeek API (2-15s, confiance 0.88)
              -> si echec : Ollama local (10-90s, confiance 0.82)
                  -> si echec : resultats regex conserves
```

### Resolution automatique Tesseract

```python
# Aucune configuration manuelle requise
pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract()
# Cherche dans : .env -> PATH -> Program Files -> AppData tous profils
```

### Sauvegarde cloud MongoDB Atlas

```python
def backup_user(uid: int, email: str) -> dict:
    factures_clean = [{k: v for k, v in f.items()
                       if k not in ("chemin", "texte_brut")}
                      for f in db.get_factures(uid, limit=10000)]

    mongo_db.backups.replace_one(
        {"email": email},
        backup_doc,
        upsert=True   # cree ou remplace
    )
    # Historique limite aux 10 dernieres sauvegardes
    if len(history) > 10:
        mongo_db.backup_history.delete_many({"_id": {"$in": old_ids}})
```

### Generation rapport PDF avec IA

```python
def export_pdf(factures, uid, periode, stats, entreprise):
    try:
        # ReportLab -> PDF complet 7 sections
        return _build_pdf(factures, uid, periode, stats, entreprise)
    except ImportError:
        # Fallback .txt si ReportLab absent
        return _pdf_fallback(factures, uid, periode)
    except Exception as exc:
        print(f"[export_service] PDF build error: {exc}")
        return _pdf_fallback(factures, uid, periode)
```

---

*Document de reference Finalyse v1.0.0 - Avril 2026*
