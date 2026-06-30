# Plan : tri chronologique vs classement pour le filtre `month` du chatbot

## Objectif
Permettre au chatbot de répondre à « les N derniers mois de février » (= les N plus
**récents**) et pas seulement « les N février les plus consommateurs ». Aujourd'hui, dès
qu'un mois calendaire est filtré, le tri est forcé par valeur décroissante → impossible
d'obtenir les plus récents.

## Étapes
1. Ajouter un paramètre `order` (`"value"` défaut | `"recent"`) aux tools
   `get_consommation` et `get_production` (filtre `month`).
2. Pour `get_echanges_energie`, ajouter la même valeur `"recent"` au tri (réutilise
   `sort_by` pour le sens du volume, `order` pour value-vs-chronologique).
3. Appliquer le tri chronologique décroissant sur la colonne date (`year_month` / `mois`)
   quand `order="recent"`.
4. Mettre à jour les descriptions : « derniers / récents » ⇒ chronologique ;
   « record / palmarès » ⇒ par valeur.

## Fichiers concernés
- `webapp/consommation/chat.py` (schémas TOOLS + `_tool_get_consommation`,
  `_tool_get_production`, `_tool_get_echanges_energie`).

## Risques / points d'attention
- Garder `value` comme défaut pour ne pas casser les requêtes de type classement.
- Le tri chronologique doit s'appliquer **avant** `top_n` (sinon on coupe les mauvaises lignes).
