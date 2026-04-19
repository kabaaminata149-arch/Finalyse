"""routes/chatbot.py — Chat IA hybride (DeepSeek en ligne / Ollama hors ligne)"""
import logging
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

import database.db as db
from auth.jwt_handler import current_user

log    = logging.getLogger("chatbot")
router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


class Msg(BaseModel):
    role:    str
    content: str


class ChatIn(BaseModel):
    message:    str
    historique: List[Msg] = []


@router.post("")
@router.post("/", include_in_schema=False)
async def chat(data: ChatIn, p: dict = Depends(current_user)):
    context = db.get_context_for_chat(p["uid"])
    hist    = [{"role": m.role, "content": m.content} for m in data.historique[-8:]]

    try:
        from services.ai_chat import chat as ai_chat
        response, source = await ai_chat(data.message, context, hist)
    except Exception as e:
        log.error("Chat error: %s", e)
        from services.ai_chat import _fallback_local
        response = _fallback_local(data.message, context)
        source   = "local"

    return {
        "response": response,
        "source":   source,
        "context": {
            "total_depenses": context.get("total_depenses", 0),
            "total_recettes": context.get("total_recettes", 0),
            "solde_net":      context.get("solde_net", 0),
            "nb_factures":    context.get("nb_factures", 0),
        },
    }


@router.get("/status")
async def chat_status():
    import os
    try:
        from services.ollama import is_available, list_models
        ollama_ok = await is_available(timeout=3)
        models    = await list_models() if ollama_ok else []
    except Exception:
        ollama_ok = False
        models    = []

    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())

    from services.ai_chat import _check_internet
    internet = _check_internet()

    mode = "deepseek" if (internet and has_deepseek) else ("ollama" if ollama_ok else "local")

    return {
        "mode":          mode,
        "internet":      internet,
        "deepseek_key":  has_deepseek,
        "ollama":        "disponible" if ollama_ok else "indisponible",
        "models":        models,
        "message": {
            "deepseek": "IA DeepSeek en ligne active",
            "ollama":   "Ollama local actif",
            "local":    "Mode basique (pas d'IA)",
        }.get(mode, ""),
    }
