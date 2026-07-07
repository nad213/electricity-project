# Plan : renommage Buzzelec → ElecStat

## Objectif

Renommer le branding « Buzzelec » (posé le matin même, cf. `plans/renommage-buzzelec.md`) en « ElecStat ». Même périmètre : UI, meta, manifest, titre OpenAPI, namespace JS, docs — les identifiants techniques restent `statelec`.

## Étapes

1. Remplacement case-sensitive `Buzzelec` → `ElecStat` sur les mêmes fichiers que le renommage précédent.
2. `blog/buzzelec.md` → `blog/elecstat.md`.
3. Tests Django, commit, push (auto-deploy prod), vérification du site.

## Fichiers concernés

Identiques à `plans/renommage-buzzelec.md`. Toujours **non renommés** : domaine `statelec.cleverapps.io`, app/alias Clever, add-on Postgres, service account Zitadel.

## Risques / points d'attention

- Casse choisie : `ElecStat` (l'utilisateur a écrit « elecstat » ; casse mixte alignée sur l'ex-StatElec).
- Namespace JS renommé partout dans le même commit (sinon charts cassés).
