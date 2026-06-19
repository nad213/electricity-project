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
from . import chat
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
    l'API Mistral."""

    URL = "/chat/message/"

    def setUp(self):
        cache.clear()  # compteur de rate-limit vierge
        self.client = Client()
        self.addCleanup(cache.clear)
        self.addCleanup(mock.patch.stopall)

    def _login(self, sub="oidc|alice"):
        """Simule un utilisateur connecté.

        Le backend de session est en cookies signés (pas de store côté serveur),
        donc poser la session via `self.client.session` ne se propage pas en
        test. On mocke directement la lecture de session de la vue : on teste
        ainsi les garde-fous, indépendamment de l'IdP. `stopall` (cf. setUp)
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
            self._login("oidc|alice")
            for _ in range(chat_views.CHAT_RATE_LIMIT):
                self._post(payload)
            self.assertEqual(self._post(payload).status_code, 429)
            # bob, lui, passe encore (quota indépendant) — on repointe le mock.
            self._login("oidc|bob")
            self.assertEqual(self._post(payload).status_code, 200)


class ChatPayloadTests(TestCase):
    """Sérialisation des séries pour le chatbot (`chat._df_to_payload`).

    Régression : une série mensuelle/annuelle est un agrégat déjà compact —
    elle ne doit JAMAIS être sous-échantillonnée (sinon le modèle perd des mois
    entiers et hallucine, cf. fév 2020 reporté à 19 TWh au lieu de 43). Et les
    stats min/max doivent embarquer leur période pour ne pas être recollées au
    mauvais mois.
    """

    def _monthly_df(self, n=174):
        # Série > _MAX_ROWS pour déclencher l'ancien sous-échantillonnage.
        # Le min est posé sur un mois unique et identifiable (2026-06).
        rows = [{"year_month": f"hist-{i:03d}", "monthly_consumption": 40_000_000.0 + i}
                for i in range(n)]
        rows.append({"year_month": "2026-06", "monthly_consumption": 19_000_000.0})  # min
        rows.append({"year_month": "2017-01", "monthly_consumption": 57_000_000.0})  # max
        return pd.DataFrame(rows)

    def test_monthly_jamais_sous_echantillonne(self):
        df = self._monthly_df()
        self.assertGreater(len(df), chat._MAX_ROWS)  # sinon le test ne prouve rien
        with mock.patch("consommation.services.get_monthly_data", return_value=df):
            payload = chat._tool_get_consommation({"granularity": "monthly"})
        # Toutes les lignes sont là, aucun échantillon partiel.
        self.assertNotIn("sample", payload)
        self.assertEqual(len(payload["data"]), len(df))
        self.assertEqual(payload["rows_total"], len(df))

    def test_annual_jamais_sous_echantillonne(self):
        df = pd.DataFrame([{"year": 2012 + i, "yearly_consumption": 4.0e8 + i}
                           for i in range(chat._MAX_ROWS + 5)])
        with mock.patch("consommation.services.get_annual_data", return_value=df):
            payload = chat._tool_get_consommation({"granularity": "annual"})
        self.assertNotIn("sample", payload)
        self.assertEqual(len(payload["data"]), len(df))

    def test_stats_portent_la_periode_du_min_max(self):
        df = self._monthly_df()
        with mock.patch("consommation.services.get_monthly_data", return_value=df):
            payload = chat._tool_get_consommation({"granularity": "monthly"})
        stats = payload["stats"]
        self.assertEqual(stats["min_row"]["year_month"], "2026-06")
        self.assertEqual(stats["max_row"]["year_month"], "2017-01")
        self.assertEqual(stats["min"], 19_000_000.0)
        self.assertEqual(stats["max"], 57_000_000.0)

    def test_payload_serialisable_en_json(self):
        # _run_tool doit produire du JSON valide (types numpy compris).
        df = self._monthly_df()
        with mock.patch("consommation.services.get_monthly_data", return_value=df):
            out = json.loads(chat._run_tool("get_consommation", {"granularity": "monthly"}))
        self.assertEqual(out["rows_total"], len(df))

    def test_raw_reste_sous_echantillonne_au_dela_du_seuil(self):
        # La donnée brute demi-horaire, elle, garde son sous-échantillonnage.
        n = (chat._MAX_ROWS + 50)
        df = pd.DataFrame({
            "date_heure": pd.date_range("2024-01-01", periods=n, freq="30min"),
            "consommation": [50_000.0 + i for i in range(n)],
        })
        with mock.patch("consommation.services.get_puissance_data", return_value=df):
            payload = chat._tool_get_consommation(
                {"granularity": "raw", "start": "2024-01-01", "end": "2024-01-05"})
        self.assertIn("sample", payload)
        self.assertNotIn("data", payload)


class ChatParcToolTests(TestCase):
    """Tool `get_parc` : snapshot pmax (toutes filières) vs historique mensuel
    (éolien/solaire uniquement, filtrable par filière et période)."""

    def test_actuel_renvoie_pmax_toutes_filieres(self):
        pmax = {"nucleaire": 61370.0, "solaire": 17419.0}
        with mock.patch("consommation.services.get_parc_pmax", return_value=pmax):
            payload = chat._tool_get_parc({"mode": "actuel"})
        self.assertEqual(payload["mode"], "actuel")
        self.assertEqual(payload["parc"], pmax)

    def _histo_df(self):
        rows = []
        for m in range(1, 13):
            for fil, base in (("Eolien terrestre", 20_000.0), ("Solaire", 25_000.0)):
                rows.append({"date": f"2025-{m:02d}", "filiere": fil, "parc_mw": base + m})
        return pd.DataFrame(rows)

    def test_historique_filtre_filiere_et_periode(self):
        with mock.patch("consommation.services.get_parc_installe_data",
                        return_value=self._histo_df()):
            payload = chat._tool_get_parc(
                {"mode": "historique", "filiere": "Solaire", "granularity": "monthly",
                 "start": "2025-03", "end": "2025-05"})
        self.assertNotIn("sample", payload)  # agrégat mensuel : jamais samplé
        self.assertEqual([r["date"] for r in payload["data"]],
                         ["2025-03", "2025-04", "2025-05"])
        self.assertTrue(all(r["filiere"] == "Solaire" for r in payload["data"]))

    def test_historique_accepte_borne_yyyy_mm_dd(self):
        # Une borne ISO complète est tronquée à YYYY-MM sans planter.
        with mock.patch("consommation.services.get_parc_installe_data",
                        return_value=self._histo_df()):
            payload = chat._tool_get_parc(
                {"mode": "historique", "filiere": "Solaire", "granularity": "monthly",
                 "start": "2025-11-15"})
        self.assertEqual([r["date"] for r in payload["data"]], ["2025-11", "2025-12"])

    def test_historique_annual_par_defaut_marque_annee_partielle(self):
        # 2025 complet (jusqu'à déc) + 2026 partiel (jusqu'à avril seulement).
        rows = [{"date": f"2025-{m:02d}", "filiere": "Eolien terrestre",
                 "parc_mw": 20_000.0 + m} for m in range(1, 13)]
        rows += [{"date": f"2026-{m:02d}", "filiere": "Eolien terrestre",
                  "parc_mw": 23_000.0 + m} for m in range(1, 5)]
        with mock.patch("consommation.services.get_parc_installe_data",
                        return_value=pd.DataFrame(rows)):
            payload = chat._tool_get_parc({"mode": "historique"})
        self.assertNotIn("sample", payload)
        by_year = {r["year"]: r for r in payload["data"]}
        # Valeur annuelle = dernier mois connu de l'année.
        self.assertEqual(by_year["2025"]["value"], 20_012.0)
        self.assertEqual(by_year["2025"]["last_month"], "2025-12")
        self.assertFalse(by_year["2025"]["partial"])
        # L'année en cours est bien présente et marquée partielle.
        self.assertEqual(by_year["2026"]["value"], 23_004.0)
        self.assertEqual(by_year["2026"]["last_month"], "2026-04")
        self.assertTrue(by_year["2026"]["partial"])

    def test_mode_inconnu_renvoie_erreur(self):
        self.assertIn("error", chat._tool_get_parc({"mode": "n_importe_quoi"}))


class ChatEchangesEnergieToolTests(TestCase):
    """Tool `get_echanges_energie` : volumes import/export (MWh) mensuels/annuels."""

    def test_monthly_renvoie_import_export(self):
        fake = pd.DataFrame([
            {"mois": "2024-01", "import_mwh": 738725.0, "export_mwh": 580832.0},
            {"mois": "2024-02", "import_mwh": 100000.0, "export_mwh": 900000.0},
        ])
        with mock.patch("consommation.services.get_echanges_energie_mensuelle",
                        return_value=fake) as m:
            payload = chat._tool_get_echanges_energie(
                {"granularity": "monthly", "pays": "ech_comm_espagne",
                 "start": "2024-01-01", "end": "2024-02-29"})
        m.assert_called_once()
        self.assertEqual(payload["unit"], "MWh")
        self.assertEqual(payload["data"][0],
                         {"mois": "2024-01", "import_mwh": 738725.0, "export_mwh": 580832.0})

    def test_annual_utilise_le_bon_service(self):
        fake = pd.DataFrame([{"annee": "2024", "import_mwh": 346249.0, "export_mwh": 89291456.5}])
        with mock.patch("consommation.services.get_echanges_annual_import_export",
                        return_value=fake):
            payload = chat._tool_get_echanges_energie(
                {"granularity": "annual", "start": "2024-01-01", "end": "2024-12-31"})
        self.assertEqual(payload["data"][0]["annee"], "2024")

    def test_dates_manquantes_renvoie_erreur(self):
        payload = chat._tool_get_echanges_energie({"granularity": "monthly"})
        self.assertIn("error", payload)

    def test_pays_invalide_remonte_en_erreur(self):
        # le service lève ValueError → _run_tool doit la transformer en {"error": ...}
        def boom(*a, **k):
            raise ValueError("Pays invalide.")
        with mock.patch("consommation.services.get_echanges_annual_import_export",
                        side_effect=boom):
            out = json.loads(chat._run_tool(
                "get_echanges_energie",
                {"granularity": "annual", "pays": "ech_physiques",
                 "start": "2024-01-01", "end": "2024-12-31"}))
        self.assertIn("error", out)


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
