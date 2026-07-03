# Plan : élagage des résultats de tools dans l'historique du chat

## Objectif

L'historique du chatbot fait l'aller-retour complet navigateur ↔ serveur ↔ Mistral à
chaque message, y compris les messages `tool` (gros JSON de données) et les
`tool_calls` des tours précédents. Ces messages ne servent plus une fois que le
modèle a produit sa réponse texte : le modèle peut rappeler un tool si besoin.

Les élaguer :
1. réduit fortement les tokens d'entrée payés à chaque tour (poste principal) ;
2. fait reculer le mur « Conversation trop longue » (`CHAT_MAX_TURNS` compte
   aujourd'hui les messages tool) → 30 vrais échanges user/assistant ;
3. allège le localStorage et le body POST (borne `MAX_BODY_BYTES`).

## Étapes

1. `chat.py` : ajouter `_prune_tool_history(messages)` —
   - supprime les messages `role == "tool"` ;
   - pour les messages assistant porteurs de `tool_calls` : retire `tool_calls`,
     garde le texte s'il y en a, supprime le message si le contenu est vide.
2. `ChatService.run()` :
   - élaguer l'historique entrant en début de méthode (compat avec les
     historiques déjà stockés côté navigateur au format actuel) ;
   - appliquer le contrôle `max_turns` sur l'historique élagué ;
   - conserver la plomberie tool-use complète PENDANT la boucle du tour courant
     (exigence du format API : un `tool_calls` doit être suivi de ses résultats) ;
   - élaguer l'historique retourné au frontend (réponse finale et erreur
     « trop d'itérations »), pour que le localStorage ne stocke plus que du texte.
3. Tests (`tests.py`) : fonction pure + boucle `run()` avec client Mistral mocké
   (l'historique retourné ne contient ni `tool` ni `tool_calls`, la réponse
   finale est correcte).
4. Doc : mettre à jour la section chatbot de `docs/04-webapp.md` (même commit).

## Fichiers concernés

- `webapp/consommation/chat.py`
- `webapp/consommation/tests.py`
- `docs/04-webapp.md`

## Risques / points d'attention

- Le modèle perd l'accès aux chiffres bruts des tours précédents : accepté, ses
  réponses texte résument déjà l'essentiel et il peut rappeler le tool.
- Ne PAS élaguer à l'intérieur de la boucle du tour courant, sinon erreur API
  Mistral (tool_calls orphelins).
- Frontend inchangé : il stocke/renvoie ce que le serveur retourne.
