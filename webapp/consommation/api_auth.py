"""Authentification par clé d'API (Bearer) pour l'API publique v1.

Pas de base de données dans ce projet (`DATABASES = {}`) : les clés valides sont
déclarées en variable d'environnement `API_KEYS`, et on n'y stocke que le
**hash SHA-256** de chaque clé — jamais la clé en clair. Ainsi, même si l'env
fuite, les clés ne sont pas réutilisables.

Format de `API_KEYS` (séparateur virgule, un libellé par clé) :

    API_KEYS="alice:<sha256hex>,bob:<sha256hex>"

Génération d'une clé : `python manage.py generate_api_key <libellé>`.

Politique d'accès :
- Si au moins une clé est configurée → toute requête doit présenter
  `Authorization: Bearer <clé>` valide, sinon 401.
- Aucune clé configurée + DEBUG (dev local) → API ouverte (confort de dev).
- Aucune clé configurée + prod (DEBUG=False) → tout est rejeté (fail-safe
  fermé : on ne s'ouvre jamais en grand par oubli de config).
"""
import hashlib
import os

from django.conf import settings
from ninja.security import HttpBearer


def hash_key(raw_key: str) -> str:
    """Hash SHA-256 (hex) d'une clé brute — ce qui est stocké dans `API_KEYS`."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def load_keys() -> dict[str, str]:
    """Parse `API_KEYS` en {hash_sha256: libellé}. Entrées invalides ignorées."""
    raw = os.getenv("API_KEYS", "").strip()
    keys: dict[str, str] = {}
    if not raw:
        return keys
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        label, _, h = entry.partition(":")
        label, h = label.strip(), h.strip().lower()
        if label and h:
            keys[h] = label
    return keys


# Chargé une fois à l'import : l'environnement ne change pas en cours d'exécution.
_KEYS = load_keys()

# API ouverte uniquement en dev local sans aucune clé configurée.
DEV_OPEN = settings.DEBUG and not _KEYS


class ApiKeyAuth(HttpBearer):
    """Valide `Authorization: Bearer <clé>` contre les hash de `API_KEYS`.

    Retourne le **libellé** de la clé (utilisé comme identité pour le quota
    par-clé du throttling), ou None → 401.

    Les globales `DEV_OPEN` / `_KEYS` sont lues à chaque requête (et non figées à
    la construction), ce qui rend la politique d'accès patchable en test.
    """

    def __call__(self, request):
        if DEV_OPEN:
            # Dev local sans clé : on laisse passer (identité partagée).
            return "dev-open"
        return super().__call__(request)

    def authenticate(self, request, token):
        if not token:
            return None
        return _KEYS.get(hash_key(token))


def get_api_auth():
    """Auth à passer à NinjaAPI. Toujours une instance : le mode dev-open est
    géré dans `ApiKeyAuth.__call__` (lecture de `DEV_OPEN` à la requête)."""
    return ApiKeyAuth()
