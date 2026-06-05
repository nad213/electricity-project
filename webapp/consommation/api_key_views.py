"""Gestion des clés d'API depuis l'interface (réservée aux connectés Auth0).

L'utilisateur génère/révoque ses propres clés sur la page API. La clé brute
n'est affichée qu'UNE fois, juste après création (passée via un flash en
session) : ensuite seul le préfixe est visible. Cf. consommation/models.py.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .api_auth import hash_key
from .auth import get_user_from_session
from .models import ApiKey

# Garde-fou : on borne le nombre de clés actives par utilisateur.
MAX_ACTIVE_KEYS = 10


@require_POST
def generate_api_key(request):
    user = get_user_from_session(request)
    if not user:
        return redirect('consommation:login')

    label = (request.POST.get('label') or '').strip()[:100]
    if not label:
        messages.error(request, "Donne un libellé à ta clé (ex. « notebook perso »).")
        return redirect('consommation:api')

    active = ApiKey.objects.filter(
        user_sub=user['sub'], revoked_at__isnull=True
    ).count()
    if active >= MAX_ACTIVE_KEYS:
        messages.error(
            request,
            f"Limite de {MAX_ACTIVE_KEYS} clés actives atteinte — révoque-en une d'abord.",
        )
        return redirect('consommation:api')

    raw_key = ApiKey.generate_raw_key()
    ApiKey.objects.create(
        user_sub=user['sub'],
        user_email=user.get('email') or '',
        label=label,
        key_hash=hash_key(raw_key),
        prefix=raw_key[:16],
    )

    # Affichée une seule fois au prochain rendu, puis effacée de la session.
    request.session['new_api_key'] = raw_key
    messages.success(
        request,
        "Clé créée. Copie-la maintenant : elle ne sera plus jamais affichée.",
    )
    return redirect('consommation:api')


@require_POST
def revoke_api_key(request, key_id):
    user = get_user_from_session(request)
    if not user:
        return redirect('consommation:login')

    # On ne révoque que SES propres clés (filtre sur user_sub).
    key = ApiKey.objects.filter(pk=key_id, user_sub=user['sub']).first()
    if key is None:
        messages.error(request, "Clé introuvable.")
    elif not key.is_active:
        messages.info(request, "Cette clé est déjà révoquée.")
    else:
        key.revoke()
        messages.success(request, f"Clé « {key.label} » révoquée.")
    return redirect('consommation:api')
