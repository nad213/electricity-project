# Plan : résilience du chatbot aux 429 Mistral

## Objectif

En prod (2026-07-08, 11:50 UTC), une question de suivi dans le chat a renvoyé
« Erreur interne: SDKError » (HTTP 500). Cause réelle dans les logs Clever :

```
SDKError: API error occurred: Status 429.
Body: {"type":"rate_limited","code":"1300","message":"Rate limit exceeded"}
```

La limite de débit Mistral (req/s et tokens/min, appliquées indépendamment)
est **par workspace**, quel que soit le crédit chargé : la boucle tool-use
(`ChatService.run`) enchaîne jusqu'à 10 appels `chat.complete` dos à dos, et
toutes les conversations partagent la même clé. Un 429 est donc un événement
normal à absorber, pas une anomalie. Trois changements :

1. **Retry avec backoff** sur 429 autour de chaque `chat.complete` (honore
   `Retry-After`) — absorbe les collisions transitoires, y compris entre
   utilisateurs simultanés.
2. **Erreur propre** quand le 429 persiste : réponse HTTP 429 avec message
   actionnable (« service très sollicité, réessaie ») au lieu du 500 opaque.
3. ~~**Garde-fou global** : quota de messages toutes sessions confondues
   (`CHAT_GLOBAL_RATE_LIMIT`)~~ — **retiré le 2026-07-16 à la demande de
   l'utilisateur**, ainsi que le **quota par utilisateur préexistant**
   (`CHAT_RATE_LIMIT`/`CHAT_RATE_WINDOW`, `_chat_rate_limited`) : plus aucun
   rate-limit applicatif sur le chat. Contexte : le workspace Mistral est
   passé du plan free au plan Pro le même jour, la contention 429 d'origine
   a largement disparu. La dépense n'est pas bornée côté appli (seule borne :
   `CHAT_MAX_BODY_BYTES`) — surveillance via la console Mistral.

## Étapes

1. `chat.py` :
   - import tolérant de `MistralError` (2.x : `mistralai.client.errors` ;
     1.x : `mistralai.models.SDKError`) — même motif que l'import de `Mistral` ;
   - exception `ChatBusyError` ;
   - méthode `ChatService._complete(history)` : l'appel API + retries
     (3 tentatives, backoff 1 s puis 2 s, `Retry-After` honoré et borné) ;
     429 persistant → `ChatBusyError` ; toute autre erreur remonte telle quelle.
2. `chat_views.py` : `except ChatBusyError` → 429 + message clair (avant le
   `except Exception`) ; suppression de tout rate-limit applicatif
   (cf. ci-dessus).
3. Tests (`tests.py`) : retry-puis-succès, 429 persistant → `ChatBusyError`,
   erreur non-429 remontée sans retry, mapping vue → 429 ; tests des quotas
   supprimés avec eux.
4. Doc : `docs/04-webapp.md` (section Chatbot : retry, absence de rate-limit
   actée), `.env.example` (variables de quota retirées).

## Fichiers concernés

- `webapp/consommation/chat.py`
- `webapp/consommation/chat_views.py`
- `webapp/consommation/tests.py`
- `webapp/.env.example`
- `docs/04-webapp.md`

## Risques / points d'attention

- Les `time.sleep` du retry bloquent un worker Gunicorn (~3 s de sommeil
  cumulé max + `Retry-After` borné à 8 s) — acceptable au trafic actuel,
  à surveiller si le nombre de workers est réduit.
- Compteurs de quota en LocMemCache = par worker (limite effective ×
  nb workers), déjà documenté pour le quota par utilisateur — même compromis
  assumé pour le quota global ; passer sur Redis pour un comptage exact.
- La vraie capacité reste bornée par le tier Mistral du workspace : si la
  contention devient fréquente (visible via les logs `chat usage`), vérifier
  la page Limits de la console Mistral et demander une augmentation au support.
