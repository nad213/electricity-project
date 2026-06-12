"""Tests de l'API publique v1 : authentification par clé (401/200) et
throttling par clé (429).

On utilise le `TestClient` de Django Ninja (exécute la pipeline auth + throttle
sans le middleware HTTP, donc pas de redirection HTTPS à gérer) et on mocke la
couche `services` pour ne pas dépendre de S3/DuckDB. Les clés sont créées en
base (chemin principal de `ApiKeyAuth`), via une `TestCase` transactionnelle.
"""
import json
from datetime import date, timedelta
from unittest import mock

import pandas as pd
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from ninja.testing import TestClient

from . import api_auth
from . import chat_views
from . import views
from .api import api
from .models import ApiKey

# Clé de test et son hash, enregistrés en base pendant les tests.
VALID_KEY = "elf_test_key"
VALID_HASH = api_auth.hash_key(VALID_KEY)
AUTH_HEADER = {"Authorization": f"Bearer {VALID_KEY}"}

# Endpoint léger choisi pour les tests d'auth/throttle : une seule dépendance à mocker.
PARC_ENDPOINT = "/parc"
FAKE_PARC = pd.DataFrame([{"date": "2024-01", "filiere": "eolien", "parc_mw": 1000.0}])


def _make_key(raw_key: str, label: str) -> ApiKey:
    """Crée une clé active en base à partir de sa valeur brute."""
    return ApiKey.objects.create(
        user_sub=f"test|{label}",
        label=label,
        key_hash=api_auth.hash_key(raw_key),
        prefix=raw_key[:8],
    )


class ApiAuthTests(TestCase):
    """401 sans/avec mauvaise clé, 200 avec la bonne clé. Comportement
    identique en dev et en prod : une clé valide est toujours requise."""

    def setUp(self):
        cache.clear()  # repart d'un compteur de throttling vierge
        self.client = TestClient(api)
        _make_key(VALID_KEY, "test")
        patch = mock.patch("consommation.services.get_parc_installe_data", return_value=FAKE_PARC)
        patch.start()
        self.addCleanup(patch.stop)

    def test_sans_cle_renvoie_401(self):
        resp = self.client.get(PARC_ENDPOINT)
        self.assertEqual(resp.status_code, 401)

    def test_mauvaise_cle_renvoie_401(self):
        resp = self.client.get(PARC_ENDPOINT, headers={"Authorization": "Bearer mauvaise"})
        self.assertEqual(resp.status_code, 401)

    def test_cle_revoquee_renvoie_401(self):
        ApiKey.objects.filter(key_hash=VALID_HASH).update(revoked_at=timezone.now())
        resp = self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 401)

    def test_bonne_cle_renvoie_200(self):
        resp = self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 1)


class ApiThrottleTests(TestCase):
    """Au-delà du plafond de rafale, l'API renvoie 429 (compté par clé)."""

    def setUp(self):
        cache.clear()
        self.client = TestClient(api)
        _make_key(VALID_KEY, "alice")
        patch = mock.patch("consommation.services.get_parc_installe_data", return_value=FAKE_PARC)
        patch.start()
        self.addCleanup(patch.stop)

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
        _make_key("k2_test_key", "bob")
        limit = self._burst_limit()
        for _ in range(limit):  # alice consomme tout son quota
            self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER)
        self.assertEqual(self.client.get(PARC_ENDPOINT, headers=AUTH_HEADER).status_code, 429)
        # bob, lui, passe encore.
        resp = self.client.get(PARC_ENDPOINT, headers={"Authorization": "Bearer k2_test_key"})
        self.assertEqual(resp.status_code, 200)


class EnergieEndpointsTests(TestCase):
    """Les endpoints énergie convertissent MWh→GWh et renvoient un total par mois."""

    def setUp(self):
        cache.clear()
        self.client = TestClient(api)
        _make_key(VALID_KEY, "test")
        self.addCleanup(cache.clear)

    def test_energie_conso_convertit_en_gwh(self):
        fake = pd.DataFrame([
            {"mois": "2024-01", "energie_mwh": 42010000.0},
            {"mois": "2024-02", "energie_mwh": 39880000.0},
        ])
        with mock.patch("consommation.services.get_consommation_energie_mensuelle",
                        return_value=fake):
            resp = self.client.get(
                "/energie_conso?debut=2024-01-01&fin=2024-02-29", headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["unite"], "GWh")
        self.assertEqual(body["data"][0], {"mois": "2024-01", "energie_gwh": 42010.0})

    def test_energie_echange_import_export_gwh(self):
        fake = pd.DataFrame([
            {"mois": "2024-01", "import_mwh": 1250000.0, "export_mwh": 3400000.0},
        ])
        with mock.patch("consommation.services.get_echanges_energie_mensuelle",
                        return_value=fake):
            resp = self.client.get(
                "/energie_echange?debut=2024-01-01&fin=2024-01-31&pays=total",
                headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 200)
        row = resp.json()["data"][0]
        self.assertEqual(row, {"mois": "2024-01", "import_gwh": 1250.0, "export_gwh": 3400.0})

    def test_date_invalide_renvoie_400(self):
        resp = self.client.get("/energie_conso?debut=pas-une-date&fin=2024-01-31",
                               headers=AUTH_HEADER)
        self.assertEqual(resp.status_code, 400)


