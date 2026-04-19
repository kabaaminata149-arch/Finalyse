# Finalyse — Analyse Intelligente de Factures

Application de bureau pour l'analyse automatique de factures par IA.  
Traitement local via Ollama — 100% sécurisé, aucune donnée envoyée à des serveurs externes.

---

## ⬇️ Télécharger et Installer

### Windows (recommandé)

**[📥 Télécharger Finalyse_Setup.exe](https://1drv.ms/u/c/8ca7329dbc513199/IQBA3KYvRwZUQpGwf5T5RjOQAWSFC_QCK6aAo4pHTVJ_u24)**

1. Téléchargez `Finalyse_Setup.exe`
2. Double-cliquez pour installer (aucun prérequis nécessaire)
3. Lancez Finalyse depuis le raccourci sur le Bureau
4. Au premier lancement, installez Tesseract OCR et Ollama si demandé

> **Taille :** ~120 MB  
> **Système requis :** Windows 10/11 64-bit

---

## Fonctionnalités

-  **Import de factures** — PDF, images (JPG, PNG)
-  **Analyse IA automatique** — extraction des données (fournisseur, montant, TVA, date)
- **Rapports financiers** — compte de résultat, flux de trésorerie, anomalies
-  **Export** — PDF, CSV, envoi par email
-  **Sauvegarde cloud** — MongoDB Atlas (optionnel)
-  **Assistant IA** — chatbot financier intégré

---

## Lancer depuis le code source

### Prérequis
- Python 3.10+
- Tesseract OCR ([télécharger](https://github.com/UB-Mannheim/tesseract/wiki))
- Ollama ([télécharger](https://ollama.ai)) — optionnel

## Architecture

```
Finalyse/
├── GO.py                  # Lanceur principal
├── backend/               # API FastAPI
│   ├── main.py
│   ├── routes/            # auth, factures, dashboard, export, chatbot
│   ├── services/          # processor, ocr, vision, export_service
│   └── database/          # SQLite WAL
└── frontend/              # Interface PyQt6
    ├── main.py
    ├── pages/             # dashboard, import, rapports, historique
    └── theme.py           # Design system
```
