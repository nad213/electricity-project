"""Génère une clé d'API pour l'API publique v1.

    python manage.py generate_api_key alice

Affiche la clé EN CLAIR (à transmettre une seule fois au consommateur) et la
ligne `libellé:hash` à ajouter à la variable d'environnement `API_KEYS`.
La clé en clair n'est jamais stockée : seul son hash l'est.
"""
import secrets

from django.core.management.base import BaseCommand, CommandError

from consommation.api_auth import hash_key


class Command(BaseCommand):
    help = "Génère une clé d'API (Bearer) pour l'API publique v1."

    def add_arguments(self, parser):
        parser.add_argument("label", help="Libellé identifiant le consommateur (ex: alice)")

    def handle(self, *args, **options):
        label = options["label"].strip()
        if not label or ":" in label or "," in label:
            raise CommandError("Le libellé ne doit pas être vide ni contenir ':' ou ','.")

        raw_key = f"elf_live_{secrets.token_urlsafe(32)}"
        entry = f"{label}:{hash_key(raw_key)}"

        self.stdout.write(self.style.SUCCESS("\nClé d'API générée.\n"))
        self.stdout.write("  Clé (à transmettre au consommateur, NON stockée) :")
        self.stdout.write(self.style.WARNING(f"    {raw_key}\n"))
        self.stdout.write("  À ajouter à la variable d'environnement API_KEYS :")
        self.stdout.write(f"    {entry}\n")
        self.stdout.write(
            "  Usage côté client :\n"
            f"    Authorization: Bearer {raw_key}\n"
        )
