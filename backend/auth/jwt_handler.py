"""auth/jwt_handler.py — JWT + bcrypt avec fallbacks robustes"""
import hashlib, hmac, secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, field_validator

import database.db as db
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_H

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ─── Hachage mot de passe ────────────────────────────────────────────────

def _bcrypt_ctx():
    try:
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        ctx.hash("test")  # test rapide
        return ctx
    except Exception:
        return None

_CTX = _bcrypt_ctx()

def hash_pwd(plain: str) -> str:
    if _CTX:
        return _CTX.hash(plain)
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260000)
    return f"pbkdf2${salt}${h.hex()}"

def verify_pwd(plain: str, hashed: str) -> bool:
    if hashed.startswith("pbkdf2$"):
        try:
            _, salt, stored = hashed.split("$")
            h = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260000)
            return hmac.compare_digest(h.hex(), stored)
        except Exception:
            return False
    if _CTX:
        try:
            return _CTX.verify(plain, hashed)
        except Exception:
            return False
    return False

# ─── JWT ─────────────────────────────────────────────────────────────────

def _jose():
    try:
        from jose import jwt as j, JWTError as Je
        return j, Je
    except Exception:
        return None, None

_JOSE, _JE = _jose()

def make_token(uid: int, email: str) -> str:
    exp  = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_H)
    data = {"sub": str(uid), "email": email,
            "exp": int(exp.timestamp()), "iat": int(datetime.utcnow().timestamp())}
    if _JOSE:
        return _JOSE.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    # fallback HS256 manuel
    import base64, json
    hdr = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b"=")
    bdy = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=")
    sig_raw = hmac.new(JWT_SECRET.encode(), hdr+b"."+bdy, hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(sig_raw).rstrip(b"=")
    return f"{hdr.decode()}.{bdy.decode()}.{sig.decode()}"

def parse_token(token: str) -> dict:
    err = HTTPException(status.HTTP_401_UNAUTHORIZED,
                        "Token invalide ou expiré.",
                        headers={"WWW-Authenticate":"Bearer"})
    try:
        if _JOSE:
            p = _JOSE.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        else:
            import base64, json
            parts = token.split(".")
            if len(parts) != 3: raise err
            pad = lambda s: s + "=" * (-len(s) % 4)
            p = json.loads(base64.urlsafe_b64decode(pad(parts[1])))
            if p.get("exp", 0) < datetime.utcnow().timestamp():
                raise err
        uid = int(p.get("sub", 0))
        if not uid: raise err
        return {"uid": uid, "email": p.get("email","")}
    except HTTPException:
        raise
    except Exception:
        raise err

def current_user(token: str = Depends(oauth2)) -> dict:
    p = parse_token(token)
    u = db.get_user_id(p["uid"])
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utilisateur introuvable.")
    return p

# ─── Schémas ─────────────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    email:    EmailStr
    password: str
    nom:      str = ""
    @field_validator("password")
    @classmethod
    def pwd_len(cls, v):
        import re
        if len(v) < 8:
            raise ValueError("Minimum 8 caractères.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Au moins une lettre majuscule requise.")
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{};':\"\\|,.<>/?]", v):
            raise ValueError("Au moins un caractère spécial requis.")
        if not re.search(r"\d", v):
            raise ValueError("Au moins un chiffre requis.")
        return v

class LoginIn(BaseModel):
    email:    EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    uid:          int
    email:        str
    nom:          str

class ResetReq(BaseModel):
    email: EmailStr

class ResetConfirm(BaseModel):
    token:        str
    new_password: str

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password:     str
    @field_validator("new_password")
    @classmethod
    def pwd_strong(cls, v):
        import re
        if len(v) < 8: raise ValueError("Minimum 8 caractères.")
        if not re.search(r"[A-Z]", v): raise ValueError("Au moins une majuscule.")
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{};':\"\\|,.<>/?]", v):
            raise ValueError("Au moins un caractère spécial.")
        if not re.search(r"\d", v): raise ValueError("Au moins un chiffre.")
        return v
