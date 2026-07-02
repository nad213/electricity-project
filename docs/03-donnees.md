# Données : sources, schémas et pièges métier

Ce fichier documente ce qui ne se voit pas dans le code : les subtilités des données sources et les erreurs déjà commises (et corrigées) en les manipulant.

## Sources

| Source | Contenu | Accès |
|---|---|---|
| ODRE `eco2mix-national-tr` | Conso, production, échanges — **temps réel**, pas 15 min, provisoire | Export Parquet opendatasoft |
| ODRE `eco2mix-national-cons-def` | Idem — **consolidé/définitif**, pas 30 min | Export Parquet opendatasoft |
| RTE analysesetdonnees | Production mensuelle et facteur de charge éolien/solaire | Scraping (JSON embarqué dans le HTML) |
| RTE pmax | Puissance max installée par filière (instantané) | JSON |

## Temps réel vs consolidé

**Le piège le plus coûteux du projet.** Les points temps réel (pas 15 min) sont systématiquement biaisés par rapport au consolidé (pas 30 min, définitif). Les intercaler dans une même série produit des « dents de scie » sur les courbes et avait gonflé l'énergie mensuelle jusqu'à **+49 %** (double comptage : deux sources sur la même plage horaire).

Règle appliquée par l'ETL (`prune_realtime_in_consolidated_zone`) : **le temps réel n'est conservé que strictement au-delà du dernier horodatage consolidé.** La purge s'applique aussi à l'historique réinjecté par le merge, pour nettoyer les données polluées avant le fix.

## Conversion puissance → énergie

Les valeurs sources sont des **puissances (MW)** échantillonnées. Pour obtenir de l'énergie (MWh), on somme puis on divise par le nombre de points par heure — **qui dépend de la source** :

- Consolidé : pas 30 min → `somme / 2`
- Temps réel : pas 15 min → `somme / 4`

La division doit se faire **par source, avant** d'additionner les deux : appliquer un diviseur unique sur le mélange fausse le résultat. C'est pour cela que les transforms agrègent d'abord par `(year, month, source)`.

## Échanges transfrontaliers

- **Convention de signe : positif = importation, négatif = exportation** (convention eco2mix, conservée telle quelle jusqu'à l'affichage).
- `ech_physiques` = solde physique total ; les colonnes `ech_comm_*` (angleterre, espagne, italie, suisse, allemagne_belgique) sont les échanges **commerciaux** par frontière. Total physique et somme des commerciaux ne coïncident pas exactement (transits, écarts physique/commercial).
- La granularité varie **par colonne** entre 15 et 30 min : le diviseur de conversion en énergie doit être déterminé colonne par colonne, pas globalement.

## Granularité historique

Le pas de 15 min n'existe que sur les 1–2 dernières années ; avant, les données sont plus grossières. Conséquence : les requêtes « raw » sur de longues plages ne renvoient pas une densité homogène, et les caps de plage (`MAX_RANGE_DAYS` de l'API, limite 31 jours du chatbot en `raw`) sont calibrés pour la zone dense.

## Parc installé : deux sources non comparables

- `rte_pmax.parquet` (« actuel ») : photo instantanée de la puissance max par filière.
- Scraping RTE (« historique ») : évolution du parc éolien terrestre / en mer / solaire uniquement.

Les deux ne mesurent pas exactement la même chose — écart connu sur le solaire (~31,9 GW côté pmax vs ~17 GW côté historique, point encore ouvert). Ne jamais comparer un chiffre « actuel » avec un chiffre « historique » sans mentionner la source ; le prompt du chatbot impose la même règle.

## Schémas des fichiers `02_clean/` (contrat ETL → webapp)

| Fichier | Colonnes principales |
|---|---|
| `consommation_france_puissance` | `date_heure`, `consommation` (MW), `source` |
| `consommation_mensuelle` | `year_month` (`"2024-01"`), `monthly_consumption` (MWh) |
| `consommation_annuelle` | `year`, `yearly_consumption` (MWh) |
| `production_france_detail` | `date_heure`, `source`, une colonne par filière et sous-filière (MW) : `nucleaire`, `gaz`, `gaz_tac`…, `pompage` |
| `production_mensuelle` | `year_month`, `<filiere>_mwh` |
| `production_annuelle` | `year`, `<filiere>_yearly_mwh` |
| `echanges_france_detail` | `date_heure`, `source`, `ech_physiques`, `ech_comm_*` (MW) |
| `echanges_mensuels` | `year_month`, `<col>_mwh` |
| `echanges_annuels` | `year`, `<col>_yearly_mwh` |
| `rte_pmax` | `filiere`, `puissance_max_mw` |

Les fichiers détaillés conservent l'historique complet (le merge ETL préserve les lignes purgées par ODRE) ; lignes filtrées si toutes les colonnes de valeurs sont nulles.

## Historique / rétention

ODRE limite la profondeur de ses exports : c'est le `merge_with_existing` de l'ETL qui construit l'historique long au fil du temps. **Les fichiers `02_clean/` sont donc irremplaçables** — les supprimer ferait perdre l'historique au-delà de la fenêtre ODRE actuelle.
