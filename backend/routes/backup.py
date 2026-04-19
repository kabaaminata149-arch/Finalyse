"""routes/backup.py — Sauvegarde et restauration cloud MongoDB Atlas"""
import os
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from auth.jwt_handler import current_user
import database.db as db

router = APIRouter(prefix="/api/backup", tags=["Backup"])


class RestoreConfirm(BaseModel):
    confirm: bool = False


@router.get("/info")
def backup_info(p: dict = Depends(current_user)):
    """Infos sur la dernière sauvegarde cloud."""
    from services.cloud_backup import get_backup_info
    user = db.get_user_id(p["uid"])
    email = user["email"] if user else ""
    return get_backup_info(email)


@router.post("/save")
def backup_save(bg: BackgroundTasks, p: dict = Depends(current_user)):
    """Lance une sauvegarde manuelle en arrière-plan."""
    user = db.get_user_id(p["uid"])
    if not user:
        return {"ok": False, "error": "Utilisateur introuvable"}
    email = user["email"]
    uid   = p["uid"]

    # Vérifier que MongoDB est configuré
    mongo_uri = os.getenv("MONGODB_URI", "").strip()
    if not mongo_uri:
        return {
            "ok": False,
            "error": "MongoDB non configuré. Ajoutez MONGODB_URI dans backend/.env"
        }

    # Lancer en arrière-plan pour ne pas bloquer l'UI
    from services.cloud_backup import backup_user
    result = backup_user(uid, email)
    return result


@router.post("/restore")
def backup_restore(data: RestoreConfirm, p: dict = Depends(current_user)):
    """Restaure les données depuis le cloud."""
    if not data.confirm:
        return {"ok": False, "error": "Confirmez la restauration avec confirm=true"}

    user = db.get_user_id(p["uid"])
    if not user:
        return {"ok": False, "error": "Utilisateur introuvable"}

    from services.cloud_backup import restore_user
    return restore_user(p["uid"], user["email"])


@router.get("/check-auto")
def check_auto_backup(p: dict = Depends(current_user)):
    """Vérifie si une sauvegarde automatique est nécessaire."""
    user = db.get_user_id(p["uid"])
    if not user:
        return {"needed": False}
    from services.cloud_backup import should_backup
    interval = int(os.getenv("BACKUP_INTERVAL_DAYS", "7"))
    needed = should_backup(user["email"], interval)
    return {"needed": needed, "interval_days": interval}
