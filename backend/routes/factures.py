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

import database.db as db
from auth.jwt_handler import current_user
from config import UPLOAD_DIR, ALLOWED_EXT, MAX_MB

log = logging.getLogger("factures")
router = APIRouter(prefix="/api/factures", tags=["Factures"])


from pydantic import BaseModel


class StatutIn(BaseModel):
    statut: str


@router.post("/upload")
async def upload(
    bg: BackgroundTasks,
    files: List[UploadFile] = File(...),
    annee: int = Query(...),
    mois: Optional[int] = Query(None),
    dossier_id: Optional[int] = Query(None),
    dossier_nom: Optional[str] = Query(None),
    p: dict = Depends(current_user),
):
    uid = p["uid"]

    user_dir = Path(UPLOAD_DIR) / str(uid)
    user_dir.mkdir(parents=True, exist_ok=True)

    current_year = time.localtime().tm_year
    if annee < 2000 or annee > current_year + 1:
        raise HTTPException(400, f"Année invalide : {annee}")

    if mois is not None:
        if mois < 1 or mois > 12:
            raise HTTPException(400, f"Mois invalide : {mois}")

    # normalisation SAFE (IMPORTANT pour Pylance)
    safe_mois: Optional[int] = int(mois) if mois is not None else None
    safe_annee: int = int(annee)

    did: Optional[int] = dossier_id

    if did is not None:
        if not db.get_dossier(did, uid):
            raise HTTPException(404, f"Dossier #{did} introuvable.")

    elif dossier_nom and dossier_nom.strip():
        nom = dossier_nom.strip()

        # description safe
        desc = ""
        if safe_mois is not None:
            try:
                desc = f"{calendar.month_name[safe_mois]} {safe_annee}"
            except Exception:
                desc = f"{safe_mois}/{safe_annee}"
        else:
            desc = f"Year {safe_annee}"

        # FIX PYLANCE → mois toujours int ou None contrôlé
        did = db.create_dossier(
            uid,
            nom,
            desc,
            annee=safe_annee,
            mois=safe_mois if safe_mois is not None else 0
        )

        log.info("Dossier créé : '%s' (id=%d)", nom, did)

    uploaded, refused = [], []
    max_b = MAX_MB * 1024 * 1024

    for f in files:
        ext = Path(f.filename or "").suffix.lower()

        if ext not in ALLOWED_EXT:
            refused.append({
                "fichier": f.filename,
                "raison": f"Extension '{ext}' non autorisée"
            })
            continue

        content = await f.read()

        if len(content) > max_b:
            refused.append({
                "fichier": f.filename,
                "raison": f"Taille trop grande"
            })
            continue

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{ts}_{f.filename}"
        dest = user_dir / filename

        with open(dest, "wb") as fp:
            fp.write(content)

        fid = db.create_facture(
            uid,
            f.filename or filename,
            str(dest),
            len(content),
            dossier_id=did,
            annee=safe_annee,
            mois=safe_mois if safe_mois is not None else 0
        )

        from services.processor import process_invoice
        bg.add_task(process_invoice, fid, str(dest), safe_annee)

        uploaded.append({
            "id": fid,
            "nom": f.filename,
            "statut": "en_attente",
            "annee": safe_annee,
            "mois": safe_mois,
            "dossier_id": did,
            "message": "Analyse en arrière-plan"
        })

    return {
        "status": "processing",
        "importees": len(uploaded),
        "refusees": len(refused),
        "dossier_id": did,
        "factures": uploaded,
        "erreurs": refused,
    }


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
        raise HTTPException(400, f"Statut invalide")

    if not db.get_facture(fid, p["uid"]):
        raise HTTPException(404, "Facture introuvable.")

    db.set_statut(fid, body.statut)

    return {"message": f"Statut mis à jour : {body.statut}"}