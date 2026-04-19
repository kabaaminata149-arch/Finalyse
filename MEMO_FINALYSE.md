# MEMO FINALYSE v1.0 — Documentation Complète

> Application desktop d'analyse intelligente de factures par IA
> Stack : Python 3.10 · FastAPI · PyQt6 · SQLite · MongoDB Atlas · Ollama / DeepSeek

---

## ARCHITECTURE

```
FinalyseV2/
├── GO.py                        # Lanceur principal (backend + frontend)
├── Finalyse.bat                 # Raccourci Windows (double-clic)
├── backup_prefs.json            # Préférences sauvegarde cloud (local)
├── backend/
│   ├── main.py                  # FastAPI — enregistrement des routes
│   ├── config.py                # Variables de configuration
│   ├── .env                     # Secrets (SMTP, MongoDB, DeepSeek, Ollama)
│   ├── requirements.txt         # Dépendances Python backend
│   ├── finalyse.db              # Base SQLite (WAL mode, thread-safe)
│   ├── auth/
│   │   └── jwt_handler.py       # JWT + bcrypt + validation mot de passe
│   ├── database/
│   │   └── db.py                # Couche DB (users, dossiers, factures, stats)
│   ├── routes/
│   │   ├── auth.py              # /api/auth/* (login, register, reset)
│   │   ├── factures.py          # /api/factures/* (upload, list, delete)
│   │   ├── dossiers.py          # /api/dossiers/* (CRUD dossiers)
│   │   ├── dashboard.py         # /api/dashboard (stats filtrées)
│   │   ├── export.py            # /api/export/* (CSV, PDF, email)
│   │   ├── chatbot.py           # /api/chat/* (IA hybride)
│   │   ├── parametres.py        # /api/parametres/* (modèles IA)
│   │   └── backup.py            # /api/backup/* (MongoDB Atlas)
│   └── services/
│       ├── processor.py         # Pipeline extraction factures (v3-REGEX)
│       ├── detector.py          # Détection entrante/sortante
│       ├── export_service.py    # Génération PDF (ReportLab) + CSV
│       ├── ocr.py               # OCR Tesseract
│       ├── vision.py            # Prétraitement image OpenCV
│       ├── ai_chat.py           # Chat IA (DeepSeek API + Ollama + fallback)
│       ├── ollama.py            # Client Ollama
│       └── cloud_backup.py      # Sauvegarde/restauration MongoDB Atlas
├── frontend/
│   ├── main.py                  # AppShell PyQt6 + navigation
│   ├── api_client.py            # Client HTTP vers le backend
│   ├── theme.py                 # Design system (couleurs, composants, Toast)
│   ├── pages/
│   │   ├── splash.py            # Écran de démarrage animé
│   │   ├── login.py             # Connexion / Inscription / Reset MDP
│   │   ├── dashboard.py         # Tableau de bord + Analyse IA
│   │   ├── import_page.py       # Import factures (drag & drop)
│   │   ├── rapports.py          # Rapport financier + conseils
│   │   ├── historique.py        # Historique avec filtres mois/année
│   │   ├── chatbot.py           # Assistant IA flottant
│   │   ├── backup.py            # Sauvegarde cloud
│   │   └── parametres.py        # Paramètres modèles IA
│   └── widgets/
│       └── sidebar.py           # Sidebar + TopBar + navigation
```

---

## FONCTIONNALITÉS

### 1. AUTHENTIFICATION
- **Inscription** : email validé (regex), mot de passe fort (8 car. min, 1 maj., 1 spécial, 1 chiffre), confirmation
- **Connexion** : JWT (24h), bcrypt, fallback PBKDF2
- **Reset MDP** : code 6 chiffres envoyé par email (Gmail SMTP), valable 2h
- **Changement MDP** : endpoint `/api/auth/change-password` (ancien MDP requis)

### 2. IMPORT DE FACTURES
- **Formats** : PDF, PNG, JPG, JPEG
- **Drag & drop** + bouton parcourir
- **Lot nommé** : popup pour nommer le lot avant envoi
- **Traitement en arrière-plan** : FastAPI BackgroundTasks
- **Polling** : le frontend poll le statut toutes les 3s jusqu'à `traite` ou `erreur`
- **Limite** : 20 MB par fichier (configurable `MAX_MB`)

### 3. EXTRACTION IA (pipeline v3-REGEX)
```
Fichier PDF/Image
    ↓
pdfplumber (texte natif)
    ↓ si < 50 chars
OCR Tesseract + OpenCV boost
    ↓
Nettoyage OCR (filtrage caractères non-latins, numéros série longs)
    ↓
Regex extraction (FR + EN + DE)
  - Montant TTC/HT/TVA
  - Date (10+ formats)
  - Référence facture
  - Fournisseur
  - Catégorie (12 catégories)
    ↓ si montant=0 ou fournisseur inconnu
DeepSeek API (si DEEPSEEK_API_KEY + internet)
    ↓ sinon
Ollama local (deepseek-r1:7b ou autre)
    ↓
Détection type : entrante (dépense) / sortante (recette)
    ↓
Anomalies : doublon, montant=0, date absente, TVA manquante, année incohérente
    ↓
Sauvegarde en DB
```

