# Plan : renommage StatElec → Buzzelec

## Objectif

Renommer l'application « StatElec » en « Buzzelec » partout où le nom est du **branding** (UI, meta, docs, API, namespace JS), sans toucher aux **identifiants techniques** qui vivent hors du code.

## Étapes

1. Remplacement case-sensitive `StatElec` → `Buzzelec` (le branding est toujours en casse mixte, les ids techniques toujours en minuscules `statelec`) :
   - templates : `base.html`, `404.html`, `500.html`, pages consommation (titres, og:, navbar)
   - `webapp/static/manifest.json` (name, short_name)
   - `webapp/consommation/api.py` (titre OpenAPI), `constants.py` (docstring)
   - namespace JS `window.StatElec` → `window.Buzzelec` (`charts.js`, `date-filter.js`, appels dans les templates)
   - `webapp/static/css/style.css` (commentaire d'en-tête)
   - `docs/05-api.md`, `spec.md`
2. Renommer `blog/statelec.md` → `blog/buzzelec.md` si le contenu est du branding.
3. Noter dans `docs/06-deploiement.md` que les ids techniques gardent `statelec`.

## Fichiers concernés

Voir étape 1. **Non renommés (volontairement)** :
- domaine `statelec.cleverapps.io` (URL réelle de prod)
- `.clever.json` + `--alias statelec` du workflow (id de l'app Clever)
- add-on Postgres `statelec-postegredb`, service account Zitadel `statelec-account-deletion`
- plans/ et docs/decisions/ historiques (archives)

## Risques / points d'attention

- Le namespace JS est référencé dans plusieurs templates : renommer partout dans le même commit sinon les charts cassent.
- Renommer le domaine / l'app Clever = opération console Clever (hors scope, à décider séparément).
