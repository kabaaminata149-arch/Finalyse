"""database/db.py — Finalyse SQLite thread-safe database layer
WAL mode + thread-local connections for full concurrency during background AI processing.
"""
import sqlite3
import json
import threading
import secrets
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional
from config import DB_PATH

log = logging.getLogger("db")

# Thread-local connections: each thread gets its own connection
# No global lock, no blocking between the background processor and HTTP handlers
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")    # Concurrent reads + writes
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=30000")  # 30s before raising BusyError
        c.execute("PRAGMA synchronous=NORMAL")  # Balance performance/durability
        _local.conn = c
    return _local.conn


@contextmanager
def session():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Schema ────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    nom         TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dossiers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    nom         TEXT NOT NULL,
    description TEXT DEFAULT '',
    annee       INTEGER,
    mois        INTEGER,
    created_at  TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS factures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    dossier_id      INTEGER,
    nom_fichier     TEXT DEFAULT '',
    chemin          TEXT DEFAULT '',
    taille          INTEGER DEFAULT 0,
    annee           INTEGER NOT NULL DEFAULT 2024,
    mois            INTEGER,
    fournisseur     TEXT DEFAULT '',
    date_facture    TEXT DEFAULT '',
    ref_facture     TEXT DEFAULT '',
    montant_ht      REAL DEFAULT 0,
    tva             REAL DEFAULT 0,
    montant_ttc     REAL DEFAULT 0,
    categorie       TEXT DEFAULT 'Autres',
    type_facture    TEXT DEFAULT 'entrante',
    statut          TEXT DEFAULT 'en_attente',
    anomalies       TEXT DEFAULT '[]',
    confiance       REAL DEFAULT 0,
    texte_brut      TEXT DEFAULT '',
    analyse_ia      TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY(user_id)    REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(dossier_id) REFERENCES dossiers(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    token      TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used       INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_f_user       ON factures(user_id);
CREATE INDEX IF NOT EXISTS idx_f_dossier    ON factures(dossier_id);
CREATE INDEX IF NOT EXISTS idx_f_statut     ON factures(statut);
CREATE INDEX IF NOT EXISTS idx_f_annee      ON factures(annee);
CREATE INDEX IF NOT EXISTS idx_f_annee_mois ON factures(annee, mois);
CREATE INDEX IF NOT EXISTS idx_d_user       ON dossiers(user_id);
"""


def init():
    # Run migrations before schema
    _migrate()
    with session() as c:
        c.executescript(SCHEMA)

    # Create default admin user if none exists
    if not user_exists("admin@finalyse.com"):
        from auth.jwt_handler import hash_pwd
        create_user("admin@finalyse.com", hash_pwd("admin123"), "Administrator")
        log.info("Default user created: admin@finalyse.com / admin123")

    log.info("Database initialized at %s", DB_PATH)


def _migrate():
    """Safe column additions for existing databases."""
    migrations = [
        "ALTER TABLE factures ADD COLUMN annee INTEGER NOT NULL DEFAULT 2024",
        "ALTER TABLE factures ADD COLUMN mois INTEGER",
        "ALTER TABLE factures ADD COLUMN type_facture TEXT DEFAULT 'entrante'",
        "ALTER TABLE dossiers ADD COLUMN annee INTEGER",
        "ALTER TABLE dossiers ADD COLUMN mois INTEGER",
    ]
    for sql in migrations:
        try:
            with session() as c:
                c.execute(sql)
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                log.debug("Migration skipped: %s", e)


# ═══════════════ USERS ═══════════════

def user_exists(email: str) -> bool:
    with session() as c:
        return c.execute(
            "SELECT id FROM users WHERE email=?", (email,)
        ).fetchone() is not None


def create_user(email: str, hashed: str, nom: str = "") -> int:
    now = _now()
    with session() as c:
        cur = c.execute(
            "INSERT INTO users(email,password,nom,created_at) VALUES(?,?,?,?)",
            (email, hashed, nom, now)
        )
        return cur.lastrowid


def get_user_email(email: str) -> Optional[dict]:
    with session() as c:
        r = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    return dict(r) if r else None


def get_user_id(uid: int) -> Optional[dict]:
    with session() as c:
        r = c.execute(
            "SELECT id,email,nom,created_at FROM users WHERE id=?", (uid,)
        ).fetchone()
    return dict(r) if r else None


def update_password(uid: int, hashed: str):
    with session() as c:
        c.execute("UPDATE users SET password=? WHERE id=?", (hashed, uid))


# ═══════════════ RESET TOKENS ═══════════════

def create_reset_token(uid: int) -> str:
    """Génère un code à 6 chiffres, valable 2h."""
    import random
    code    = f"{random.randint(0, 999999):06d}"
    expires = (datetime.utcnow() + timedelta(hours=2)).isoformat()
    with session() as c:
        c.execute("UPDATE reset_tokens SET used=1 WHERE user_id=?", (uid,))
        c.execute(
            "INSERT INTO reset_tokens(user_id,token,expires_at) VALUES(?,?,?)",
            (uid, code, expires)
        )
    return code


def validate_reset_token(token: str) -> Optional[int]:
    with session() as c:
        r = c.execute(
            "SELECT user_id,expires_at,used FROM reset_tokens WHERE token=?", (token,)
        ).fetchone()
    if not r or r["used"]:
        return None
    if datetime.fromisoformat(r["expires_at"]) < datetime.utcnow():
        return None
    return r["user_id"]


def consume_reset_token(token: str):
    with session() as c:
        c.execute("UPDATE reset_tokens SET used=1 WHERE token=?", (token,))


# ═══════════════ DOSSIERS ═══════════════

def create_dossier(uid: int, nom: str, desc: str = "",
                   annee: int = None, mois: int = None) -> int:
    now = _now()
    with session() as c:
        cur = c.execute(
            "INSERT INTO dossiers(user_id,nom,description,annee,mois,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (uid, nom, desc, annee, mois, now)
        )
        return cur.lastrowid


def get_dossiers(uid: int) -> list:
    with session() as c:
        rows = c.execute(
            """SELECT d.*,
               COUNT(f.id)                                        AS nb_total,
               SUM(CASE WHEN f.statut='traite' THEN 1 ELSE 0 END) AS nb_traites,
               COALESCE(SUM(f.montant_ttc), 0)                    AS total_ttc
               FROM dossiers d
               LEFT JOIN factures f ON f.dossier_id = d.id
               WHERE d.user_id = ?
               GROUP BY d.id ORDER BY d.created_at DESC""",
            (uid,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_dossier(did: int, uid: int) -> Optional[dict]:
    with session() as c:
        r = c.execute(
            "SELECT * FROM dossiers WHERE id=? AND user_id=?", (did, uid)
        ).fetchone()
    return dict(r) if r else None


def delete_dossier(did: int, uid: int) -> bool:
    with session() as c:
        c.execute("UPDATE factures SET dossier_id=NULL WHERE dossier_id=?", (did,))
        cur = c.execute("DELETE FROM dossiers WHERE id=? AND user_id=?", (did, uid))
    return cur.rowcount > 0


# ═══════════════ FACTURES ═══════════════

def create_facture(uid: int, nom: str, chemin: str, taille: int,
                   dossier_id: Optional[int] = None,
                   annee: int = None, mois: Optional[int] = None) -> int:
    now = _now()
    if annee is None:
        annee = datetime.utcnow().year
    with session() as c:
        cur = c.execute(
            """INSERT INTO factures(user_id,dossier_id,nom_fichier,chemin,
               taille,annee,mois,statut,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,'en_attente',?,?)""",
            (uid, dossier_id, nom, chemin, taille, annee, mois, now, now)
        )
        return cur.lastrowid


def update_facture(fid: int, data: dict):
    """
    BUG CORRIGE : annee et mois ne sont plus ecrasés ici.
    Ils sont définis à la création et ne doivent jamais changer.
    L'ancienne version les mettait à NULL car processor.py ne les passait pas.
    """
    now = _now()
    with session() as c:
        c.execute(
            """UPDATE factures SET
               fournisseur=?,date_facture=?,ref_facture=?,
               montant_ht=?,tva=?,montant_ttc=?,
               categorie=?,type_facture=?,statut=?,anomalies=?,
               confiance=?,texte_brut=?,analyse_ia=?,
               updated_at=?
               WHERE id=?""",
            (
                data.get("fournisseur", ""),
                data.get("date_facture", ""),
                data.get("ref_facture", ""),
                data.get("montant_ht", 0),
                data.get("tva", 0),
                data.get("montant_ttc", 0),
                data.get("categorie", "Autres"),
                data.get("type_facture", "entrante"),
                data.get("statut", "traite"),
                json.dumps(data.get("anomalies", []), ensure_ascii=False),
                data.get("confiance", 0),
                data.get("texte_brut", "")[:5000],
                data.get("analyse_ia", ""),
                now, fid,
            )
        )


def set_statut(fid: int, statut: str):
    with session() as c:
        c.execute(
            "UPDATE factures SET statut=?,updated_at=? WHERE id=?",
            (statut, _now(), fid)
        )


def get_factures(uid: int, limit=100, statut=None, dossier_id=None,
                 annee=None, mois=None) -> list:
    with session() as c:
        q = "SELECT * FROM factures WHERE user_id=?"
        p = [uid]
        if annee is not None:
            q += " AND (annee=? OR (annee=0 AND date_facture LIKE ?))"
            p.append(annee); p.append(f"%{annee}%")
        if mois is not None:
            mois_cond = "(date_facture LIKE ? OR date_facture LIKE ? OR date_facture LIKE ?)"
            q += f" AND {mois_cond}"
            p.extend([f"%/{mois:02d}/%", f"%-{mois:02d}-%", f"%/{mois}/%"])
        if statut:
            q += " AND statut=?"; p.append(statut)
        if dossier_id:
            q += " AND dossier_id=?"; p.append(dossier_id)
        q += " ORDER BY created_at DESC LIMIT ?"; p.append(limit)
        rows = c.execute(q, p).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["anomalies"] = json.loads(d.get("anomalies") or "[]")
        except Exception:
            d["anomalies"] = []
        result.append(d)
    return result


def get_facture(fid: int, uid: int) -> Optional[dict]:
    with session() as c:
        r = c.execute(
            "SELECT * FROM factures WHERE id=? AND user_id=?", (fid, uid)
        ).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["anomalies"] = json.loads(d.get("anomalies") or "[]")
    except Exception:
        d["anomalies"] = []
    return d


def delete_facture(fid: int, uid: int) -> bool:
    with session() as c:
        cur = c.execute(
            "DELETE FROM factures WHERE id=? AND user_id=?", (fid, uid)
        )
    return cur.rowcount > 0


# ═══════════════ DASHBOARD ═══════════════

def get_stats(uid: int, annee: int = None, mois: int = None) -> dict:
    # Construire le filtre WHERE
    # On filtre sur annee/mois de la facture OU sur la date_facture extraite
    base_filter = "user_id=?"
    base_params = [uid]
    if annee:
        # Filtre sur l'année d'import OU l'année dans la date_facture
        base_filter += " AND (annee=? OR (annee=0 AND date_facture LIKE ?))"
        base_params.append(annee)
        base_params.append(f"%{annee}%")
    if mois:
        # Filtre sur le mois : chercher dans date_facture
        # Formats : JJ/MM/AAAA, AAAA-MM-JJ, DD Month YYYY
        mois_patterns = [
            f"/{mois:02d}/",   # JJ/MM/AAAA
            f"-{mois:02d}-",   # AAAA-MM-JJ
            f"/{mois}/",       # JJ/M/AAAA sans zero
        ]
        mois_cond = " OR ".join(["date_facture LIKE ?"] * len(mois_patterns))
        base_filter += f" AND ({mois_cond})"
        base_params.extend([f"%{p}%" for p in mois_patterns])

    with session() as c:
        tot = dict(c.execute(
            f"""SELECT COUNT(*) nb_total,
               COALESCE(SUM(montant_ttc),0) total_ttc,
               COALESCE(SUM(tva),0) total_tva,
               COALESCE(SUM(montant_ht),0) total_ht,
               COUNT(CASE WHEN statut='traite'     THEN 1 END) nb_traites,
               COUNT(CASE WHEN statut='en_attente' THEN 1 END) nb_attente,
               COUNT(CASE WHEN statut='erreur'     THEN 1 END) nb_erreur
               FROM factures WHERE {base_filter}""", base_params
        ).fetchone())

        flux = dict(c.execute(
            f"""SELECT
               COALESCE(SUM(CASE WHEN type_facture='entrante' THEN montant_ttc ELSE 0 END),0) depenses_ttc,
               COALESCE(SUM(CASE WHEN type_facture='entrante' THEN montant_ht  ELSE 0 END),0) depenses_ht,
               COALESCE(SUM(CASE WHEN type_facture='entrante' THEN tva         ELSE 0 END),0) depenses_tva,
               COUNT(CASE WHEN type_facture='entrante' THEN 1 END) nb_entrantes,
               COALESCE(SUM(CASE WHEN type_facture='sortante' THEN montant_ttc ELSE 0 END),0) recettes_ttc,
               COALESCE(SUM(CASE WHEN type_facture='sortante' THEN montant_ht  ELSE 0 END),0) recettes_ht,
               COALESCE(SUM(CASE WHEN type_facture='sortante' THEN tva         ELSE 0 END),0) recettes_tva,
               COUNT(CASE WHEN type_facture='sortante' THEN 1 END) nb_sortantes
               FROM factures WHERE {base_filter} AND statut='traite'""", base_params
        ).fetchone())

        fourn = [dict(r) for r in c.execute(
            f"""SELECT fournisseur,COUNT(*) nb,SUM(montant_ttc) total
               FROM factures WHERE {base_filter} AND fournisseur!='' AND statut='traite'
               GROUP BY fournisseur ORDER BY total DESC LIMIT 10""", base_params
        ).fetchall()]

        cats = [dict(r) for r in c.execute(
            f"""SELECT categorie,COUNT(*) nb,SUM(montant_ttc) total
               FROM factures WHERE {base_filter} AND statut='traite'
               GROUP BY categorie ORDER BY total DESC""", base_params
        ).fetchall()]

        evol = [dict(r) for r in c.execute(
            f"""SELECT substr(created_at,1,7) mois,
               COUNT(*) nb,SUM(montant_ttc) total,
               COALESCE(SUM(CASE WHEN type_facture='entrante' THEN montant_ttc ELSE 0 END),0) depenses,
               COALESCE(SUM(CASE WHEN type_facture='sortante' THEN montant_ttc ELSE 0 END),0) recettes
               FROM factures WHERE {base_filter} AND statut='traite'
               GROUP BY mois ORDER BY mois DESC LIMIT 6""", base_params
        ).fetchall()]

        anom_nb = c.execute(
            f"""SELECT COUNT(*) nb FROM factures
               WHERE {base_filter} AND anomalies!='[]'
               AND anomalies!='' AND statut='traite'""", base_params
        ).fetchone()["nb"]

        # Total global des anomalies (toutes périodes confondues)
        anom_total = c.execute(
            """SELECT COUNT(*) nb FROM factures
               WHERE user_id=? AND anomalies!='[]'
               AND anomalies!='' AND statut='traite'""", [uid]
        ).fetchone()["nb"]

        derniers = get_factures(uid, limit=8, annee=annee, mois=mois)

    solde_net = flux["recettes_ttc"] - flux["depenses_ttc"]

    return {
        "totaux":         tot,
        "flux":           {**flux, "solde_net": solde_net},
        "fournisseurs":   fourn,
        "categories":     cats,
        "evolution":      list(reversed(evol)),
        "nb_anomalies":   anom_nb,        # filtré par période
        "nb_anomalies_total": anom_total, # toutes périodes
        "dernieres":      derniers,
        "devise":         "FCFA",
    }


def get_context_for_chat(uid: int) -> dict:
    stats = get_stats(uid)
    flux  = stats.get("flux", {})
    return {
        "total_depenses":   flux.get("depenses_ttc", stats["totaux"]["total_ttc"]),
        "total_recettes":   flux.get("recettes_ttc", 0),
        "solde_net":        flux.get("solde_net", 0),
        "nb_factures":      stats["totaux"]["nb_total"],
        "nb_traites":       stats["totaux"]["nb_traites"],
        "nb_anomalies":     stats["nb_anomalies"],
        "top_fournisseurs": stats["fournisseurs"][:5],
        "categories":       stats["categories"],
        "devise":           "FCFA",
    }


def _now() -> str:
    return datetime.utcnow().isoformat()
