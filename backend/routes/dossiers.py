"""routes/dossiers.py — Folder management"""
import calendar
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

import database.db as db
from auth.jwt_handler import current_user

log    = logging.getLogger("dossiers")
router = APIRouter(prefix="/api/dossiers", tags=["Dossiers"])


class DossierIn(BaseModel):
    nom:         str
    description: str         = ""
    annee:       Optional[int] = None
    mois:        Optional[int] = None


@router.post("", status_code=201)
@router.post("/", status_code=201, include_in_schema=False)
def create(data: DossierIn, p: dict = Depends(current_user)):
    if not data.nom or not data.nom.strip():
        raise HTTPException(400, "Le nom du dossier est obligatoire.")
    if data.mois is not None and (data.mois < 1 or data.mois > 12):
        raise HTTPException(400, f"Mois invalide : {data.mois} (doit être entre 1 et 12)")

    desc = data.description or ""
    if data.annee and data.mois:
        try:
            mois_nom = calendar.month_name[data.mois]
            desc = f"{mois_nom} {data.annee}" + (f" — {desc}" if desc else "")
        except Exception:
            desc = f"{data.mois}/{data.annee}" + (f" — {desc}" if desc else "")
    elif data.annee:
        desc = f"Année {data.annee}" + (f" — {desc}" if desc else "")

    did = db.create_dossier(
        p["uid"], data.nom.strip(), desc,
        annee=data.annee, mois=data.mois,
    )
    return {
        "id":      did,
        "nom":     data.nom.strip(),
        "annee":   data.annee,
        "mois":    data.mois,
        "message": f"Dossier '{data.nom}' créé.",
    }


@router.get("")
@router.get("/", include_in_schema=False)
def list_dossiers(p: dict = Depends(current_user)):
    return {"dossiers": db.get_dossiers(p["uid"])}


@router.get("/{did}")
def get_dossier(did: int, p: dict = Depends(current_user)):
    d = db.get_dossier(did, p["uid"])
    if not d:
        raise HTTPException(404, "Dossier introuvable.")
    factures = db.get_factures(p["uid"], dossier_id=did)
    return {"dossier": d, "factures": factures}


@router.delete("/{did}")
def delete_dossier(did: int, p: dict = Depends(current_user)):
    if not db.delete_dossier(did, p["uid"]):
        raise HTTPException(404, "Dossier introuvable.")
    return {"message": "Dossier supprimé."}
