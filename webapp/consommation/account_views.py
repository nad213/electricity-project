"""Fermeture de compte en self-service.

L'entrée « Supprimer mon compte » du menu utilisateur (GET) affiche une page de
confirmation ; le POST exécute la suppression en tout-ou-rien : anonymisation
des clés d'API locales puis suppression du compte chez l'IdP, dans une même
transaction — si l'appel Zitadel échoue, le ménage local est annulé et rien n'a
changé. Cf. consommation/idp_admin.py et docs/04-webapp.md.
"""
import requests
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .auth import get_user_from_session
from .idp_admin import delete_idp_user, is_account_deletion_enabled
from .models import ApiKey

# Mot à recopier dans le formulaire pour confirmer (garde-fou anti-clic réflexe).
CONFIRM_WORD = 'SUPPRIMER'


def delete_account(request: HttpRequest) -> HttpResponse:
    if not is_account_deletion_enabled():
        return redirect('consommation:accueil')
    user = get_user_from_session(request)
    if not user:
        return redirect('consommation:login')

    context = {
        'active_keys': ApiKey.objects.filter(
            user_sub=user['sub'], revoked_at__isnull=True
        ).count(),
        'confirm_word': CONFIRM_WORD,
    }

    if request.method != 'POST':
        return render(request, 'consommation/delete_account.html', context)

    if (request.POST.get('confirm') or '').strip() != CONFIRM_WORD:
        messages.error(
            request,
            f"Confirmation incorrecte — tape {CONFIRM_WORD} pour supprimer ton compte.",
        )
        return render(request, 'consommation/delete_account.html', context)

    try:
        with transaction.atomic():
            ApiKey.anonymize_user(user['sub'])
            # Appel réseau dans la transaction : c'est lui qui rend le flow
            # tout-ou-rien (échec IdP ⇒ rollback de l'anonymisation locale).
            delete_idp_user(user['sub'])
    except requests.RequestException:
        messages.error(
            request,
            "La suppression a échoué — rien n'a été modifié. "
            "Réessaie plus tard ou contacte-nous.",
        )
        return render(request, 'consommation/delete_account.html', context)

    # Pas de logout RP-initiated vers l'IdP : le compte n'existe plus, Zitadel
    # a terminé ses sessions à la suppression. On vide juste la session locale.
    request.session.flush()
    messages.success(request, "Ton compte a été supprimé.")
    return redirect('consommation:accueil')
