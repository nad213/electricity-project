"""
Chatbot views — authenticated only.
"""
import json
import logging
import os

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .auth import get_user_from_session
from .chat import ChatBusyError, ChatService

logger = logging.getLogger(__name__)

# ~25k tokens : large pour 30 tours de conversation, borne le coût par requête.
MAX_BODY_BYTES = int(os.getenv("CHAT_MAX_BODY_BYTES", "100000"))

# Rate-limit par utilisateur (réintroduit le 2026-07-23) : sans plafond, un
# compte scripté peut vider le budget Mistral mensuel en quelques minutes.
# Deux fenêtres (heure / jour) via le cache Django — même approche que le
# throttling de l'API : compteur LocMem par process, donc limite effective
# multipliée par le nombre de workers Gunicorn. Approximation suffisante pour
# borner la dépense ; la surveillance fine reste côté console Mistral et logs
# `chat usage`. Seuils ajustables sans redéploiement via variables d'env
# (0 = chat coupé, kill switch).
CHAT_RATE_HOURLY = int(os.getenv("CHAT_RATE_HOURLY", "50"))
CHAT_RATE_DAILY = int(os.getenv("CHAT_RATE_DAILY", "100"))


def _rate_limit_exceeded(user_key: str) -> bool:
    """Compte les messages de `user_key` sur deux fenêtres (heure / jour).

    Le TTL du cache fait office de fenêtre : le compteur repart à zéro à
    expiration. True si l'une des limites est atteinte (le message courant
    n'est alors PAS compté).
    """
    fenetres = (
        (f"chat_rl_h:{user_key}", CHAT_RATE_HOURLY, 3600),
        (f"chat_rl_d:{user_key}", CHAT_RATE_DAILY, 86400),
    )
    for key, maxi, _ttl in fenetres:
        if (cache.get(key) or 0) >= maxi:
            return True
    for key, _maxi, ttl in fenetres:
        if not cache.add(key, 1, ttl):
            cache.incr(key)
    return False


@require_GET
@ensure_csrf_cookie
def chat_page(request):
    # Page accessible aux visiteurs : le template affiche une invitation à se
    # connecter/s'inscrire si l'utilisateur n'est pas authentifié.
    return render(request, "consommation/chat.html")


@require_POST
def chat_message(request):
    user = get_user_from_session(request)
    if user is None:
        return JsonResponse({"error": "Authentification requise"}, status=401)

    # Borne la taille AVANT de parser : un body démesuré = un coût de tokens
    # démesuré. Content-Length peut mentir/manquer, donc on se fie à len(body).
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse(
            {"error": "Conversation trop volumineuse — réinitialise-la."},
            status=413,
        )

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return JsonResponse({"error": "messages requis (liste non vide)"}, status=400)

    if _rate_limit_exceeded(user.get("sub") or user.get("email", "?")):
        logger.warning("Chat rate-limit dépassé user=%s", user.get("email"))
        return JsonResponse(
            {"error": "Limite de messages atteinte — réessaie plus tard."},
            status=429,
        )

    try:
        service = ChatService()
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=503)

    try:
        result = service.run(messages)
    except ChatBusyError:
        # 429 Mistral persistant malgré les retries : transitoire, pas interne.
        logger.warning("Chat busy (429 Mistral persistant) user=%s", user.get("email"))
        return JsonResponse(
            {"error": "Le service est très sollicité en ce moment — réessaie dans quelques instants."},
            status=429,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Chat error")
        return JsonResponse({"error": f"Erreur interne: {type(e).__name__}"}, status=500)

    if "error" in result:
        return JsonResponse(result, status=400)

    logger.info("chat usage user=%s usage=%s", request.session.get("user", {}).get("email"), result["usage"])
    return JsonResponse({
        "reply": result["reply"],
        "messages": result["messages"],
    })
