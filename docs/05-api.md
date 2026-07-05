# API publique v1 (StatElec)

API JSON en lecture seule (django-ninja), montée sous `/api/v1/`. Documentation interactive Swagger : `/api/v1/docs`. Elle réutilise directement `services.py` — les endpoints ne font que valider les paramètres et sérialiser.

## Endpoints

| Endpoint | Paramètres | Retour |
|---|---|---|
| `GET /meta` | — | Bornes de dates disponibles, filières, pays |
| `GET /courbe_conso` | `debut`, `fin` | Courbe de consommation (MW) |
| `GET /courbe_prod` | `debut`, `fin`, `filiere` (défaut `nucleaire`) | Courbe de production (MW) |
| `GET /echange` | `debut`, `fin`, `pays` (défaut `total`) | Courbe d'échanges (MW, positif = import) |
| `GET /energie_conso` | `debut`, `fin` | Énergie mensuelle (GWh) |
| `GET /energie_prod` | `debut`, `fin`, `filiere` | Énergie mensuelle (GWh) |
| `GET /energie_echange` | `debut`, `fin`, `pays` | Énergie mensuelle (GWh) |
| `GET /parc` | — | Puissance max installée par filière (MW) |

Unités : courbes en **MW**, énergie en **GWh**. Dates au format `YYYY-MM-DD`. `pays=total` correspond au solde physique (`ech_physiques`).

## Limites de plage

Les courbes infra-journalières génèrent ~35 000 points/an/série : la plage est bornée à **`API_MAX_RANGE_DAYS` (défaut 366 jours)** pour les endpoints `courbe_*`/`echange`. Les endpoints `energie_*` (une ligne par mois) acceptent jusqu'à 10 ans. Ajustable sans redéploiement (variable d'env).

## Authentification

En-tête `Authorization: Bearer <clé>` obligatoire (sinon 401). Deux sources de vérité, dans cet ordre :

1. **Base de données** — table `ApiKey` : seuls le **hash SHA-256** et un préfixe d'affichage sont stockés, jamais la clé en clair (montrée une seule fois à la génération, format `elf_live_<token>`). Révocation = soft-delete (`revoked_at`), effet immédiat, trace conservée. `last_used_at` mis à jour à l'usage.
2. **Variable d'env `API_KEYS`** (`libellé:sha256hex,…`) — chemin de compatibilité pour les clés distribuées avant la migration en base.

Cycle de vie self-service : page `/api/` (connecté via l'IdP) → génération et révocation de ses propres clés (rattachées au `sub` OIDC). En local sans IdP : créer une `ApiKey` via `manage.py shell`.

## Rate limiting

Throttling **par clé** (django-ninja `AuthRateThrottle`), deux fenêtres réglables par variables d'env :

- `API_THROTTLE_BURST` (défaut `1/2s`) — coupe les boucles serrées
- `API_THROTTLE_SUSTAINED` (défaut `5/min`) — plafonne le volume

⚠️ Le compteur vit dans le cache Django (LocMemCache, par process) : la limite effective est multipliée par le nombre de workers Gunicorn. Comptage exact en multi-worker ⇒ brancher un cache partagé (Redis) ; l'approximation actuelle suffit à protéger le service.

## Exemple

```bash
curl -H "Authorization: Bearer elf_live_xxxxx" \
  "https://statelec.cleverapps.io/api/v1/energie_conso?debut=2025-01-01&fin=2025-12-31"
```
