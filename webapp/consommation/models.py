"""Modèle des clés d'API de l'API publique v1.

Une `ApiKey` appartient à un utilisateur (identifié par son `sub` OIDC). On ne
stocke JAMAIS la clé en clair : seulement son hash SHA-256 (`key_hash`) et un
court préfixe (`prefix`) qui sert uniquement à reconnaître la clé dans la liste
de l'interface (la clé complète n'est montrée qu'une fois, à la génération).

La révocation est un soft-delete : on renseigne `revoked_at` au lieu de
supprimer la ligne, ce qui invalide la clé immédiatement tout en gardant une
trace (audit). Cf. consommation/api_auth.py pour la vérification à chaque requête.
"""
import hashlib
import secrets

from django.db import models
from django.utils import timezone


class ApiKey(models.Model):
    # Identifiant stable de l'utilisateur côté IdP (request.session['user']['sub']).
    user_sub = models.CharField(max_length=255, db_index=True)
    # Email au moment de la création — confort d'affichage / support, non clé.
    user_email = models.EmailField(blank=True)
    # Libellé choisi par l'utilisateur (ex: « script perso », « notebook »).
    label = models.CharField(max_length=100)
    # Hash SHA-256 (hex, 64 car.) de la clé brute. Unique = pas deux clés égales.
    key_hash = models.CharField(max_length=64, unique=True)
    # Préfixe affichable (ex: « elf_live_a1B2… ») pour reconnaître la clé.
    prefix = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    # Soft-delete : non nul = clé révoquée (refusée par l'auth).
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.label} ({self.prefix}…)"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=['revoked_at'])

    @staticmethod
    def generate_raw_key() -> str:
        """Nouvelle clé brute (jamais stockée telle quelle)."""
        return f"elf_live_{secrets.token_urlsafe(32)}"

    @classmethod
    def anonymize_user(cls, sub: str) -> int:
        """Efface les données personnelles d'un utilisateur (fermeture de compte).

        Révoque ses clés encore actives, puis vide `user_email` et remplace
        `user_sub` par un pseudonyme opaque (hash tronqué : garde les lignes
        d'un même ex-utilisateur groupées pour l'audit, sans réversibilité
        pratique). Les lignes sont conservées — cohérent avec le soft-delete.

        Returns:
            Le nombre de lignes anonymisées.
        """
        rows = cls.objects.filter(user_sub=sub)
        rows.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        pseudo = f"deleted:{hashlib.sha256(sub.encode()).hexdigest()[:12]}"
        return rows.update(user_sub=pseudo, user_email='')
