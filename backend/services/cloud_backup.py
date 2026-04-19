"""
services/cloud_backup.py — Sauvegarde cloud MongoDB Atlas
Sauvegarde automatique des données utilisateur (factures, dossiers, rapports)
vers MongoDB Atlas. Restauration complète sur un nouvel appareil.
"""
import os, json, logging, hashlib
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("cloud_backup")


def _get_client():
    """Retourne un client MongoDB Atlas ou None si non configuré."""
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    load_dotenv(_env, override=True)
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=5000,
                             connectTimeoutMS=5000, socketTimeoutMS=8000)
        client.admin.command("ping")
        return client
    except Exception as e:
        log.warning("[BACKUP] MongoDB non accessible: %s", e)
        return None


def _get_db(client):
    db_name = os.getenv("MONGODB_DB", "finalyse")
    return client[db_name]


# ── Sauvegarde ────────────────────────────────────────────────────────────────

def backup_user(uid: int, email: str) -> dict:
    """
    Sauvegarde toutes les données d'un utilisateur vers MongoDB Atlas.
    Retourne {"ok": bool, "nb_factures": int, "nb_dossiers": int, "timestamp": str}
    """
    client = _get_client()
    if not client:
        return {"ok": False, "error": "MongoDB non configuré"}

    try:
        import database.db as db
        mongo_db = _get_db(client)

        now = datetime.utcnow().isoformat()

        # ── Factures ──────────────────────────────────────────────────────
        factures = db.get_factures(uid, limit=10000)
        # Ne pas sauvegarder le texte brut (trop lourd) ni le chemin local
        factures_clean = []
        for f in factures:
            fc = {k: v for k, v in f.items()
                  if k not in ("chemin", "texte_brut")}
            factures_clean.append(fc)

        # ── Dossiers ──────────────────────────────────────────────────────
        dossiers = db.get_dossiers(uid)

        # ── Stats ─────────────────────────────────────────────────────────
        stats = db.get_stats(uid)

        # ── Document de sauvegarde ────────────────────────────────────────
        backup_doc = {
            "uid":        uid,
            "email":      email,
            "timestamp":  now,
            "version":    "1.0",
            "factures":   factures_clean,
            "dossiers":   dossiers,
            "stats_snapshot": {
                "total_ttc":   stats["totaux"].get("total_ttc", 0),
                "nb_total":    stats["totaux"].get("nb_total", 0),
                "nb_traites":  stats["totaux"].get("nb_traites", 0),
                "nb_anomalies": stats.get("nb_anomalies", 0),
            },
        }

        # Upsert — remplace la sauvegarde existante pour cet utilisateur
        mongo_db.backups.replace_one(
            {"email": email},
            backup_doc,
            upsert=True
        )

        # Historique des sauvegardes (garder les 10 dernières)
        mongo_db.backup_history.insert_one({
            "email":     email,
            "uid":       uid,
            "timestamp": now,
            "nb_factures": len(factures_clean),
            "nb_dossiers": len(dossiers),
        })
        # Garder seulement les 10 dernières entrées d'historique
        history = list(mongo_db.backup_history.find(
            {"email": email}, sort=[("timestamp", -1)]
        ))
        if len(history) > 10:
            old_ids = [h["_id"] for h in history[10:]]
            mongo_db.backup_history.delete_many({"_id": {"$in": old_ids}})

        log.info("[BACKUP] Sauvegarde OK pour %s — %d factures, %d dossiers",
                 email, len(factures_clean), len(dossiers))

        client.close()
        return {
            "ok":          True,
            "nb_factures": len(factures_clean),
            "nb_dossiers": len(dossiers),
            "timestamp":   now,
        }

    except Exception as e:
        log.error("[BACKUP] Erreur sauvegarde: %s", e)
        try: client.close()
        except: pass
        return {"ok": False, "error": str(e)}


# ── Restauration ──────────────────────────────────────────────────────────────

