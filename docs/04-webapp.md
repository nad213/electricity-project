# Webapp Django

Application Django 6 (`webapp/`), une seule app : `consommation`. Elle lit les Parquet produits par l'ETL, trace des graphiques Plotly, et expose une API publique et un chatbot. Prod : Gunicorn + WhiteNoise sur Clever Cloud.

## Structure du module `consommation/`

| Fichier | Rôle |
|---|---|
| `services.py` | Accès aux données : requêtes SQL DuckDB sur les Parquet (une fonction par besoin) |
| `data_cache.py` | Cache local des Parquet S3 (voir ci-dessous) |
| `views.py` | Pages + construction des figures Plotly |
| `constants.py` | Couleurs, configs graphiques, définitions des filières |
| `api.py` / `api_auth.py` / `api_key_views.py` | API publique v1 (voir [05-api.md](05-api.md)) |
| `models.py` | `ApiKey` — unique modèle en base |
| `auth.py` / `auth_views.py` / `context_processors.py` | OIDC : login/callback/logout, infos utilisateur dans les templates |
| `idp_admin.py` / `account_views.py` | Fermeture de compte (suppression chez Zitadel + anonymisation locale) |
| `chat.py` / `chat_views.py` | Chatbot (boucle tool-use Mistral) |
| `management/commands/refresh_data.py` | Rafraîchit le cache Parquet (`--force` pour tout retélécharger) |

## Pages

- **Accueil** (`/`) — dashboard du jour (rendu SSR)
- **Consommation** (`/consommation/`), **Production** (`/production/`), **Échanges** (`/echanges/`) — courbes détaillées / mensuelles / annuelles, avec exports CSV
- **API** (`/api/`) — self-service de clés d'API (réservé aux connectés)
- **Chat** (`/chat/`) — chatbot (réservé aux connectés)

### Thème sombre (`static/css/style.css`)

L'UI s'appuie sur Tabler (CDN, thème clair par défaut) passé en sombre par remap des variables `--tblr-*` dans `:root` + surcharges par composant. **Le remap est partiel** : un composant Tabler utilisé pour la première fois peut tomber sur des variables non remappées et sortir blanc avec du texte clair illisible (cas des modales, corrigé en 7759e86). Au premier usage d'un composant, vérifier son rendu et ajouter la section correspondante dans `style.css`. Certains utilitaires Tabler (`.link-*`) sont posés en `!important` — la surcharge doit l'être aussi.

### Chargement AJAX des graphiques

Consommation, Production et Échanges retournent d'abord un squelette (formulaire + `<div aria-busy>`), puis `KiloWatch.loadCharts()` (`static/js/charts.js`) refait la même requête en XHR au `DOMContentLoaded`. Les vues détectent `X-Requested-With: XMLHttpRequest` et renvoient alors un `JsonResponse({'charts': {id: {data, layout}}})` au lieu du HTML. L'accueil reste en SSR.

## Cache Parquet local (`data_cache.py`)

DuckDB pourrait lire S3 directement (`httpfs`) mais chaque requête paierait la latence réseau alors que les données ne changent que quelques fois par jour. Le cache télécharge chaque fichier une fois dans `PARQUET_CACHE_DIR` (défaut `/tmp/parquet_cache`) et ne revérifie l'ETag S3 qu'au plus une fois par `PARQUET_CACHE_CHECK_TTL` secondes.

Cycle de `ensure_local_parquet(key)` :

1. **Fast path** : fichier local présent et vérifié il y a moins de TTL → chemin local, zéro appel réseau.
2. Sinon, sous un lock par clé (double-checked locking, workers Gunicorn) : `head_object` S3 → ETag identique ⇒ rafraîchit le timestamp ; ETag différent ou fichier absent ⇒ retéléchargement atomique (`.tmp` + `rename`).
3. **Dégradation** : sur erreur réseau, sert la copie locale périmée ; sans copie locale, retourne l'URL `s3://…` et `get_duckdb_connection()` bascule sur `httpfs`.

