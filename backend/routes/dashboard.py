"""routes/dashboard.py — Statistiques tableau de bord"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
import database.db as db
from auth.jwt_handler import current_user

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/dashboard")
def dashboard(
    annee: Optional[int] = Query(None),
    mois:  Optional[int] = Query(None),
    p: dict = Depends(current_user)
):
    return db.get_stats(p["uid"], annee=annee, mois=mois)


@router.get("/analyse/stats")
def analyse_stats(p: dict = Depends(current_user)):
    # BUG CORRIGE : limit=100 par défaut tronquait les stats au-delà de 100 factures
    factures = db.get_factures(p["uid"], limit=10000)
    import json
    traites  = [f for f in factures if f["statut"] == "traite"]
    confs    = [f["confiance"] for f in traites if f.get("confiance")]
    avg_conf = sum(confs)/len(confs) if confs else 0.0
    total_an = sum(len(f.get("anomalies",[])) for f in traites)
    return {
        "nb_total":         len(factures),
        "nb_traites":       len(traites),
        "nb_attente":       sum(1 for f in factures if f["statut"]=="en_attente"),
        "nb_erreur":        sum(1 for f in factures if f["statut"]=="erreur"),
        "nb_anomalies":     total_an,
        "confiance_moy":    round(avg_conf*100, 1),
        "gain_temps_h":     len(factures) * 5 // 60,
        "devise":           "FCFA",
    }


@router.get("/analyse/anomalies")
def anomalies(p: dict = Depends(current_user)):
    factures = db.get_factures(p["uid"], statut="traite")
    result   = [f for f in factures if f.get("anomalies")]
    return {
        "nb_total": sum(len(f["anomalies"]) for f in result),
        "factures": result,
    }
