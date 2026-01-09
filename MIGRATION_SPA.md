# Migration vers SPA React - ElecFlow

Ce document décrit la migration de l'application ElecFlow d'une architecture Django SSR (Server-Side Rendering) vers une architecture SPA (Single Page Application) moderne avec React.

## 📋 Vue d'ensemble

### Architecture Avant
- **Frontend**: Django Templates (SSR)
- **Backend**: Django avec views traditionnelles
- **UI**: Tabler + Bootstrap 5
- **Charts**: Plotly.js côté serveur

### Architecture Après
- **Frontend**: React 18 + TypeScript + Vite (SPA)
- **Backend**: Django + Django REST Framework (API)
- **UI**: Tailwind CSS
- **Charts**: Plotly.js côté client
- **State Management**: TanStack Query
- **Routing**: React Router v6
- **Auth**: Auth0 React SDK

## 🎯 Changements Effectués

### 1. Backend - Django REST Framework

#### Nouveaux fichiers créés:
- `webapp/consommation/serializers.py` - Serializers pour la validation des données API
- `webapp/consommation/api_views.py` - API views RESTful
- `webapp/consommation/api_urls.py` - Routes API

#### Fichiers modifiés:
- `webapp/requirements.txt` - Ajout de `djangorestframework` et `django-cors-headers`
- `webapp/config/settings.py` - Configuration DRF et CORS
- `webapp/config/urls.py` - Ajout des routes API

#### Nouvelles routes API:

**Consommation:**
- `GET /api/consumption/metadata/` - Métadonnées (dates disponibles)
- `GET /api/consumption/power-curve/?date_debut=...&date_fin=...` - Courbe de puissance
- `GET /api/consumption/annual/?date_debut=...&date_fin=...` - Données annuelles
- `GET /api/consumption/monthly/?date_debut=...&date_fin=...` - Données mensuelles
- `GET /api/consumption/export/power/` - Export CSV puissance
- `GET /api/consumption/export/annual/` - Export CSV annuel
- `GET /api/consumption/export/monthly/` - Export CSV mensuel

**Production:**
- `GET /api/production/metadata/` - Métadonnées (secteurs, dates)
- `GET /api/production/power-curve/?secteur=...&date_debut=...&date_fin=...` - Courbe par secteur
- `GET /api/production/annual/?date_debut=...&date_fin=...` - Production annuelle
- `GET /api/production/monthly/?date_debut=...&date_fin=...` - Production mensuelle

**Échanges:**
- `GET /api/exchanges/metadata/` - Métadonnées (pays, dates)
- `GET /api/exchanges/curve/?pays=...&date_debut=...&date_fin=...` - Courbe par pays

### 2. Frontend - Application React

#### Structure créée:
```
webapp/frontend/
├── src/
│   ├── components/          # Composants réutilisables
│   │   ├── DateRangeFilter.tsx
│   │   └── PlotlyChart.tsx
│   ├── layouts/             # Layouts
│   │   └── MainLayout.tsx
│   ├── pages/               # Pages principales
│   │   ├── HomePage.tsx
│   │   ├── ConsumptionPage.tsx
│   │   ├── ProductionPage.tsx
│   │   └── ExchangesPage.tsx
│   ├── services/            # Services API
│   │   └── api.ts
│   ├── types/               # Types TypeScript
│   │   └── api.ts
│   ├── App.tsx              # App principal
│   ├── main.tsx             # Entry point
│   └── index.css            # Styles globaux
├── .env.example             # Template variables d'environnement
├── .env.local               # Variables d'environnement locales
├── tailwind.config.js       # Config Tailwind
├── vite.config.ts           # Config Vite
└── README.md                # Documentation frontend
```

#### Fonctionnalités implémentées:
- ✅ Authentification Auth0
- ✅ Routing avec React Router
- ✅ State management avec TanStack Query
- ✅ Composants de visualisation Plotly
- ✅ Filtres de dates réutilisables
- ✅ Export CSV
- ✅ Design responsive avec Tailwind
- ✅ Loading states et error handling
- ✅ Navigation persistante
- ✅ Thème navy blue professionnel

## 🚀 Guide de Démarrage

### Prérequis
- Python 3.12+
- Node.js 18+
- npm 9+

### Installation Backend

1. Installer les nouvelles dépendances Python:
```bash
cd webapp
source venv/bin/activate
pip install -r requirements.txt
```

2. Les anciennes views Django sont conservées pour compatibilité descendante

### Installation Frontend

1. Installer les dépendances npm:
```bash
cd webapp/frontend
npm install
```

2. Configurer les variables d'environnement:
```bash
cp .env.example .env.local
```

3. Éditer `.env.local` et configurer Auth0:
```
VITE_API_URL=http://localhost:8000/api
VITE_AUTH0_DOMAIN=votre-domaine.auth0.com
VITE_AUTH0_CLIENT_ID=votre-client-id
VITE_AUTH0_REDIRECT_URI=http://localhost:5173
```

