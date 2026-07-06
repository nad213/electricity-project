# Plan : fermeture de compte en self-service (bouton in-app)

## Objectif

Permettre à un utilisateur connecté de supprimer définitivement son compte depuis
le site, en un seul flow atomique qui traite les **deux moitiés** du problème :

1. **Côté app** : révoquer ses clés d'API et anonymiser ses données personnelles
   (`user_email`, `user_sub`) dans la table `ApiKey` — sans supprimer les lignes,
   pour rester cohérent avec le design soft-delete/audit existant.
2. **Côté IdP (Zitadel)** : supprimer le compte utilisateur via l'API de
   management Zitadel, appelée par le serveur avec un service account.

Motivation : avec le self-service Zitadel seul, un utilisateur peut supprimer son
compte IdP sans que l'app en soit notifiée → clés d'API actives orphelines et
email restant en base. Le bouton in-app garantit que le ménage local et la
suppression IdP se font ensemble. Couvre aussi le droit à l'effacement (RGPD).

## Étapes

### 1. Client Zitadel de suppression — `consommation/idp_admin.py` (nouveau)

- Fonction `delete_idp_user(sub: str) -> None` : `DELETE {OIDC_ISSUER}/v2/users/{sub}`
  (User Service v2 de Zitadel ; le `sub` OIDC **est** l'ID utilisateur Zitadel),
  header `Authorization: Bearer {ZITADEL_SERVICE_TOKEN}`, timeout 10 s,
  `raise_for_status()`.
- **Isolé dans un module à part** (pas dans `auth.py`) : `auth.py` est
  volontairement provider-agnostic (OIDC discovery) ; la suppression
  d'utilisateur n'est PAS du OIDC standard, c'est du Zitadel-spécifique. Le
  docstring du module doit le dire explicitement (à adapter si changement d'IdP).
- Helper `is_account_deletion_enabled() -> bool` : `bool(settings.ZITADEL_SERVICE_TOKEN)`
  — permet de masquer le bouton quand la variable n'est pas configurée
  (dev local, ou IdP non-Zitadel).

### 2. Config — `settings.py` + `.env.example`

- `ZITADEL_SERVICE_TOKEN = os.getenv('ZITADEL_SERVICE_TOKEN', '')` — PAT d'un
  service user Zitadel.
- Documenter dans `.env.example` : variable optionnelle ; si vide, le bouton
  « Supprimer mon compte » n'apparaît pas.

### 3. Côté Zitadel (manuel, console — prérequis avant mise en prod)

- Créer un **service user** dédié (ex. `statelec-account-deletion`) avec un
  **PAT** et le rôle **Org User Manager** sur l'organisation (droit minimal qui
  permet la suppression d'utilisateurs de l'org).
- Reporter le PAT dans les variables d'env Clever Cloud (⚠️ piège connu de la
  console Clever : **pas de guillemets** autour de la valeur).
- Noter la **date d'expiration du PAT** choisie à la création (même piège que le
  token Clever qui expire 2027-07-04) → l'inscrire dans ce plan une fois créé.

### 4. Anonymisation — `consommation/models.py`

