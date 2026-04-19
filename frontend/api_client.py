
import json
import os
import mimetypes
import uuid
import time
import logging
from typing import Optional, List
import urllib.request
import urllib.parse
from urllib import error as ue

log  = logging.getLogger("api_client")
BASE = "http://127.0.0.1:8000"


class ApiError(Exception):
    def __init__(self, msg: str, code: int = 0):
        super().__init__(msg)
        self.code = code


class Client:
    def __init__(self):
        self._token: Optional[str] = None
        self.base = BASE

    @property
    def ok(self) -> bool:
        return self._token is not None

    def set_token(self, t: str):
        self._token = t

    def logout(self):
        self._token = None

    # ── JSON request ──────────────────────────────────────────────────────
    def _req(self, method: str, path: str, body=None, timeout=20) -> dict:
        url = f"{self.base}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8") if body else None,
            method=method,
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept",       "application/json")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except ue.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("detail", str(e))
            except Exception:
                detail = f"Erreur serveur (HTTP {e.code})"
            raise ApiError(detail, e.code)
        except ue.URLError as e:
            reason = str(getattr(e, "reason", e))
            if "timed out" in reason.lower() or "timeout" in reason.lower():
                raise ApiError(
                    "The server is taking too long to respond.\n"
                    "Ensure the backend is running (GO.py)."
                )
            raise ApiError(
                f"Cannot reach the server.\n"
                f"Ensure the backend is running on {self.base}\n"
                f"(Lancez GO.py ou démarrez le backend manuellement)"
            )
        except Exception as e:
            raise ApiError(f"Erreur réseau inattendue : {e}")

    # ── Multipart upload ──────────────────────────────────────────────────
    def _upload(self, path: str, files: List[tuple]) -> dict:
        """Multipart/form-data upload. Returns immediately (< 2s)."""
        boundary = uuid.uuid4().hex.encode()
        parts    = []
        for field, fname, content, mime in files:
            safe_fname = fname.encode("ascii", "replace").decode("ascii")
            parts.append(
                b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="' +
                field.encode() + b'"; filename="' +
                safe_fname.encode() + b'"\r\n'
                b"Content-Type: " + mime.encode() + b"\r\n\r\n" +
                content + b"\r\n"
            )
        parts.append(b"--" + boundary + b"--\r\n")
        body = b"".join(parts)

        req = urllib.request.Request(
            f"{self.base}{path}", data=body, method="POST"
        )
        req.add_header("Content-Type",
                       f"multipart/form-data; boundary={boundary.decode()}")
        req.add_header("Accept", "application/json")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")

        try:
            # 30s: only file transfer time — AI analysis runs in background server-side
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except ue.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("detail", str(e))
            except Exception:
                detail = f"Erreur serveur (HTTP {e.code})"
            raise ApiError(detail, e.code)
        except ue.URLError as e:
            raise ApiError(f"Échec de l'upload : {getattr(e, 'reason', str(e))}")
        except Exception as e:
            raise ApiError(f"Erreur upload : {e}")

    # ── AUTH ──────────────────────────────────────────────────────────────
    def register(self, email: str, pwd: str, nom: str = "") -> dict:
        r = self._req("POST", "/api/auth/register",
                      {"email": email, "password": pwd, "nom": nom},
                      timeout=30)
        self._token = r["access_token"]
        return r

    def login(self, email: str, pwd: str) -> dict:
        r = self._req("POST", "/api/auth/login",
                      {"email": email, "password": pwd},
                      timeout=30)
        self._token = r["access_token"]
        return r

    def me(self) -> dict:
        return self._req("GET", "/api/auth/me", timeout=10)

    def forgot_password(self, email: str) -> dict:
        return self._req("POST", "/api/auth/forgot-password",
                         {"email": email}, timeout=15)

    def reset_password(self, token: str, new_pwd: str) -> dict:
        return self._req("POST", "/api/auth/reset-password",
                         {"token": token, "new_password": new_pwd}, timeout=15)

    def change_password(self, current_pwd: str, new_pwd: str) -> dict:
        return self._req("POST", "/api/auth/change-password",
                         {"current_password": current_pwd, "new_password": new_pwd}, timeout=15)

    # ── DOSSIERS ──────────────────────────────────────────────────────────
    def create_dossier(self, nom: str, desc: str = "",
                       annee: int = None, mois: int = None) -> dict:
        body = {"nom": nom, "description": desc}
        if annee: body["annee"] = annee
        if mois:  body["mois"]  = mois
        return self._req("POST", "/api/dossiers", body, timeout=10)

    def get_bilan(self, periode: str = "") -> dict:
        url = "/api/export/bilan"
        if periode:
            import urllib.parse
            url += f"?periode={urllib.parse.quote(periode)}"
        return self._req("GET", url, timeout=90)

    def get_dossiers(self) -> dict:
        return self._req("GET", "/api/dossiers", timeout=10)

    def get_dossier(self, did: int) -> dict:
        return self._req("GET", f"/api/dossiers/{did}", timeout=10)

    def delete_dossier(self, did: int) -> dict:
        return self._req("DELETE", f"/api/dossiers/{did}", timeout=10)

    # ── FACTURES ──────────────────────────────────────────────────────────
    def upload(self, paths: List[str],
               dossier_id:  Optional[int] = None,
               dossier_nom: Optional[str] = None,
               annee:       int           = None,
               mois:        Optional[int] = None) -> dict:
        from datetime import datetime
        if annee is None:
            annee = datetime.now().year

        files = []
        for p in paths:
            with open(p, "rb") as f:
                content = f.read()
            mime, _ = mimetypes.guess_type(p)
            files.append((
                "files",
                os.path.basename(p),
                content,
                mime or "application/octet-stream",
            ))

        url = f"/api/factures/upload?annee={annee}"
        if mois is not None:
            url += f"&mois={mois}"
        if dossier_id:
            url += f"&dossier_id={dossier_id}"
        elif dossier_nom:
            url += f"&dossier_nom={urllib.parse.quote(dossier_nom)}"

        return self._upload(url, files)

    def get_factures(self, statut=None, dossier_id=None,
                     annee=None, mois=None, limit=100) -> dict:
        url = f"/api/factures?limit={limit}"
        if annee is not None: url += f"&annee={annee}"
        if mois is not None:  url += f"&mois={mois}"
        if statut:            url += f"&statut={statut}"
        if dossier_id:        url += f"&dossier_id={dossier_id}"
        return self._req("GET", url, timeout=15)

    def get_facture(self, fid: int) -> dict:
        return self._req("GET", f"/api/factures/{fid}", timeout=10)

    def delete_facture(self, fid: int) -> dict:
        return self._req("DELETE", f"/api/factures/{fid}", timeout=10)

    def set_statut(self, fid: int, statut: str) -> dict:
        return self._req("PATCH", f"/api/factures/{fid}/statut",
                         {"statut": statut}, timeout=10)

    # ── DASHBOARD ─────────────────────────────────────────────────────────
    def dashboard(self, annee=None, mois=None) -> dict:
        url = "/api/dashboard"
        params = []
        if annee: params.append(f"annee={annee}")
        if mois:  params.append(f"mois={mois}")
        if params: url += "?" + "&".join(params)
        return self._req("GET", url, timeout=20)

    def analyse_stats(self) -> dict:
        return self._req("GET", "/api/analyse/stats", timeout=20)

    def anomalies(self) -> dict:
        return self._req("GET", "/api/analyse/anomalies", timeout=20)

    # ── CHAT ──────────────────────────────────────────────────────────────
    def chat(self, message: str, historique: list) -> dict:
        return self._req("POST", "/api/chat/",
                         {"message": message, "historique": historique},
                         timeout=100)

    def chat_status(self) -> dict:
        return self._req("GET", "/api/chat/status", timeout=5)

    # ── EXPORT ────────────────────────────────────────────────────────────
    def download_csv(self, save_path: str) -> bool:
        return self._download("/api/export/csv", save_path)

    def download_pdf(self, save_path: str, periode: str = "",
                     annee: int = 0, mois: int = 0) -> bool:
        params = []
        if periode: params.append(f"periode={urllib.parse.quote(periode)}")
        if annee:   params.append(f"annee={annee}")
        if mois:    params.append(f"mois={mois}")
        url = "/api/export/pdf" + (f"?{'&'.join(params)}" if params else "")
        return self._download(url, save_path)

    def send_report(self, to_email: str, to_name: str = "",
                    periode: str = "", message: str = "") -> dict:
        return self._req("POST", "/api/export/send-report", {
            "to_email": to_email,
            "to_name":  to_name,
            "periode":  periode,
            "message":  message,
        }, timeout=120)

    def _download(self, path: str, save_path: str, timeout: int = 120) -> bool:
        req = urllib.request.Request(f"{self.base}{path}")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if not data:
                raise ValueError("Réponse vide du serveur")
            with open(save_path, "wb") as f:
                f.write(data)
            return True
        except ue.HTTPError as e:
            try:
                detail = json.loads(e.read().decode()).get("detail", str(e))
            except Exception:
                detail = f"Erreur serveur HTTP {e.code}"
            raise ApiError(detail, e.code)
        except ue.URLError as e:
            raise ApiError(f"Connexion impossible : {getattr(e, 'reason', str(e))}")
        except Exception as e:
            raise ApiError(str(e))

    # ── UTILS ─────────────────────────────────────────────────────────────

    # ── BACKUP CLOUD ──────────────────────────────────────────────────────────
    def backup_info(self) -> dict:
        return self._req("GET", "/api/backup/info", timeout=10)

    def backup_save(self) -> dict:
        return self._req("POST", "/api/backup/save", timeout=60)

    def backup_restore(self) -> dict:
        return self._req("POST", "/api/backup/restore", {"confirm": True}, timeout=120)

    def backup_check_auto(self) -> dict:
        return self._req("GET", "/api/backup/check-auto", timeout=5)

    def ping(self, retries: int = 1) -> bool:
        for i in range(max(1, retries)):
            try:
                self._req("GET", "/health", timeout=3)
                return True
            except Exception:
                if i < retries - 1:
                    time.sleep(1)
        return False

    def wait_ready(self, max_seconds: int = 30) -> bool:
        for _ in range(max_seconds):
            try:
                self._req("GET", "/health", timeout=2)
                return True
            except Exception:
                time.sleep(1)
        return False


api = Client()
