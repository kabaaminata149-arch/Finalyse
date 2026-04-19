"""routes/auth.py — Inscription, connexion, reset mot de passe"""
import os, smtplib, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
import database.db as db
from auth.jwt_handler import (
    hash_pwd, verify_pwd, make_token, current_user,
    RegisterIn, LoginIn, TokenOut, ResetReq, ResetConfirm, ChangePasswordIn
)
from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS

log = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _send_reset_email(to_email: str, to_nom: str, token: str) -> bool:
    """Envoie le code de réinitialisation par email."""
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    log.info("[AUTH] SMTP check — user=%r configured=%s", smtp_user, bool(smtp_user and smtp_pass))

    if not smtp_user or not smtp_pass:
        log.warning("[AUTH] SMTP non configuré : user=%r pass=%r", bool(smtp_user), bool(smtp_pass))
        return False

    if not smtp_user or not smtp_pass:
        log.warning("[AUTH] SMTP non configuré : user=%r pass=%r", bool(smtp_user), bool(smtp_pass))
        return False
    try:
        log.info("[AUTH] Tentative envoi email reset à %s via %s:%s", to_email, smtp_host, smtp_port)
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"Finalyse <{SMTP_USER}>"
        msg["To"]      = to_email
        msg["Subject"] = "Finalyse — Réinitialisation de mot de passe"

        html = f"""
        <div style="font-family:sans-serif;max-width:520px;margin:auto;">
          <div style="background:#000666;color:white;padding:28px 32px;border-radius:12px 12px 0 0;">
            <h1 style="margin:0;font-size:22px;font-weight:800;">Finalyse</h1>
            <p style="margin:4px 0 0;opacity:.7;font-size:13px;">Réinitialisation de mot de passe</p>
          </div>
          <div style="padding:28px 32px;background:#f8f9fa;border-radius:0 0 12px 12px;">
            <p style="font-size:14px;">Bonjour <strong>{to_nom or to_email}</strong>,</p>
            <p style="font-size:13px;color:#454652;">
              Vous avez demandé la réinitialisation de votre mot de passe.<br>
              Utilisez le code ci-dessous dans l'application. Il expire dans <strong>2 heures</strong>.
            </p>
            <div style="background:white;border:2px solid #000666;border-radius:10px;
                        padding:20px;text-align:center;margin:24px 0;">
              <div style="font-size:11px;color:#666;letter-spacing:2px;margin-bottom:8px;">
                CODE DE RÉINITIALISATION
              </div>
              <div style="font-size:32px;font-weight:900;color:#000666;letter-spacing:8px;">
                {token}
              </div>
            </div>
            <p style="font-size:12px;color:#999;">
              Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.<br>
              Votre mot de passe ne sera pas modifié.
            </p>
          </div>
          <p style="text-align:center;font-size:11px;color:#bbb;margin-top:16px;">
            Finalyse © {datetime.now().year}
          </p>
        </div>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        log.info("[AUTH] Email reset envoyé avec succès à %s", to_email)
        return True
    except smtplib.SMTPAuthenticationError as e:
        log.error("[AUTH] SMTPAuthenticationError : %s", e)
        return False
    except Exception as e:
        log.error("[AUTH] Erreur envoi email reset : %s", e)
        return False


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn):
    if db.user_exists(data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email déjà utilisé.")
    uid   = db.create_user(data.email, hash_pwd(data.password), data.nom)
    token = make_token(uid, data.email)
    return TokenOut(access_token=token, uid=uid, email=data.email, nom=data.nom)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn):
    user = db.get_user_email(data.email)
    if not user or not verify_pwd(data.password, user["password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect.")
    token = make_token(user["id"], user["email"])
    return TokenOut(access_token=token, uid=user["id"],
                    email=user["email"], nom=user["nom"] or "")


@router.get("/me")
def get_me(p: dict = Depends(current_user)):
    u = db.get_user_id(p["uid"])
    if not u:
        raise HTTPException(404, "Introuvable.")
    return u


@router.post("/forgot-password")
def forgot_password(data: ResetReq):
    # Toujours retourner le même message pour ne pas révéler si l'email existe
    u = db.get_user_email(data.email)
    if not u:
        return {"message": "Si cet email existe, un code a été envoyé.", "email_sent": False}

    token = db.create_reset_token(u["id"])
    email_sent = _send_reset_email(data.email, u.get("nom", ""), token)

    if email_sent:
        log.info("[AUTH] Code reset envoyé à %s", data.email)
        return {
            "message": f"Un code de réinitialisation a été envoyé à {data.email}.",
            "email_sent": True,
        }
    else:
        # SMTP non configuré ou erreur — retourner le token en dev
        log.warning("[AUTH] Email non envoyé, token retourné en clair")
        return {
            "message": "Email non envoyé (SMTP). Code disponible ci-dessous.",
            "email_sent": False,
            "reset_token": token,
            "expires_in": "2 heures",
        }


@router.post("/reset-password")
def reset_password(data: ResetConfirm):
    uid = db.validate_reset_token(data.token)
    if not uid:
        raise HTTPException(400, "Code invalide ou expiré.")
    db.update_password(uid, hash_pwd(data.new_password))
    db.consume_reset_token(data.token)
    return {"message": "Mot de passe mis à jour avec succès."}


@router.post("/change-password")
def change_password(
    data: ChangePasswordIn,
    p: dict = Depends(current_user)
):
    u = db.get_user_id(p["uid"])
    if not u:
        raise HTTPException(404, "Utilisateur introuvable.")
    full = db.get_user_email(u["email"])
    if not verify_pwd(data.current_password, full["password"]):
        raise HTTPException(400, "Mot de passe actuel incorrect.")
    db.update_password(p["uid"], hash_pwd(data.new_password))
    return {"message": "Mot de passe modifié avec succès."}

