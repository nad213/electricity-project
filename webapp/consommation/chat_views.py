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
from .chat import ChatService

logger = logging.getLogger(__name__)

# Garde-fous anti-abus (coût). Chaque message peut déclencher jusqu'à 10 appels
# Anthropic facturés : sans limite, une boucle de requêtes ou un historique
# énorme passe directement sur la facture. Mêmes compromis que le throttling de
# l'API (cf. api.py) : compteur dans le cache Django (LocMemCache par défaut =
# par process, donc limite effective × nombre de workers Gunicorn) — suffisant
# comme borne anti-abus, à brancher sur Redis pour un comptage exact.
# Seuils ajustables sans redéploiement via variables d'environnement (comme les
# THROTTLE_* de l'API).
CHAT_RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT", "15"))        # messages...
CHAT_RATE_WINDOW = int(os.getenv("CHAT_RATE_WINDOW", "600"))     # ...par fenêtre (s) → 15 / 10 min
# ~25k tokens : large pour 30 tours de conversation, borne le coût par requête.
MAX_BODY_BYTES = int(os.getenv("CHAT_MAX_BODY_BYTES", "100000"))


def _chat_rate_limited(user_sub: str) -> bool:
    """True si l'utilisateur a dépassé son quota de messages sur la fenêtre.

    Compteur best-effort dans le cache (incr atomique). `get_or_set` pose la clé
    avec son TTL au premier appel ; on n'incrémente qu'ensuite pour ne pas
    réarmer la fenêtre à chaque message.
    """
    key = f"chat_rl:{user_sub}"
    count = cache.get_or_set(key, 0, CHAT_RATE_WINDOW)
    if count >= CHAT_RATE_LIMIT:
        return True
    try:
        cache.incr(key)
    except ValueError:
        # La clé a expiré entre le get_or_set et l'incr : on repart à 1.
        cache.set(key, 1, CHAT_RATE_WINDOW)
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

    # Quota par utilisateur (anti-boucle). `sub` OIDC = identité stable.
    if _chat_rate_limited(user["sub"]):
        return JsonResponse(
            {"error": "Trop de messages, réessaie dans quelques minutes."},
            status=429,
        )

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return JsonResponse({"error": "messages requis (liste non vide)"}, status=400)

    try:
        service = ChatService()
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=503)

    try:
        result = service.run(messages)
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
