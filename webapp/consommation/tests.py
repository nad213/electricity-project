"""Tests de l'API publique v1 : authentification par clé (401/200) et
throttling par clé (429).

On utilise le `TestClient` de Django Ninja (exécute la pipeline auth + throttle
sans le middleware HTTP, donc pas de redirection HTTPS à gérer) et on mocke la
couche `services` pour ne pas dépendre de S3/DuckDB.
"""
from unittest import mock

import pandas as pd
from django.core.cache import cache
from django.test import SimpleTestCase
from ninja.testing import TestClient

from . import api_auth
from .api import api

# Clé de test et son hash, injectés dans le trousseau pendant les tests.
VALID_KEY = "elf_test_key"
VALID_HASH = api_auth.hash_key(VALID_KEY)
AUTH_HEADER = {"Authorization": f"Bearer {VALID_KEY}"}

# Endpoint léger choisi pour les tests : une seule dépendance à mocker.
PARC_ENDPOINT = "/parc-installe"
FAKE_PARC = pd.DataFrame([{"date": "2024-01", "filiere": "eolien", "parc_mw": 1000.0}])


class ApiAuthTests(SimpleTestCase):
    """401 sans/avec mauvaise clé, 200 avec la bonne clé."""

    def setUp(self):
        cache.clear()  # repart d'un compteur de throttling vierge
        self.client = TestClient(api)
        # Force le mode « clé requise » indépendamment de DEBUG, avec une seule
        # clé valide connue.
        self._patches = [
            mock.patch.object(api_auth, "DEV_OPEN", False),
            mock.patch.object(api_auth, "_KEYS", {VALID_HASH: "test"}),
            mock.patch("consommation.services.get_parc_installe_data", return_value=FAKE_PARC),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def test_sans_cle_renvoie_401(self):
        resp = self.client.get(PARC_ENDPOINT)
        self.assertEqual(resp.status_code, 401)

    def test_mauvaise_cle_renvoie_401(self):
        resp = self.client.get(PARC_ENDPOINT, headers={"Authorization": "Bearer mauvaise"})
        self.assertEqual(resp.status_code, 401)

    def test_bonne_cle_renvoie_200(self):
        resp = self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)

    def test_dev_open_laisse_passer_sans_cle(self):
        # En dev local sans clé configurée, l'API est ouverte.
        with mock.patch.object(api_auth, "DEV_OPEN", True):
            resp = self.client.get(PARC_ENDPOINT)
        self.assertEqual(resp.status_code, 200)


class ApiThrottleTests(SimpleTestCase):
    """Au-delà du plafond de rafale, l'API renvoie 429 (compté par clé)."""

    def setUp(self):
        cache.clear()
        self.client = TestClient(api)
        self._patches = [
            mock.patch.object(api_auth, "DEV_OPEN", False),
            mock.patch.object(api_auth, "_KEYS", {VALID_HASH: "test"}),
            mock.patch("consommation.services.get_parc_installe_data", return_value=FAKE_PARC),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def _burst_limit(self):
        """Nombre de requêtes autorisées par la fenêtre de rafale (la + petite)."""
        return min(t.num_requests for t in api.throttle)

    def test_depassement_renvoie_429(self):
        limit = self._burst_limit()
        # Les `limit` premières passent...
        for i in range(limit):
            resp = self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
            self.assertEqual(resp.status_code, 200, f"requête {i + 1} inattendue")
        # ...la suivante est rejetée.
        resp = self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 429)

    def test_quota_par_cle_independant(self):
        # Une 2e clé épuise son propre quota sans être affectée par la 1re.
        with mock.patch.object(api_auth, "_KEYS", {VALID_HASH: "alice", api_auth.hash_key("k2"): "bob"}):
            limit = self._burst_limit()
            for _ in range(limit):  # alice consomme tout son quota
                self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
            self.assertEqual(self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER).status_code, 429)
            # bob, lui, passe encore.
            resp = self.client.get(PARC_ENDPOINT, headers={"Authorization": "Bearer k2"})
            self.assertEqual(resp.status_code, 200)