def restore_user(uid: int, email: str) -> dict:
    """
    Restaure les données d'un utilisateur depuis MongoDB Atlas.
    Retourne {"ok": bool, "nb_factures": int, "nb_dossiers": int, "timestamp": str}
    """
    client = _get_client()
    if not client:
        return {"ok": False, "error": "MongoDB non configuré"}

    try:
        import database.db as db
        mongo_db = _get_db(client)

        backup = mongo_db.backups.find_one({"email": email})
        if not backup:
            client.close()
            return {"ok": False, "error": "Aucune sauvegarde trouvée pour cet email"}

        factures = backup.get("factures", [])
        dossiers = backup.get("dossiers", [])
        timestamp = backup.get("timestamp", "")

        # ── Restaurer les dossiers ────────────────────────────────────────
        dossier_id_map = {}  # ancien id → nouveau id
        for d in dossiers:
            old_id = d.get("id")
            new_id = db.create_dossier(
                uid,
                d.get("nom", "Dossier restauré"),
                d.get("description", ""),
                annee=d.get("annee"),
                mois=d.get("mois"),
            )
            if old_id:
                dossier_id_map[old_id] = new_id

        # ── Restaurer les factures ────────────────────────────────────────
        restored = 0
        for f in factures:
            old_did = f.get("dossier_id")
            new_did = dossier_id_map.get(old_did) if old_did else None

            fid = db.create_facture(
                uid,
                f.get("nom_fichier", "facture_restauree"),
                "",  # chemin vide — fichier non disponible
                f.get("taille", 0),
                dossier_id=new_did,
                annee=f.get("annee"),
                mois=f.get("mois"),
            )
            # Mettre à jour avec les données extraites
            db.update_facture(fid, {
                "fournisseur":  f.get("fournisseur", ""),
                "date_facture": f.get("date_facture", ""),
                "ref_facture":  f.get("ref_facture", ""),
                "montant_ht":   f.get("montant_ht", 0),
                "tva":          f.get("tva", 0),
                "montant_ttc":  f.get("montant_ttc", 0),
                "categorie":    f.get("categorie", "Autres"),
                "type_facture": f.get("type_facture", "entrante"),
                "statut":       f.get("statut", "traite"),
                "anomalies":    f.get("anomalies", []),
                "confiance":    f.get("confiance", 0),
                "analyse_ia":   f.get("analyse_ia", "Restauré depuis sauvegarde cloud"),
            })
            restored += 1

        log.info("[BACKUP] Restauration OK pour %s — %d factures, %d dossiers",
                 email, restored, len(dossiers))

        client.close()
        return {
            "ok":          True,
            "nb_factures": restored,
            "nb_dossiers": len(dossiers),
            "timestamp":   timestamp,
        }

    except Exception as e:
        log.error("[BACKUP] Erreur restauration: %s", e)
        try: client.close()
        except: pass
        return {"ok": False, "error": str(e)}


# ── Infos sauvegarde ──────────────────────────────────────────────────────────

def get_backup_info(email: str) -> dict:
    """Retourne les infos de la dernière sauvegarde."""
    client = _get_client()
    if not client:
        return {"configured": False}
    try:
        mongo_db = _get_db(client)
        backup = mongo_db.backups.find_one(
            {"email": email},
            {"timestamp": 1, "factures": 1, "dossiers": 1}
        )
        history = list(mongo_db.backup_history.find(
            {"email": email},
            {"timestamp": 1, "nb_factures": 1},
            sort=[("timestamp", -1)],
            limit=5
        ))
        client.close()
        if not backup:
            return {"configured": True, "has_backup": False}
        return {
            "configured":   True,
            "has_backup":   True,
            "timestamp":    backup.get("timestamp", ""),
            "nb_factures":  len(backup.get("factures", [])),
            "nb_dossiers":  len(backup.get("dossiers", [])),
            "history":      [{"timestamp": h["timestamp"],
                              "nb_factures": h.get("nb_factures", 0)}
                             for h in history],
        }
    except Exception as e:
        try: client.close()
        except: pass
        return {"configured": True, "error": str(e)}


# ── Vérification si sauvegarde nécessaire ─────────────────────────────────────

def should_backup(email: str, interval_days: int = 7) -> bool:
    """Retourne True si une sauvegarde automatique est nécessaire."""
    info = get_backup_info(email)
    if not info.get("configured") or not info.get("has_backup"):
        return True
    ts = info.get("timestamp", "")
    if not ts:
        return True
    try:
        last = datetime.fromisoformat(ts)
        return datetime.utcnow() - last > timedelta(days=interval_days)
    except Exception:
        return True
