"""Authentification par clé d'API (Bearer) pour l'API publique v1.

Les clés sont désormais générées par les utilisateurs depuis l'interface et
stockées en base (`consommation.models.ApiKey`) : seul le **hash SHA-256** est
conservé, jamais la clé en clair. Cf. `models.py`.

Compatibilité : on garde aussi le support de la variable d'environnement
`API_KEYS` (format `libellé:sha256hex,...`), pour ne pas casser d'éventuelles
clés déjà distribuées avant la migration vers la base.

Politique d'accès (identique en dev et en prod) :
- Au moins une clé valide présentée (DB ou env) → OK, sinon 401.

Les clés se créent depuis la page `/api/` (connecté via l'IdP) ; en local sans
IdP, créer une `ApiKey` via `manage.py shell`.
"""
import hashlib
import os

from django.utils import timezone
from ninja.security import HttpBearer


def hash_key(raw_key: str) -> str:
    """Hash SHA-256 (hex) d'une clé brute — ce qui est stocké."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def load_env_keys() -> dict[str, str]:
    """Parse `API_KEYS` en {hash_sha256: libellé}. Entrées invalides ignorées.

    Chemin de compatibilité : la source principale est désormais la base.
    """
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


# Clés d'env chargées une fois (l'environnement ne change pas en cours d'exécution).
_ENV_KEYS = load_env_keys()


class ApiKeyAuth(HttpBearer):
    """Valide `Authorization: Bearer <clé>` contre la base puis l'env.

    Retourne une **identité** utilisée comme clé du quota de throttling, ou
    None → 401. Comportement identique en dev et en prod : une clé valide est
    toujours requise.

    Important : l'identité retournée est celle de l'**utilisateur**
    (`user:<sub>`), pas de la clé. Sinon le quota serait par-clé, et générer
    plusieurs clés multiplierait le débit autorisé (contournement du
    throttling). Toutes les clés d'un même user partagent donc un seul budget.
    """

    def authenticate(self, request, token):
        if not token:
            return None
        h = hash_key(token)

        # Source principale : la base. On filtre sur les clés non révoquées.
        from .models import ApiKey
        key = ApiKey.objects.filter(key_hash=h, revoked_at__isnull=True).first()
        if key is not None:
            # Trace de dernière utilisation (best-effort, sans bloquer la requête).
            ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
            # Identité = l'utilisateur, pour que le throttling soit partagé entre
            # toutes ses clés (cf. docstring). Repli sur la clé si pas de sub.
            return f"user:{key.user_sub}" if key.user_sub else f"key:{key.pk}"

        # Compat : clés héritées (env) — pas d'utilisateur, quota par hash.
        if h in _ENV_KEYS:
            return f"env:{h}"
        return None


def get_api_auth():
    """Auth à passer à NinjaAPI."""
    return ApiKeyAuth()
