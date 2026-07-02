# Plan : expiration de l'historique du chat après 1 h d'inactivité

## Objectif
Aligner la durée de vie du fil de conversation du chatbot sur celle de la session
Django (1 h d'inactivité glissante, cf. commit 49a39cd). Aujourd'hui l'historique
vit dans le `localStorage` du navigateur (clé `kilowatch_chat_history`) et persiste
indéfiniment : après expiration de la session, le fil reste affiché — incohérent.

## Étapes
1. Ajouter une constante `CHAT_TTL_MS = 3600000` (1 h, = SESSION_COOKIE_AGE) dans le
   script de `chat.html`.
2. Stocker un timestamp de dernière activité (clé `kilowatch_chat_ts`) à chaque
   écriture de l'historique (`saveHistory`).
3. Au chargement : si `Date.now() - ts > CHAT_TTL_MS`, purger les deux clés et
   repartir d'un fil vide (mode glissant : chaque message repousse le délai).

## Fichiers concernés
- `webapp/consommation/templates/consommation/chat.html` (JS inline uniquement)

## Risques / points d'attention
- Purement côté client : pas de backend, pas de migration. Le backend reste stateless.
- Par navigateur/appareil (comme aujourd'hui), pas par compte.
- Ne pas casser le format existant du `localStorage` (rétrocompat : une clé sans
  timestamp est traitée comme expirée → purge propre).
