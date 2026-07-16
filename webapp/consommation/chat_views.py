"""
Chatbot views — authenticated only.
"""
import json
import logging
import os

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .auth import get_user_from_session
from .chat import ChatBusyError, ChatService

logger = logging.getLogger(__name__)

# Pas de rate-limit applicatif (quotas utilisateur/global retirés le
# 2026-07-16, choix assumé) : la dépense Mistral n'est bornée que par l'usage
# réel — surveillance via la console Mistral et les logs `chat usage`.
# ~25k tokens : large pour 30 tours de conversation, borne le coût par requête.
MAX_BODY_BYTES = int(os.getenv("CHAT_MAX_BODY_BYTES", "100000"))


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
