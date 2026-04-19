"""
services/ollama.py — Client IA Finalyse (Chat + Vision)
Modèles recommandés 2026 :
  Vision : glm-ocr, llama3.2-vision, granite3.2-vision
  Chat   : qwen2.5:7b, mistral, llama3.1:8b
"""
import json, re, base64, logging, os
from typing import Optional
from config import OLLAMA_URL, OLLAMA_MODEL

log = logging.getLogger("ollama")

OLLAMA_MODEL_VISION = os.getenv("OLLAMA_MODEL_VISION",
                      os.getenv("OLLAMA_MODEL", "glm-ocr"))


# ═══════════════════════════════════════════════════════════════════════════
# API PUBLIQUE
# ═══════════════════════════════════════════════════════════════════════════

async def is_available(timeout: float = 3.0) -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def list_models() -> list:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


async def chat(question: str, context: dict, historique: list) -> str:
    """Chat avec fallback immédiat si Ollama indisponible."""
    if not await is_available(timeout=2):
        return _fallback(question, context)

    modeles = await list_models()
    # Choisir le meilleur modèle chat disponible
    model   = _choisir_chat_model(modeles) or OLLAMA_MODEL

    hist_str = "\n".join(
        f"{'Utilisateur' if m['role']=='user' else 'Assistant'}: {m['content']}"
        for m in historique[-6:]
    )
    system = (
        f"Tu es l'assistant financier IA de Finalyse. "
        f"Tu réponds en français, de façon concise et professionnelle.\n\n"
        f"Données financières disponibles :\n"
        f"- Dépenses totales : {context.get('total_depenses',0):,.0f} FCFA\n"
        f"- Nombre de factures : {context.get('nb_factures',0)}\n"
        f"- Anomalies détectées : {context.get('nb_anomalies',0)}\n"
        f"- Principaux fournisseurs : "
        f"{[f.get('fournisseur','') for f in context.get('top_fournisseurs',[])[:3]]}"
    )
    prompt = f"{system}\n\nHistorique :\n{hist_str}\n\nQuestion : {question}"
    raw = await _call(prompt, model=model, fmt_json=False, timeout=90, temperature=0.6)
    return raw or _fallback(question, context)


def _choisir_chat_model(modeles: list[str]) -> Optional[str]:
    """Sélectionne le meilleur modèle chat disponible."""
    configured = OLLAMA_MODEL
    for m in modeles:
        if m.startswith(configured.split(":")[0]):
            return m
    preference = [
        "deepseek-r1:7b","deepseek-r1",
        "mistral",
        "qwen2.5:7b","qwen2.5",
        "llama3.1:8b","llama3.1",
        "phi4:14b","phi4","phi",
    ]
    for pref in preference:
        for m in modeles:
            if m.startswith(pref.split(":")[0]): return m
    return modeles[0] if modeles else None


async def _call(prompt: str, model: str = None, fmt_json=False,
                timeout=60, temperature=0.1) -> Optional[str]:
    model = model or OLLAMA_MODEL
    try:
        import httpx
        payload = {
            "model":   model,
            "prompt":  prompt,
            "stream":  False,
            "options": {
                "temperature":    temperature,
                "num_predict":    1024,
                "repeat_penalty": 1.1,
            },
        }
        if fmt_json: payload["format"] = "json"
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{OLLAMA_URL}/api/generate", json=payload)
            if r.status_code == 200:
                return r.json().get("response","").strip()
            log.error("[Ollama] HTTP %d : %s", r.status_code, r.text[:200])
    except Exception as e:
        log.error("[Ollama] Erreur : %s", e)
    return None


def _fallback(question: str, ctx: dict) -> str:
    """Réponse immédiate sans Ollama."""
    q     = question.lower()
    total = ctx.get("total_depenses", 0)
    nb    = ctx.get("nb_factures",    0)
    anom  = ctx.get("nb_anomalies",   0)
    fourn = ctx.get("top_fournisseurs", [])

    if any(w in q for w in ["total","dépense","montant","combien","coût","budget"]):
        return f"Vos dépenses totales s'élèvent à {total:,.0f} FCFA pour {nb} facture(s)."
    if any(w in q for w in ["anomalie","problème","alerte","erreur","suspect"]):
        return ("Aucune anomalie détectée dans vos factures." if anom == 0
                else f"{anom} anomalie(s) détectée(s). Consultez la page Analyse IA pour les détails.")
    if any(w in q for w in ["fournisseur","vendor","principal","top"]):
        if fourn:
            top = fourn[0].get("fournisseur","—")
            return f"Votre principal fournisseur est {top}."
        return "Aucun fournisseur identifié pour l'instant."
    if any(w in q for w in ["bonjour","salut","aide","hello","bonsoir"]):
        return (f"Bonjour ! Je suis l'assistant IA de Finalyse.\n"
                f"Vous avez {nb} facture(s) pour un total de {total:,.0f} FCFA.\n"
                f"(Mode basique — Ollama non démarré. "
                f"Lancez 'ollama pull qwen2.5:7b' pour activer l'IA complète.)")
    return (f"Assistant Finalyse (mode basique — Ollama non démarré).\n"
            f"{nb} factures | {total:,.0f} FCFA | {anom} anomalie(s)\n\n"
            f"Installez Ollama et lancez 'ollama pull qwen2.5:7b' pour activer l'IA complète.")
