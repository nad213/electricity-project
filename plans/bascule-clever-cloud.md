# Plan : bascule de la webapp de Render vers Clever Cloud

> Suite de `plans/deploiement-clever-cloud.md` (test réussi le 2026-07-03 sur
> https://statelec.cleverapps.io). Ici : adoption de Clever comme **prod** et
> décommissionnement de Render. L'ETL AWS ne bouge pas.
>
> **État 2026-07-05** : décisions prises — domaine `statelec.cleverapps.io` conservé,
> auto-deploy via GitHub Actions. Parties A+B implémentées sur la branche
> `bascule-clever-cloud` (ajout par rapport au plan : `clevercloud/post_build.sh` committé
> aussi, symétrique de `run.sh` — remplace le CC_POST_BUILD_HOOK inline). Restent C et D.

## Objectif

Faire de l'app Clever `statelec` la production : le code et la doc ne référencent plus
Render, le déploiement sur push `master` est conservé, les clés d'API migrent vers la
Postgres Clever, puis le service Render est éteint.

## Étapes

### A. Code / repo (préparables tout de suite, sur une branche)

1. **Run command sans chemin en dur** : committer `clevercloud/run.sh` (gunicorn, bind 9000)
   et passer `CC_RUN_COMMAND=bash clevercloud/run.sh`. La commande est exec-utée sans shell
   mais depuis la racine du repo → un chemin relatif marche, et on supprime le
   `/home/bas/app_<id>/webapp` en dur (fragile si l'app est recréée).
2. **Auto-deploy** : workflow GitHub Actions `webapp-deploy.yml` qui, sur push `master`,
   pousse vers le remote Clever (ou `clever deploy` avec `CLEVER_TOKEN`/`CLEVER_SECRET` en
   secrets GitHub). Réplique le `autoDeploy: true` de Render.
3. **Supprimer** `render.yaml` et `build.sh` (racine, utilisé uniquement par Render) —
   dans le commit de bascule, pas avant.
4. **Commentaires code** : `webapp/config/settings.py` (mentions Render lignes ~44, ~100,
   ~125, ~183) et `webapp/.env.example` (« Render=1 ») → neutraliser ou dire « Clever ».
5. **Committer `.clever.json`** (ids d'app/org, pas des secrets) pour que la CLI soit
   utilisable depuis n'importe quel clone.

### B. Documentation (même commit que A, règle CLAUDE.md)

- `docs/06-deploiement.md` : section Render → Clever (env `CC_*`, hooks, port 9000,
  add-on Postgres, logs `clever logs`).
- `docs/01-architecture.md` : URL publiée, diagramme Mermaid (`subgraph Render`), tableau
  hébergement.
- `docs/04-webapp.md` : 3 mentions (Gunicorn/Render, /tmp éphémère, TTL posé par render.yaml).
- `docs/05-api.md` : URL d'exemple `onrender.com`.
- `README.md` : URL + section déploiement.
- Nouvel ADR `docs/decisions/004-hebergement-clever-cloud.md` (pourquoi : souveraineté,
  échéance Postgres Render ~2026-09-03, coût) + note de clôture dans l'ADR 002.

### C. Ops (bloquants avant la bascule, hors code)

1. ~~OIDC IdP~~ **fait le 2026-07-05** : URIs ajoutées côté Zitadel — ⚠️ le `redirect_uri`
   envoyé par l'app a un **slash final** (`…/callback/`), l'entrée IdP doit l'avoir aussi
   (comparaison exacte). Reste à valider par un login réel dans le navigateur.
2. ~~Clés d'API~~ **abandonné le 2026-07-05** : pas de migration — uniquement des
   utilisateurs test, qui régénéreront leurs clés depuis `/api/` sur la nouvelle instance.
   L'échéance Postgres Render (~2026-09-03) devient sans objet une fois Render éteint.
3. **Vérifier `NINJA_NUM_PROXIES`** sur Clever : nginx local + LB Sozu devant → la
   profondeur X-Forwarded-For n'est peut-être pas 1 comme sur Render. Tester avec une
   requête réelle avant d'activer le throttling en confiance.
4. **Décision domaine** : rester sur `statelec.cleverapps.io` ou prendre un domaine propre ?
   Changement d'URL = cassant pour les consommateurs de l'API et les favoris
   (`electricity-project-1.onrender.com` ne redirigera plus une fois Render éteint).

### D. Bascule et décommissionnement

1. Valider sur Clever : login OIDC (navigateur), chat, génération d'une clé d'API depuis
   `/api/` + un appel authentifié (permet aussi de vérifier `NINJA_NUM_PROXIES`).
   Warmup cache déjà validé (pages 200 à ~100 ms).
2. ~~Env vars Clever + secrets GitHub~~ **fait le 2026-07-05** :
   `CC_RUN_COMMAND=bash ../clevercloud/run.sh` (⚠️ le run part de `$APP_FOLDER`, pas de la
   racine — contrairement aux hooks), `CC_POST_BUILD_HOOK=bash clevercloud/post_build.sh`,
   secrets `CLEVER_TOKEN`/`CLEVER_SECRET` posés. Branche déployée et validée sur
   statelec.cleverapps.io (toutes pages 200).
3. ~~Merger sur `master`~~ **fait le 2026-07-05** (merge `d990f4d`) : workflow
   `Deploy Webapp` passé au vert (1 min 07), site en 200 après deploy. Validations
   préalables toutes OK : OIDC (⚠️ redirect_uri avec slash final), chat (piège :
   guillemets à ne PAS coller dans la console env Clever), API + throttling 429.
4. **→ prochaine action** : désactiver l'autoDeploy Render (sinon deux prods en
   parallèle — le deploy Render du merge échouera de toute façon, build.sh supprimé),
   observer quelques jours.
5. Supprimer le service + la Postgres Render (pas d'export : clés test uniquement).

## Fichiers concernés

- Créés : `clevercloud/run.sh`, `.github/workflows/webapp-deploy.yml`,
  `docs/decisions/004-hebergement-clever-cloud.md`, ce plan
- Modifiés : `docs/01-architecture.md`, `docs/04-webapp.md`, `docs/05-api.md`,
  `docs/06-deploiement.md`, `README.md`, `webapp/config/settings.py` (commentaires),
  `webapp/.env.example`, `docs/decisions/002-postgres-render-api-keys.md`
- Supprimés : `render.yaml`, `build.sh`
- Committé : `.clever.json`

## Risques / points d'attention

- **Deux prods en parallèle** entre la bascule et la désactivation de l'autoDeploy Render :
  les deux liront le même S3 (inoffensif) mais deux Postgres divergent → migrer les clés
  en dernier, juste avant la bascule.
- **URL cassante** : pas de redirect possible depuis onrender.com après extinction.
- **Secrets GitHub Actions** : `CLEVER_TOKEN`/`CLEVER_SECRET` à créer ; sinon fallback
  manuel `git push clever master`. ⚠️ Le token Clever **expire le 2027-07-04** (champ
  `expirationDate` de `~/.config/clever-cloud/clever-tools.json`) : refaire `clever login`
  et mettre à jour les deux secrets avant cette date, sinon le workflow échouera.
- La config effective Render est celle du **dashboard**, pas `render.yaml` — vérifier au
  moment du décommissionnement qu'aucune env var prod n'a été oubliée dans la note
  `notes/clever-cloud-webapp.md`.