### Démarrage en Développement

**Terminal 1 - Backend Django:**
```bash
cd webapp
source venv/bin/activate
python manage.py runserver
```

**Terminal 2 - Frontend React:**
```bash
cd webapp/frontend
npm run dev
```

L'application sera accessible sur:
- Frontend SPA: http://localhost:5173
- Backend API: http://localhost:8000/api
- Django Admin (ancien): http://localhost:8000/admin

## 📦 Build de Production

### Frontend
```bash
cd webapp/frontend
npm run build
```

Les fichiers statiques seront générés dans `webapp/frontend/dist/`.

### Déploiement

Pour servir le frontend via Django en production:

1. Configurer Django pour servir les fichiers statiques React:
```python
# Dans settings.py
STATICFILES_DIRS = [
    BASE_DIR / 'static',
    BASE_DIR / 'frontend' / 'dist',
]
```

2. Créer une vue catch-all pour le routing React:
```python
# Dans urls.py
from django.views.generic import TemplateView

urlpatterns = [
    path('api/', include('consommation.api_urls')),
    # ... autres routes API
    path('', TemplateView.as_view(template_name='index.html')),
]
```

## 🔄 Compatibilité

### Ancien système conservé
Les anciennes views Django templates sont toujours accessibles:
- `/accueil/` - Page d'accueil Django
- `/consommation/` - Page consommation Django
- `/production/` - Page production Django
- `/echanges/` - Page échanges Django

### Nouveau système SPA
Les nouvelles routes React:
- `/` - Page d'accueil React
- `/consumption` - Page consommation React
- `/production` - Page production React
- `/exchanges` - Page échanges React

## 🎨 Différences UI/UX

### Améliorations
- ✅ Navigation plus fluide (pas de rechargement de page)
- ✅ State management optimisé avec cache
- ✅ Meilleure gestion du loading et des erreurs
- ✅ Design moderne avec Tailwind CSS
- ✅ Responsive design amélioré
- ✅ Transitions et animations

### Changements visuels
- Navigation horizontale conservée (navy blue)
- Cartes et layouts modernisés
- Typographie système moderne
- Espacement et padding optimisés

## 🔐 Authentification

### Avant (Django)
- Session-based auth avec Auth0 OAuth2
- Cookies de session Django

### Après (React + Django)
- Auth0 React SDK côté client
- Session Django conservée pour l'API
- Cookies avec credentials pour CORS

## 📊 Performance

### Avantages du SPA
- Premier chargement initial plus lent (bundle JS)
- Navigation suivante instantanée (pas de rechargement)
- Mise en cache des données avec React Query
- Optimisation du rendu avec React
- Code splitting possible avec Vite

### Optimisations possibles
- [ ] Lazy loading des routes
- [ ] Code splitting par page
- [ ] Service Worker pour offline
- [ ] Compression gzip/brotli
- [ ] CDN pour les assets statiques

## 🧪 Tests

### À implémenter
- [ ] Tests unitaires React (Vitest)
- [ ] Tests d'intégration API
- [ ] Tests E2E (Playwright/Cypress)
- [ ] Tests de performance

## 📝 Notes de Migration

### Points d'attention
1. **Auth0 Configuration**: Vous devez configurer Auth0 avec les bonnes URLs de callback
2. **CORS**: Assurez-vous que CORS est correctement configuré pour le développement local
3. **Variables d'environnement**: Ne pas committer `.env.local`
4. **Plotly.js**: Le bundle est assez lourd (~3MB), considérer le lazy loading

### Problèmes connus
- ⚠️ Le bundle initial est volumineux à cause de Plotly.js
- ⚠️ Auth0 nécessite une configuration externe

### Prochaines étapes recommandées
1. [ ] Implémenter les tests
2. [ ] Optimiser le bundle size
3. [ ] Ajouter un loading skeleton pour les charts
4. [ ] Implémenter le dark mode
5. [ ] Ajouter la PWA (Progressive Web App)
6. [ ] Internationalisation (i18n)

## 🤝 Contribution

Pour contribuer au projet:
1. Créer une branche depuis `feature/spa-react-migration`
2. Développer votre fonctionnalité
3. Tester localement
4. Soumettre une Pull Request

## 📚 Ressources

### Documentation
- [React](https://react.dev/)
- [Vite](https://vitejs.dev/)
- [Tailwind CSS](https://tailwindcss.com/)
- [TanStack Query](https://tanstack.com/query)
- [React Router](https://reactrouter.com/)
- [Auth0 React](https://auth0.com/docs/quickstart/spa/react)
- [Django REST Framework](https://www.django-rest-framework.org/)

### Tutoriels
- Migration SSR vers SPA
- Django + React best practices
- Auth0 integration
- Plotly.js avec React

---

**Date de migration**: 2026-01-09
**Version**: 1.0.0
**Auteur**: Migration automatique via Claude Code