class ChatMessageGuardTests(TestCase):
    """Garde-fous anti-abus de /chat/message/ : auth (401), taille (413),
    quota par utilisateur (429). On mocke ChatService pour ne pas appeler
    l'API Anthropic."""

    URL = "/chat/message/"

    def setUp(self):
        cache.clear()  # compteur de rate-limit vierge
        self.client = Client()
        self.addCleanup(cache.clear)
        self.addCleanup(mock.patch.stopall)

    def _login(self, sub="auth0|alice"):
        """Simule un utilisateur connecté.

        Le backend de session est en cookies signés (pas de store côté serveur),
        donc poser la session via `self.client.session` ne se propage pas en
        test. On mocke directement la lecture de session de la vue : on teste
        ainsi les garde-fous, indépendamment d'Auth0. `stopall` (cf. setUp)
        nettoie le patch au teardown.
        """
        mock.patch.object(
            chat_views, "get_user_from_session",
            return_value={"sub": sub, "email": f"{sub}@example.com"},
        ).start()

    def _post(self, payload):
        return self.client.post(
            self.URL, data=json.dumps(payload), content_type="application/json"
        )

    def test_sans_auth_renvoie_401(self):
        # Pas de _login → get_user_from_session renvoie None (pas de session).
        resp = self._post({"messages": [{"role": "user", "content": "salut"}]})
        self.assertEqual(resp.status_code, 401)

    def test_body_trop_gros_renvoie_413(self):
        self._login()
        big = "x" * (chat_views.MAX_BODY_BYTES + 1)
        resp = self._post({"messages": [{"role": "user", "content": big}]})
        self.assertEqual(resp.status_code, 413)

    def test_quota_depasse_renvoie_429(self):
        self._login()
        ok = {"reply": "ok", "messages": [], "usage": {}}
        with mock.patch.object(chat_views, "ChatService") as MockSvc:
            MockSvc.return_value.run.return_value = ok
            payload = {"messages": [{"role": "user", "content": "salut"}]}
            # Les CHAT_RATE_LIMIT premières passent...
            for i in range(chat_views.CHAT_RATE_LIMIT):
                resp = self._post(payload)
                self.assertEqual(resp.status_code, 200, f"message {i + 1} inattendu")
            # ...la suivante est rejetée.
            resp = self._post(payload)
            self.assertEqual(resp.status_code, 429)

    def test_quota_par_utilisateur_independant(self):
        ok = {"reply": "ok", "messages": [], "usage": {}}
        payload = {"messages": [{"role": "user", "content": "salut"}]}
        with mock.patch.object(chat_views, "ChatService") as MockSvc:
            MockSvc.return_value.run.return_value = ok
            # alice épuise son quota
            self._login("auth0|alice")
            for _ in range(chat_views.CHAT_RATE_LIMIT):
                self._post(payload)
            self.assertEqual(self._post(payload).status_code, 429)
            # bob, lui, passe encore (quota indépendant) — on repointe le mock.
            self._login("auth0|bob")
            self.assertEqual(self._post(payload).status_code, 200)


