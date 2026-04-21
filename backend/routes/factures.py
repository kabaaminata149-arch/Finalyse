"""routes/factures.py — Upload, list, detail, delete"""
import os
import time
import calendar
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import (
    APIRouter, Depends, HTTPException,
    UploadFile, File, BackgroundTasks, Query,
)
from pydantic import BaseModel

import database.db as db
from auth.jwt_handler import current_user
from config import UPLOAD_DIR, ALLOWED_EXT, MAX_MB
from services.analysis_state import (
    start_analysis, finish_analysis, update_progress,
    is_analyzing, get_state
)

log = logging.getLogger("factures")
router = APIRouter(prefix="/api/factures", tags=["Factures"])


class StatutIn(BaseModel):
    statut: str


# ── Progression en temps réel ─────────────────────────────────────────────────

@router.get("/progress")
def get_progress(p: dict = Depends(current_user)):
    """Retourne la progression de l'analyse en cours pour cet utilisateur."""
    return get_state(p["uid"])


@router.get("/is-analyzing")
def check_analyzing(p: dict = Depends(current_user)):
    """Vérifie si une analyse est en cours."""
    return {"analyzing": is_analyzing(p["uid"])}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload(
    bg: BackgroundTasks,
    files: List[UploadFile] = File(...),
    annee: int = Query(...),
    mois: Optional[int] = Query(None),
    dossier_id: Optional[int] = Query(None),
    dossier_nom: Optional[str] = Query(None),
    lot_nom: Optional[str] = Query(None),
    p: dict = Depends(current_user),
):
    uid = p["uid"]

    # Vérifier si une analyse est déjà en cours
    if is_analyzing(uid):
        raise HTTPException(409, "Une analyse est déjà en cours. Attendez sa fin avant d'en lancer une nouvelle.")

    user_dir = Path(UPLOAD_DIR) / str(uid)
    user_dir.mkdir(parents=True, exist_ok=True)

    current_year = time.localtime().tm_year
    if annee < 2000 or annee > current_year + 1:
        raise HTTPException(400, f"Année invalide : {annee}")
    if mois is not None and (mois < 1 or mois > 12):
        raise HTTPException(400, f"Mois invalide : {mois}")

    safe_mois: Optional[int] = int(mois) if mois is not None else None
    safe_annee: int = int(annee)
    did: Optional[int] = dossier_id

    if did is not None:
        if not db.get_dossier(did, uid):
            raise HTTPException(404, f"Dossier #{did} introuvable.")
    elif dossier_nom and dossier_nom.strip():
        nom = dossier_nom.strip()
        desc = ""
        if safe_mois is not None:
            try:
                desc = f"{calendar.month_name[safe_mois]} {safe_annee}"
            except Exception:
                desc = f"{safe_mois}/{safe_annee}"
        else:
            desc = f"Year {safe_annee}"
        did = db.create_dossier(
            uid, nom, desc,
            annee=safe_annee,
            mois=safe_mois if safe_mois is not None else 0
        )
        log.info("Dossier créé : '%s' (id=%d)", nom, did)

    uploaded, refused = [], []
    max_b = MAX_MB * 1024 * 1024

    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            refused.append({"fichier": f.filename, "raison": f"Extension '{ext}' non autorisée"})
            continue
        content = await f.read()
        if len(content) > max_b:
            refused.append({"fichier": f.filename, "raison": "Taille trop grande"})
            continue

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{ts}_{f.filename}"
        dest = user_dir / filename
        with open(dest, "wb") as fp:
            fp.write(content)

        fid = db.create_facture(
            uid, f.filename or filename, str(dest), len(content),
            dossier_id=did, annee=safe_annee,
            mois=safe_mois if safe_mois is not None else 0
        )
        uploaded.append({
            "id": fid, "nom": f.filename, "statut": "en_attente",
            "annee": safe_annee, "mois": safe_mois,
            "dossier_id": did, "message": "Analyse en arrière-plan"
        })

    if uploaded:
        # Démarrer le verrou d'analyse
        nom_lot = lot_nom or dossier_nom or f"Lot {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        start_analysis(uid, len(uploaded), lot_nom=nom_lot)

        # Lancer le traitement en arrière-plan avec mise à jour de progression
        fids_paths = [(u["id"], str(user_dir / f"{u['nom']}")) for u in uploaded]
        bg.add_task(_process_batch, uid, uploaded, safe_annee)

    return {
        "status": "processing",
        "importees": len(uploaded),
        "refusees": len(refused),
        "dossier_id": did,
        "factures": uploaded,
        "erreurs": refused,
    }


async def _process_batch(uid: int, uploaded: list, annee: int):
    """Traite les factures une par une et met à jour la progression."""
    import asyncio
    from services.processor import process_invoice
    try:
        for item in uploaded:
            fid    = item["id"]
            record = db.get_facture(fid, uid)
            if not record:
                update_progress(uid, error_delta=1)
                continue
            nom = item.get("nom", "")
            update_progress(uid, current_file=nom)
            try:
                # process_invoice est synchrone — on le lance dans un thread
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, process_invoice, fid, record["chemin"], annee
                )
                update_progress(uid, done_delta=1)
            except Exception as e:
                log.error("[BATCH] fid=%d err=%s", fid, e)
                update_progress(uid, error_delta=1)
    finally:
        finish_analysis(uid)


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("")
def list_factures(
    annee: Optional[int] = Query(None),
    mois: Optional[int] = Query(None),
    statut: Optional[str] = Query(None),
    dossier_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    p: dict = Depends(current_user),
):
    return {
        "factures": db.get_factures(
            p["uid"], limit, statut, dossier_id,
            annee=annee, mois=mois,
        )
    }


@router.get("/{fid}")
def get_facture(fid: int, p: dict = Depends(current_user)):
    f = db.get_facture(fid, p["uid"])
    if not f:
        raise HTTPException(404, "Facture introuvable.")
    return f


@router.delete("/{fid}")
def delete_facture(fid: int, p: dict = Depends(current_user)):
    f = db.get_facture(fid, p["uid"])
    if not f:
        raise HTTPException(404, "Facture introuvable.")
    chemin = f.get("chemin", "")
    if chemin and os.path.exists(chemin):
        try:
            os.remove(chemin)
        except Exception:
            pass
    db.delete_facture(fid, p["uid"])
    return {"message": f"Facture #{fid} supprimée."}


@router.patch("/{fid}/statut")
def update_statut(fid: int, body: StatutIn, p: dict = Depends(current_user)):
    valides = {"en_attente", "en_cours", "traite", "valide", "rejete", "erreur"}
    if body.statut not in valides:
        raise HTTPException(400, "Statut invalide")
    if not db.get_facture(fid, p["uid"]):
        raise HTTPException(404, "Facture introuvable.")
    db.set_statut(fid, body.statut)
    return {"message": f"Statut mis à jour : {body.statut}"}
