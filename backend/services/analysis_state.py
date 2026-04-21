"""
services/analysis_state.py — Gestion de l'état global d'analyse
Verrou par utilisateur : un seul lot peut être analysé à la fois.
"""
import threading
from typing import Dict, Optional
from datetime import datetime

# Structure par utilisateur
# { uid: { "active": bool, "total": int, "done": int, "errors": int,
#           "current_file": str, "started_at": str, "lot_nom": str } }
_state: Dict[int, dict] = {}
_lock = threading.Lock()


def start_analysis(uid: int, total: int, lot_nom: str = "") -> bool:
    """
    Démarre une analyse pour l'utilisateur.
    Retourne False si une analyse est déjà en cours.
    """
    with _lock:
        s = _state.get(uid, {})
        if s.get("active", False):
            return False
        _state[uid] = {
            "active":       True,
            "total":        total,
            "done":         0,
            "errors":       0,
            "current_file": "",
            "started_at":   datetime.utcnow().isoformat(),
            "lot_nom":      lot_nom,
        }
        return True


def update_progress(uid: int, current_file: str = "",
                    done_delta: int = 0, error_delta: int = 0):
    """Met à jour la progression après chaque fichier traité."""
    with _lock:
        s = _state.get(uid)
        if not s:
            return
        if current_file:
            s["current_file"] = current_file
        s["done"]   += done_delta
        s["errors"] += error_delta


def finish_analysis(uid: int):
    """Marque l'analyse comme terminée."""
    with _lock:
        s = _state.get(uid)
        if s:
            s["active"] = False
            s["current_file"] = ""


def get_state(uid: int) -> dict:
    """Retourne l'état courant de l'analyse pour un utilisateur."""
    with _lock:
        s = _state.get(uid, {})
        if not s:
            return {"active": False, "total": 0, "done": 0,
                    "errors": 0, "percent": 0, "current_file": "",
                    "lot_nom": ""}
        total   = s.get("total", 1) or 1
        done    = s.get("done", 0)
        percent = min(int(done / total * 100), 100)
        return {
            "active":       s.get("active", False),
            "total":        s.get("total", 0),
            "done":         done,
            "errors":       s.get("errors", 0),
            "percent":      percent,
            "current_file": s.get("current_file", ""),
            "lot_nom":      s.get("lot_nom", ""),
            "started_at":   s.get("started_at", ""),
        }


def is_analyzing(uid: int) -> bool:
    """Vérifie si une analyse est en cours pour cet utilisateur."""
    with _lock:
        return _state.get(uid, {}).get("active", False)