Au démarrage (hors `migrate`/`collectstatic`/`test`), `apps.py` lance un thread daemon qui pré-télécharge tous les fichiers de `settings.S3_PATHS` (warmup), puis **re-vérifie les ETags en boucle** toutes les `PARQUET_CACHE_REFRESH_INTERVAL` secondes (défaut 600 ; `0` = warmup seul). Ce refresh de fond passe outre le TTL (`force_check`) : c'est lui qui pilote la fraîcheur effective, et les requêtes utilisateur restent sur le fast path en permanence — personne ne paie le `head_object` ni le retéléchargement dans le chemin d'une requête. Le TTL ne sert plus que de filet de sécurité si le thread meurt. Chaque worker Gunicorn fait tourner sa propre boucle (les `head_object` dupliqués sont négligeables ; un double téléchargement est sans danger, l'écriture est atomique). `/tmp` étant éphémère sur Clever Cloud, chaque déploiement repart d'un cache propre.

Défauts : TTL et interval à 600 s dans `settings.py` ; en prod le TTL est monté à **3600 s** (variable d'env Clever) puisqu'il n'est qu'un filet de sécurité.

## Cache du dashboard accueil (`views.py`)

L'accueil est l'endpoint le plus coûteux de la webapp (~1 s CPU : `get_dashboard_data`, import/export annuel des échanges, nid d'abeille, parc ENR — mesures dans `notes/capacite_charge_clever_2026-07-18.md`) et il est identique pour tous les visiteurs. La vue `accueil` met donc son **contexte calculé** en cache Django (`default`, LocMem) :

- **Clé** = date locale + ETags des 9 Parquet sources (via `data_cache.get_etag()`, lecture des `.meta.json` sans appel S3). Un nouvel ETL change l'ETag ⇒ nouvelle clé ⇒ recalcul au visiteur suivant ; la date dans la clé évite de servir la « photo du jour » de la veille après minuit.
- **TTL 1 h** (`ACCUEIL_CACHE_TTL`) en filet de sécurité.
- Le rendu du template reste par requête (la navbar dépend de la session) ; un contexte vide (S3 indisponible) n'est jamais caché.
- LocMem étant par process, chaque worker a son cache — exact tant qu'on est mono-worker, et au pire un recalcul par worker.

Effet mesuré en local : ~2,3 s le premier hit, ~8 ms ensuite.

## Sessions et authentification

- **Sessions en cookies signés** (`SESSION_ENGINE = signed_cookies`) — aucun stockage serveur. Expiration glissante d'**1 h** (`SESSION_COOKIE_AGE = 3600` + `SESSION_SAVE_EVERY_REQUEST`), qui expire aussi les filtres mémorisés. L'historique local du chat expire pareillement après 1 h d'inactivité (côté client).
- **OIDC générique** (Authlib) : tous les endpoints sont découverts via `/.well-known/openid-configuration` de `OIDC_ISSUER` — n'importe quel IdP conforme (Zitadel, Keycloak, Auth0…) fonctionne en changeant trois variables d'env (`OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`). L'identité en session (`user.sub`, email) sert de propriétaire aux clés d'API.
- **Base de données** : Postgres en prod via `DATABASE_URL` (dj-database-url), fallback SQLite en local. Une seule table applicative (`ApiKey`).
- **Fermeture de compte** (`account_views.py`) : entrée « Supprimer mon compte » dans le menu utilisateur → page de confirmation `compte/supprimer/` (taper `SUPPRIMER`) → POST **tout-ou-rien** : dans une même transaction, `ApiKey.anonymize_user()` (révocation + `user_email` vidé + `user_sub` → `deleted:<hash>`, lignes conservées pour l'audit) puis suppression de l'utilisateur chez l'IdP ; si l'appel IdP échoue, rollback local. La suppression d'utilisateur n'étant pas du OIDC standard, elle est isolée dans `idp_admin.py` (**Zitadel-spécifique** : API User v2, PAT `ZITADEL_SERVICE_TOKEN` d'un service user Org User Manager) — `auth.py` reste provider-agnostic. Sans `ZITADEL_SERVICE_TOKEN`, la fonctionnalité est masquée. Pas de logout RP-initiated après suppression : Zitadel termine lui-même les sessions du compte supprimé.

## Chatbot (`chat.py`)

Boucle tool-use **stateless** sur l'API Mistral (`CHAT_MODEL`, défaut `mistral-medium-latest` en prod) : le client envoie tout l'historique à chaque tour, le serveur ne stocke rien. Les tools exposés sont de minces wrappers de `services.py` (`get_overview`, `get_consommation`, `get_production`, `get_echanges`, `get_echanges_energie`, `get_peak`, `get_parc`, `get_calendrier`…).

**Élagage de l'historique** (`_prune_tool_history`) : les messages `tool` et les `tool_calls` des tours passés sont retirés de l'historique — à l'entrée de `run()` (compat avec les historiques déjà stockés côté navigateur) et de l'historique renvoyé au frontend. Seuls les échanges texte user/assistant sont conservés et comptés dans `CHAT_MAX_TURNS` ; le modèle rappelle un tool s'il a besoin des chiffres bruts. La plomberie tool-use du tour **courant** est en revanche conservée pendant la boucle (exigence du format API : un `tool_calls` doit être immédiatement suivi de ses résultats).

Points d'attention encodés dans le prompt système :

- La **date du jour** (Europe/Paris) est injectée à chaque appel — sans elle le modèle résout « hier » sur ses connaissances internes.
- Périmètre restreint à l'électricité française ; unités toujours précisées ; chiffres uniquement via les tools ; pics/records via `get_peak` (les courbes raw downsamplent) ; granularité `raw` bornée à 31 jours.

**Limite de débit Mistral (429)** : la limite (req/s + tokens/min) est par **workspace**, quel que soit le crédit — la boucle tool-use enchaîne les appels dos à dos et toutes les conversations partagent la même clé. Un 429 est donc un événement normal, absorbé par **retry avec backoff** (`ChatService._complete`) : 3 tentatives, backoff 1 s puis 2 s, `Retry-After` honoré (borné à 8 s). Un 429 persistant lève `ChatBusyError`, que la vue traduit en HTTP 429 avec un message actionnable (jamais de 500 « Erreur interne »).

Il n'y a **aucun rate-limit applicatif** sur le chat — ni par utilisateur ni global (quotas retirés le 2026-07-16, choix assumé après le passage du workspace Mistral au plan Pro). Seule borne côté appli : la taille du body (`CHAT_MAX_BODY_BYTES`). La dépense Mistral n'est donc bornée que par l'usage réel — surveiller la consommation côté console Mistral (et les logs `chat usage` côté appli). Si la contention 429 devient fréquente, vérifier la page **Limits** de la console Mistral et demander une augmentation au support.

## Lancer en local

Un virtualenv existe dans `webapp/venv` ; port standard 8000 :

```bash
cd webapp
venv/bin/python manage.py runserver 8000
```

Première installation : `cp .env.example .env` (remplir), puis `venv/bin/pip install -r requirements.txt`.
