# ADR 004 — Hébergement de la webapp sur Clever Cloud

**Statut : adopté (juillet 2026)** — remplace Render pour la webapp ; l'ETL reste sur AWS.

## Contexte

La webapp tournait sur Render.com depuis l'origine, avec deux irritants :

- **Échéance Postgres** : le free tier Postgres Render (clés d'API) expirait vers 2026-09-03 ([ADR 002](002-postgres-render-api-keys.md)), sans successeur décidé.
- **Souveraineté** : l'étude Scaleway ([ADR 003](003-migration-scaleway-etude.md)) avait posé la préférence pour un hébergeur européen. Clever Cloud (français) avait été écarté pour l'ETL faute de FaaS, mais restait candidat pour la webapp seule.

Un déploiement test sur Clever Cloud (2026-07-03, `notes/clever-cloud-webapp.md`) a validé la faisabilité **sans changement de code** : gunicorn + WhiteNoise + cache Parquet se comportent comme sur Render.

## Décision

Héberger la webapp sur **Clever Cloud** (app `statelec`, runtime Python, instance XS, domaine `statelec.cleverapps.io`), avec un **add-on Postgres** pour les clés d'API — ce qui clôt l'échéance de l'ADR 002. L'auto-deploy sur push `master` est répliqué par un workflow GitHub Actions (`clever deploy`), Clever n'ayant pas d'intégration GitHub native équivalente à celle de Render.

Particularités encodées dans le repo (détail : [06-deploiement.md](06-deploiement.md)) :

- `clevercloud/run.sh` (gunicorn, port 9000) et `clevercloud/post_build.sh` (collectstatic + migrate), pointés par `CC_RUN_COMMAND` / `CC_POST_BUILD_HOOK` — évite les commandes à chemins absolus dans les variables d'env.
- `.clever.json` versionné : lie le repo à l'app pour la CLI.

## Conséquences

- `render.yaml` et `build.sh` supprimés ; le service et la Postgres Render sont décommissionnés après une période d'observation (les clés d'API sont migrées par dump/restore juste avant la bascule).
- **Changement d'URL cassant** : `electricity-project-1.onrender.com` → `statelec.cleverapps.io`, sans redirect possible une fois Render éteint (consommateurs API et favoris à prévenir). Un domaine propre reste possible plus tard à faible coût.
- L'ETL reste sur AWS : la question souveraineté n'est traitée que pour la webapp (voir ADR 003 pour l'ETL).