- Méthode de classe `ApiKey.anonymize_user(sub: str) -> int` :
  - `revoked_at = now()` sur les clés encore actives du `sub` ;
  - `user_email = ''` et `user_sub = f'deleted:{sha256(sub)[:12]}'` sur toutes
    ses lignes (le hash tronqué garde les lignes d'un même ex-utilisateur
    groupées pour l'audit, sans donnée personnelle ni réversibilité pratique).
  - Retourne le nombre de lignes touchées (log/message).
- Les hash de clés (`key_hash`, `prefix`) ne sont pas personnels → conservés.

### 5. Vue — `consommation/account_views.py` (nouveau)

Une seule route `compte/supprimer/` (name `delete_account`), deux méthodes :

- **GET** : page de confirmation dédiée (l'entrée du menu déroulant est un
  lien, la suppression reste un POST). Connecté requis, sinon redirect login.
- **POST** : exécute la suppression :
  1. `get_user_from_session(request)` — sinon redirect login.
  2. Garde-fou : champ de confirmation POST (`confirm == 'SUPPRIMER'`) — sinon
     message d'erreur et re-rendu de la page de confirmation.
  3. Dans `transaction.atomic()` : `ApiKey.anonymize_user(sub)` **puis**
     `delete_idp_user(sub)`. Si l'appel Zitadel lève → rollback du ménage local,
     message d'erreur « réessaie ou contacte-nous », rien n'a changé. (Appel
     réseau dans une transaction : acceptable à cette échelle, et c'est ce qui
     rend le flow tout-ou-rien.)
  4. `request.session.flush()` — pas de logout RP-initiated vers l'IdP : le
     compte n'existe plus, Zitadel termine ses sessions à la suppression.
  5. Redirect accueil + `messages.success("Ton compte a été supprimé.")`.

### 6. UI — menu déroulant + page de confirmation

- **`templates/base.html`** : dans le dropdown utilisateur (celui qui porte
  l'email et « Se déconnecter », ~l.129), ajouter un item « Supprimer mon
  compte » (lien GET vers `delete_account`), séparé par un
  `dropdown-divider`, classe `text-danger` (convention Tabler pour les actions
  destructives — rouge conventionnel, pas décoratif). Affiché seulement si
  `account_deletion_enabled`.
- **`consommation/context_processors.py`** : exposer
  `account_deletion_enabled` (= `is_account_deletion_enabled()`) — le dropdown
  est dans `base.html`, donc rendu sur toutes les pages ; le flag doit être
  global, pas passé par une vue.
- **`templates/consommation/delete_account.html`** (nouveau) : page de
  confirmation — conséquences (compte IdP supprimé, clés d'API révoquées,
  irréversible), nombre de clés actives de l'utilisateur, champ texte « tape
  SUPPRIMER pour confirmer », bouton danger + lien annuler. Sobriété UI :
  monochrome, le rouge réservé au bouton. Vérifier le rendu en thème dark
  (remap Tabler partiel — les composants neufs peuvent rester blancs).

### 7. Tests — `consommation/tests.py`

- `anonymize_user` : clés actives révoquées, email vidé, sub remplacé, clés déjà
  révoquées non re-révoquées (`revoked_at` inchangé).
- Vue : non connecté (GET et POST) → redirect login ; GET connecté → page de
  confirmation ; confirmation absente/mauvaise → rien ne change ; échec API Zitadel (mock qui lève) → rollback (les `ApiKey` sont
  intactes) ; succès (mock) → anonymisation + session vidée + redirect.
- Mocker `idp_admin.delete_idp_user` — aucun appel réseau réel en test.

### 8. Documentation (même commit)

- `docs/04-webapp.md` (section Sessions et authentification) : le flow de
  fermeture de compte + la nuance « auth provider-agnostic, suppression
  Zitadel-spécifique ».
- `docs/06-deploiement.md` : `ZITADEL_SERVICE_TOKEN` (+ expiration du PAT).
- Mentions légales / page API : mentionner la possibilité de supprimer son
  compte (et le mail de contact en fallback).

## Fichiers concernés

- `webapp/consommation/idp_admin.py` — **nouveau** : appel Zitadel
- `webapp/consommation/account_views.py` — **nouveau** : vue de suppression
- `webapp/consommation/models.py` — `ApiKey.anonymize_user()`
- `webapp/consommation/urls.py` — route `compte/supprimer/`
- `webapp/consommation/context_processors.py` — flag global `account_deletion_enabled`
- `webapp/templates/base.html` — item « Supprimer mon compte » dans le dropdown utilisateur
- `webapp/consommation/templates/consommation/delete_account.html` — **nouveau** : page de confirmation
- `webapp/config/settings.py` + `webapp/.env.example` — `ZITADEL_SERVICE_TOKEN`
- `webapp/consommation/tests.py` — tests
- `docs/04-webapp.md`, `docs/06-deploiement.md` — doc

## Risques / points d'attention

- **Le PAT expire** : à sa création Zitadel demande une date d'expiration. Après
  expiration, la suppression échouera (500 côté Zitadel → message d'erreur à
  l'utilisateur, rollback local, rien de cassé — mais fonctionnalité morte en
  silence). Mettre un rappel/date dans `docs/06-deploiement.md`.
- **Droits du service user** : Org User Manager suffit pour les utilisateurs de
  l'org ; tester en recette avec un compte jetable avant d'activer en prod.
- **Ordre des opérations** : le ménage local est dans la transaction et l'appel
  Zitadel aussi → si Zitadel échoue, rollback complet. L'inverse (Zitadel OK,
  commit local qui échoue) est l'unique cas résiduel : données locales
  orphelines, rattrapable à la main — probabilité négligeable.
- **Zitadel-spécifique** : si l'IdP change un jour (Keycloak…), seul
  `idp_admin.py` est à réécrire ; le reste du flow est inchangé. Sans
  `ZITADEL_SERVICE_TOKEN`, le bouton disparaît proprement (dégradation douce).
- **Réinscription** : le même email peut recréer un compte ensuite → nouveau
  `sub`, historique vierge. C'est le comportement voulu (l'ancien historique
  anonymisé ne lui est pas ré-attaché).
- **Self-service Zitadel en parallèle** : un utilisateur peut toujours supprimer
  son compte directement chez Zitadel (si la policy l'autorise) sans passer par
  le bouton → clés orphelines. Hors périmètre ici ; option future : désactiver
  cette policy côté Zitadel pour forcer le passage par l'app, ou job périodique
  de réconciliation.
- **Pas de double confirmation JS** : le champ « tape SUPPRIMER » suffit ; pas
  de modal custom (sobriété, pas de JS en plus).
