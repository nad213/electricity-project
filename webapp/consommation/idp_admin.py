"""Opérations d'administration côté IdP — SPÉCIFIQUE ZITADEL.

Contrairement à `auth.py` (OIDC standard, provider-agnostic via discovery), la
suppression d'un utilisateur n'est PAS couverte par OpenID Connect : on appelle
ici l'API de management de Zitadel (User Service v2). Le `sub` OIDC est l'ID
utilisateur Zitadel. Si l'IdP change un jour (Keycloak, Auth0…), seul ce module
est à réécrire.

Authentification : PAT d'un service user Zitadel (rôle Org User Manager),
fourni via la variable d'env ``ZITADEL_SERVICE_TOKEN``. ⚠️ Le PAT a une date
d'expiration fixée à sa création — cf. docs/06-deploiement.md.
"""
import requests
from django.conf import settings

# Seconds to wait on network calls to the IdP before giving up.
_HTTP_TIMEOUT = 10


def is_account_deletion_enabled() -> bool:
    """La fermeture de compte in-app n'est proposée que si le PAT est configuré
    (masquée en dev local sans token, ou avec un IdP non-Zitadel)."""
    return bool(settings.ZITADEL_SERVICE_TOKEN)


def delete_idp_user(sub: str) -> None:
    """Supprime définitivement l'utilisateur `sub` chez Zitadel.

    Lève ``requests.RequestException`` (HTTP != 2xx ou erreur réseau) en cas
    d'échec — l'appelant doit traiter l'échec comme bloquant (rollback du
    ménage local, cf. account_views.py).
    """
    url = f"{settings.OIDC_ISSUER.rstrip('/')}/v2/users/{sub}"
    resp = requests.delete(
        url,
        headers={'Authorization': f'Bearer {settings.ZITADEL_SERVICE_TOKEN}'},
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
