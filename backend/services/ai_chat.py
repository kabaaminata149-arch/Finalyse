"""
services/ai_chat.py — Chat IA hybride Finalyse
- En ligne  : DeepSeek API (deepseek-chat)
- Hors ligne: Ollama local (deepseek-r1:7b ou autre)
- Fallback  : réponses basiques depuis les données BD
"""
import os, json, logging
from typing import Optional

log = logging.getLogger("ai_chat")


def _build_system_prompt(context: dict) -> str:
    """Construit le prompt système avec toutes les données financières de l'utilisateur."""
    total_dep  = context.get("total_depenses", 0)
    total_rec  = context.get("total_recettes", 0)
    solde      = context.get("solde_net", total_rec - total_dep)
    nb_total   = context.get("nb_factures", 0)
    nb_traites = context.get("nb_traites", 0)
    nb_anom    = context.get("nb_anomalies", 0)
    fourn      = context.get("top_fournisseurs", [])
    cats       = context.get("categories", [])
    devise     = context.get("devise", "FCFA")

    fourn_str = "\n".join(
        f"  - {f.get('fournisseur','—')} : {f.get('total',0):,.0f} {devise} ({f.get('nb',0)} factures)"
        for f in fourn[:5]
    ) or "  Aucun fournisseur identifié"

    cats_str = "\n".join(
        f"  - {c.get('categorie','—')} : {c.get('total',0):,.0f} {devise}"
        for c in cats[:5]
    ) or "  Aucune catégorie"

    solde_txt = "excédentaire" if solde > 0 else ("déficitaire" if solde < 0 else "équilibré")

    return f"""Tu es l'assistant financier IA de Finalyse, une application d'analyse de factures.
Tu réponds en français, de façon concise, professionnelle et précise.
Tu as accès aux données financières réelles de l'utilisateur ci-dessous.
Utilise ces données pour répondre aux questions. Ne dis jamais que tu n'as pas accès aux données.

=== DONNÉES FINANCIÈRES ACTUELLES ===

FLUX FINANCIERS :
  Dépenses totales (factures entrantes) : {total_dep:,.0f} {devise}
  Recettes totales (factures sortantes) : {total_rec:,.0f} {devise}
  Solde net                             : {solde:+,.0f} {devise}
  Situation                             : {solde_txt}

FACTURES :
  Total importées  : {nb_total}
  Traitées         : {nb_traites}
  Anomalies        : {nb_anom}

TOP FOURNISSEURS :
{fourn_str}

RÉPARTITION PAR CATÉGORIE :
{cats_str}

=== FIN DES DONNÉES ===

Réponds aux questions en te basant sur ces données. Si l'utilisateur demande des conseils,
donne des recommandations concrètes basées sur les chiffres ci-dessus."""


async def _call_deepseek(question: str, context: dict, historique: list) -> Optional[str]:
    """Appel à l'API DeepSeek en ligne."""
    # Recharger .env avec chemin absolu
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        from dotenv import load_dotenv
        load_dotenv(_env, override=True)
    except Exception:
        pass
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import httpx
        system = _build_system_prompt(context)
        messages = [{"role": "system", "content": system}]
        for m in historique[-8:]:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.6,
                },
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            log.error("[DeepSeek] HTTP %d : %s", r.status_code, r.text[:200])
    except Exception as e:
        log.error("[DeepSeek] Erreur : %s", e)
    return None


async def _call_ollama(question: str, context: dict, historique: list) -> Optional[str]:
    """Appel à Ollama local."""
    try:
        from services.ollama import chat as ol_chat, is_available
        if not await is_available(timeout=2):
            return None
        return await ol_chat(question, context, historique)
    except Exception as e:
        log.error("[Ollama] Erreur : %s", e)
    return None


def _check_internet() -> bool:
    """Vérifie la connectivité internet rapidement."""
    try:
        import socket
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


def _fallback_local(question: str, ctx: dict) -> str:
    """Réponse basique depuis les données sans IA."""
    q          = question.lower()
    total_dep  = ctx.get("total_depenses", 0)
    total_rec  = ctx.get("total_recettes", 0)
    solde      = ctx.get("solde_net", total_rec - total_dep)
    nb         = ctx.get("nb_factures", 0)
    anom       = ctx.get("nb_anomalies", 0)
    fourn      = ctx.get("top_fournisseurs", [])
    devise     = ctx.get("devise", "FCFA")

    if any(w in q for w in ["solde","résultat","bénéfice","perte","profit"]):
        if solde > 0:
            return f"Votre solde net est excédentaire : +{solde:,.0f} {devise}.\nRecettes : {total_rec:,.0f} | Dépenses : {total_dep:,.0f}"
        elif solde < 0:
            return f"Votre solde net est déficitaire : {solde:,.0f} {devise}.\nVos dépenses dépassent vos recettes de {abs(solde):,.0f} {devise}."
        return f"Votre situation est équilibrée. Recettes = Dépenses = {total_dep:,.0f} {devise}."

    if any(w in q for w in ["dépense","charge","achat","fournisseur","entrante"]):
        top = fourn[0].get("fournisseur","—") if fourn else "—"
        return f"Dépenses totales : {total_dep:,.0f} {devise}\nPrincipal fournisseur : {top}"

    if any(w in q for w in ["recette","revenu","vente","client","sortante"]):
        return f"Recettes totales : {total_rec:,.0f} {devise} ({ctx.get('nb_factures',0)} factures)"

    if any(w in q for w in ["anomalie","problème","alerte","suspect","doublon"]):
        if anom == 0:
            return "Aucune anomalie détectée. Toutes vos factures sont conformes."
        return f"{anom} anomalie(s) détectée(s). Consultez la page Analyse IA pour les détails."

    if any(w in q for w in ["facture","nombre","combien","total"]):
        return f"Vous avez {nb} facture(s) importée(s).\nDépenses : {total_dep:,.0f} | Recettes : {total_rec:,.0f} {devise}"

    return (
        f"Assistant Finalyse — Données actuelles :\n"
        f"  Dépenses : {total_dep:,.0f} {devise}\n"
        f"  Recettes : {total_rec:,.0f} {devise}\n"
        f"  Solde    : {solde:+,.0f} {devise}\n"
        f"  Factures : {nb} | Anomalies : {anom}\n\n"
        f"Posez une question précise sur vos finances."
    )


async def chat(question: str, context: dict, historique: list) -> tuple[str, str]:
    """
    Retourne (réponse, source) où source = 'deepseek' | 'ollama' | 'local'
    Stratégie :
      1. Internet dispo + clé DeepSeek → DeepSeek API
      2. Ollama local dispo → Ollama
      3. Fallback local
    """
    has_internet = _check_internet()
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())

    if has_internet and has_deepseek:
        resp = await _call_deepseek(question, context, historique)
        if resp:
            return resp, "deepseek"

    resp = await _call_ollama(question, context, historique)
    if resp:
        return resp, "ollama"

    return _fallback_local(question, context), "local"