### 4. TABLEAU DE BORD
- **KPIs** : Dépenses totales, Nb factures, Anomalies (total global), Traitées
- **Transactions récentes** : 5 dernières avec statut
- **Analyse IA** : Factures analysées, Anomalies détectées
- **Détail anomalie** : clic sur une facture → détails + liste anomalies
- **Chargement animé** : points clignotants pendant le fetch

### 5. RAPPORT FINANCIER
- **Filtres** : Mois + Année (sélecteurs indépendants)
- **KPIs** : Charges, Produits, Résultat Net, TVA déductible
- **Compte de résultat** : Produits / Charges / Résultat + marge
- **Flux de trésorerie** : Entrées / Sorties / Flux net + ratio
- **Analyse de santé** : Rentabilité, Ratio, Anomalies, Taux traitement
- **Camembert** : Répartition charges par catégorie (dynamique, se redessine)
- **Évolution mensuelle** : 6 derniers mois (dépenses / recettes / solde)
- **Résumé exécutif** : texte narratif auto-généré
- **Conseils financiers** : 5 types de conseils basés sur les données réelles
- **Export** : CSV, PDF (8 sections), Email (HTML + PDF joint)

### 6. HISTORIQUE
- **Filtres** : Mois + Année + Recherche texte
- **Colonnes** : Fournisseur, Date, Montant TTC, Catégorie, Type (Charge/Produit), Statut
- **KPIs filtrés** : Total, Traitées, En attente, Total TTC
- **État vide** : icône + message + conseil

### 7. ASSISTANT IA (chatbot flottant)
- **Accès** : bouton "IA" flottant en bas à droite
- **Mode DeepSeek** : si `DEEPSEEK_API_KEY` + internet → deepseek-chat
- **Mode Ollama** : si Ollama local disponible → deepseek-r1:7b ou autre
- **Mode basique** : fallback local avec données BD
- **Contexte** : accès aux vraies données (dépenses, recettes, solde, fournisseurs, anomalies)
- **Typing animé** : points ●○○ → ○●○ → ○○● pendant la réponse
- **Spinner** : ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ sur le bouton d'envoi

### 8. SAUVEGARDE CLOUD (MongoDB Atlas)
- **Fréquences** : Manuel / Chaque jour / Chaque semaine / Chaque mois
- **Contenu sauvegardé** : factures (métadonnées + données extraites), dossiers
- **Restauration** : récupère tout sur un nouvel appareil
- **Historique** : 10 dernières sauvegardes conservées
- **Préférences** : stockées dans `backup_prefs.json`
- **Auto-backup** : vérifie toutes les heures si une sauvegarde est due

### 9. UX / INTERFACE
- **Responsive** : sidebar adaptative (160/190/220px selon largeur)
- **Transitions** : fade-in 150ms entre les pages
- **Toast notifications** : succès (vert), erreur (rouge), info (bleu), warning (orange)
- **StatCard hover** : ombre animée 16→24px
- **Scrollbars** : fines (6px), modernes
- **Splash screen** : barre de progression fluide + points animés
- **Instance unique** : impossible d'ouvrir 2 fois l'app

---

## CONFIGURATION (.env)

```env
# JWT
JWT_SECRET=finalyse-secret-key-CHANGE-THIS
JWT_EXPIRE_H=24

# Ollama (IA locale)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:7b
OLLAMA_MODEL_VISION=glm-ocr

# DeepSeek API (IA en ligne)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx

# SMTP Gmail (email)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre@gmail.com
SMTP_PASS=xxxx xxxx xxxx xxxx  # mot de passe d'application

# MongoDB Atlas (sauvegarde cloud)
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB=finalyse
BACKUP_INTERVAL_DAYS=7

# Limites
MAX_MB=20
```

---

## PIPELINE EMAIL

```
Utilisateur clique "Envoyer Email" dans Rapports
    ↓
Frontend → POST /api/export/send-report
    ↓
Backend lit SMTP_USER/SMTP_PASS depuis os.getenv()
    ↓
Génère PDF (8 sections ReportLab)
    ↓
Construit email HTML (KPIs + résumé)
    ↓
Attache PDF en pièce jointe
    ↓
smtplib.SMTP → Gmail → destinataire
```

**Prérequis** : Mot de passe d'application Gmail (myaccount.google.com/apppasswords)

---

## ERREURS RENCONTRÉES ET SOLUTIONS