class FiltresSessionTests(TestCase):
    """Mémoire par page des filtres : les params GET explicites gagnent et
    sont mémorisés en session, une navigation sans params relit la session,
    et une session périmée ou corrompue retombe silencieusement sur les
    défauts (jamais d'erreur)."""

    MIN = date(2020, 1, 1)
    MAX = date(2026, 6, 10)

    def _request(self, query="", session=None):
        request = RequestFactory().get("/conso/" + (f"?{query}" if query else ""))
        request.session = SessionStore()
        if session:
            request.session.update(session)
        return request

    # --- validate_and_get_dates ---

    def test_params_explicites_retournes_et_memorises(self):
        request = self._request("start_date=2026-01-01&end_date=2026-02-01")
        result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
        self.assertEqual(result, (date(2026, 1, 1), date(2026, 2, 1)))
        self.assertEqual(request.session["dates_conso"], {"start": "2026-01-01", "end": "2026-02-01"})

    def test_sans_params_relit_la_session(self):
        request = self._request(session={"dates_conso": {"start": "2025-06-01", "end": "2025-12-31"}})
        result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
        self.assertEqual(result, (date(2025, 6, 1), date(2025, 12, 31)))

    def test_sans_params_ni_session_defaut_15_jours(self):
        request = self._request()
        result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
        self.assertEqual(result, (self.MAX - timedelta(days=15), self.MAX))

    def test_session_perimee_recalee_dans_la_plage(self):
        # end mémorisé au-delà du max disponible → recalé sur max, sans erreur
        request = self._request(session={"dates_conso": {"start": "2026-06-01", "end": "2030-01-01"}})
        result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
        self.assertEqual(result, (date(2026, 6, 1), self.MAX))

    def test_session_entierement_hors_plage_defaut(self):
        request = self._request(session={"dates_conso": {"start": "2019-01-01", "end": "2019-12-31"}})
        result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
        self.assertEqual(result, (self.MAX - timedelta(days=15), self.MAX))

    def test_session_corrompue_defaut_sans_exception(self):
        for corrompu in ("n'importe quoi", {"start": "pas-une-date", "end": "2026-01-01"}, {"start": "2026-01-01"}):
            request = self._request(session={"dates_conso": corrompu})
            result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
            self.assertEqual(result, (self.MAX - timedelta(days=15), self.MAX))

    def test_params_explicites_prioritaires_sur_la_session(self):
        request = self._request(
            "start_date=2026-03-01&end_date=2026-04-01",
            session={"dates_conso": {"start": "2025-01-01", "end": "2025-02-01"}},
        )
        result = views.validate_and_get_dates(request, self.MIN, self.MAX, session_key="dates_conso")
        self.assertEqual(result, (date(2026, 3, 1), date(2026, 4, 1)))

    def test_sans_session_key_la_session_est_ignoree(self):
        # cas des exports CSV : ni lecture...
        request = self._request(session={"dates_conso": {"start": "2025-06-01", "end": "2025-12-31"}})
        result = views.validate_and_get_dates(request, self.MIN, self.MAX)
        self.assertEqual(result, (self.MAX - timedelta(days=15), self.MAX))
        # ...ni écriture
        request = self._request("start_date=2026-01-01&end_date=2026-02-01")
        views.validate_and_get_dates(request, self.MIN, self.MAX)
        self.assertNotIn("dates_conso", request.session)

    # --- resolve_multi_filter ---

    OPTIONS = {"nucleaire": "Nucléaire", "eolien": "Éolien", "solaire": "Solaire"}

    def test_filtre_explicite_memorise(self):
        request = self._request("start_date=2026-01-01&end_date=2026-02-01&filiere=eolien&filiere=solaire")
        selected = views.resolve_multi_filter(
            request, "filiere", "filiere_production", self.OPTIONS, default=["nucleaire"], label="Filière"
        )
        self.assertEqual(selected, ["eolien", "solaire"])
        self.assertEqual(request.session["filiere_production"], ["eolien", "solaire"])

    def test_filtre_tout_decoche_retombe_sur_le_defaut(self):
        # le formulaire soumet toujours les dates : leur présence sans le
        # param filiere = sélection vide explicite → défaut, mémorisé
        request = self._request("start_date=2026-01-01&end_date=2026-02-01")
        selected = views.resolve_multi_filter(
            request, "filiere", "filiere_production", self.OPTIONS, default=["nucleaire"], label="Filière"
        )
        self.assertEqual(selected, ["nucleaire"])
        self.assertEqual(request.session["filiere_production"], ["nucleaire"])

    def test_navigation_nue_relit_la_session_filtree(self):
        # 'charbon' n'existe plus dans les options → écarté sans erreur
        request = self._request(session={"filiere_production": ["eolien", "charbon"]})
        selected = views.resolve_multi_filter(
            request, "filiere", "filiere_production", self.OPTIONS, default=["nucleaire"], label="Filière"
        )
        self.assertEqual(selected, ["eolien"])

    def test_session_filtre_corrompue_defaut(self):
        request = self._request(session={"filiere_production": "pas-une-liste"})
        selected = views.resolve_multi_filter(
            request, "filiere", "filiere_production", self.OPTIONS, default=["nucleaire"], label="Filière"
        )
        self.assertEqual(selected, ["nucleaire"])

    def test_filtre_explicite_invalide_leve_valueerror(self):
        request = self._request("start_date=2026-01-01&end_date=2026-02-01&filiere=charbon")
        with self.assertRaises(ValueError):
            views.resolve_multi_filter(
                request, "filiere", "filiere_production", self.OPTIONS, default=["nucleaire"], label="Filière"
            )
