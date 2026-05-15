"""
Chatbot views — authenticated only.
"""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .auth import is_authenticated
from .chat import ChatService

logger = logging.getLogger(__name__)


@require_GET
@ensure_csrf_cookie
def chat_page(request):
    if not is_authenticated(request):
        return redirect("consommation:login")
    return render(request, "consommation/chat.html")


@require_POST
def chat_message(request):
    if not is_authenticated(request):
        return JsonResponse({"error": "Authentification requise"}, status=401)

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