### 1. IndentationError db.py ligne 1
- **Cause** : espace parasite avant le docstring
- **Fix** : suppression de l'espace avec PowerShell `$content -replace '^ """', '"""`

### 2. StatutIn non Pydantic → FastAPI crash
- **Cause** : `class StatutIn:` sans hériter de `BaseModel`
- **Fix** : `class StatutIn(BaseModel): statut: str`

### 3. RuntimeError QLabel deleted (anomalies dashboard)
- **Cause** : `self._empty` supprimé par `deleteLater()` dans la boucle de nettoyage
- **Fix** : vérification `if w is not self._empty` + `setParent(None)` au lieu de `deleteLater`

### 4. Double TopBar (barre Windows + barre custom)
- **Cause** : boutons —/□/✕ ajoutés dans TopBar alors que la fenêtre Windows a déjà sa barre
- **Fix** : suppression des boutons custom, garder la barre Windows native

### 5. Superposition de texte dans les rapports
- **Cause** : `_kv()` utilisait `addLayout(QHBoxLayout)` — les layouts ne sont pas supprimés par `takeAt()`
- **Fix** : `_kv()` crée un `QFrame` widget (supprimable par `deleteLater()`)

### 6. SMTP ne fonctionne pas (email non envoyé)
- **Cause** : `load_dotenv()` rechargé dans le subprocess mais les variables étaient déjà dans l'env
- **Fix** : GO.py injecte les variables `.env` directement dans l'environnement du subprocess uvicorn

### 7. DeepSeek API → connexion refusée (WinError 10054)
- **Cause** : DeepSeek appelé pour chaque facture → rate limit / connexion reset
- **Fix** : DeepSeek activé seulement si montant=0 ou fournisseur inconnu

### 8. NumPy incompatible avec OpenCV
- **Cause** : `pip install opencv-python` a upgradé NumPy vers 2.x incompatible
- **Fix** : `pip install numpy==1.26.4` puis `pip install opencv-python-headless==4.8.1.78`

### 9. App se ferme au login (NameError backup.py)
- **Cause** : variable `config_text` non définie (coupure lors de l'écriture du fichier)
- **Fix** : ajout de `config_text = QLabel(...)` avant `config_text.setWordWrap(True)`

### 10. App se ferme au clic Sauvegarder
- **Cause** : `_BackupWorker` appelait `api.me()` (requête HTTP) → exception non catchée dans le thread
- **Fix** : décodage JWT local (sans HTTP) + wrapper `try/except` absolu dans `run()`

### 11. MongoDB "non configuré" alors que configuré
- **Cause** : `get_backup_info()` timeout → retournait `{"configured": False}`
- **Fix** : vérification `os.getenv("MONGODB_URI")` avant d'appeler MongoDB

### 12. Extraction montant = 0 (tickets de caisse)
- **Cause** : regex ne couvrait pas `Total 22.40 e`, `Total (EURO) 6,40`, `Elec. Pay. EUR 24.75`
- **Fix** : nouveaux patterns + nettoyage OCR (filtrage lignes non-latines) + sanity check montants

### 13. Double instance de l'app
- **Cause** : double-clic sur le raccourci bureau
- **Fix** : verrou socket sur port 19876 — 2ème instance se ferme immédiatement

### 14. Backend réutilisé (ancien code en mémoire)
- **Cause** : GO.py détectait le port 8000 occupé et réutilisait l'ancien backend
- **Fix** : GO.py tue maintenant l'ancien process avant de démarrer un nouveau

### 15. Rapport filtre mois → anomalies incorrectes
- **Cause** : `nb_anomalies` filtré par période, pas le total global
- **Fix** : `get_stats()` retourne `nb_anomalies` (filtré) ET `nb_anomalies_total` (global)

---

## LANCEMENT

```bash
# Démarrage normal
python GO.py

# Ou double-clic sur Finalyse.lnk (bureau)
# Ou double-clic sur Finalyse.bat
```

**Prérequis système** :
- Python 3.10+
- Tesseract OCR installé (Windows : `C:\Users\...\AppData\Local\Programs\Tesseract-OCR\`)
- Ollama (optionnel, pour IA locale) : `ollama pull deepseek-r1:7b`

**Installation dépendances** :
```bash
pip install -r backend/requirements.txt
pip install PyQt6
```

---

## MODÈLES IA INSTALLÉS

| Modèle | Usage | Commande |
|--------|-------|---------|
| deepseek-r1:7b | Chat + extraction | `ollama pull deepseek-r1:7b` |
| mistral:latest | Chat fallback | déjà installé |
| llava:latest | Vision (images) | déjà installé |
| glm-ocr | OCR factures | `ollama pull glm-ocr` |

---

## BASE DE DONNÉES (SQLite)

```sql
users          -- id, email, password, nom, created_at
dossiers       -- id, user_id, nom, description, annee, mois
factures       -- id, user_id, dossier_id, nom_fichier, chemin, taille,
               -- annee, mois, fournisseur, date_facture, ref_facture,
               -- montant_ht, tva, montant_ttc, categorie, type_facture,
               -- statut, anomalies, confiance, texte_brut, analyse_ia
reset_tokens   -- id, user_id, token (6 chiffres), expires_at, used
```

**Statuts facture** : `en_attente` → `en_cours` → `traite` | `erreur`
**Types** : `entrante` (dépense) | `sortante` (recette)

---

*Généré le 17/04/2026 — Finalyse v1.0.0*
