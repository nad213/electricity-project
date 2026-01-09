# ElecFlow Frontend - React SPA

Application React moderne pour la visualisation des données électriques françaises.

## Stack Technique

- **Framework**: React 18 avec TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **State Management**: TanStack Query (React Query)
- **Routing**: React Router v6
- **Authentication**: Auth0 React SDK
- **Charts**: Plotly.js avec react-plotly.js
- **HTTP Client**: Axios

## Prérequis

- Node.js >= 18
- npm >= 9

## Configuration

1. Copier le fichier d'exemple des variables d'environnement:
```bash
cp .env.example .env.local
```

2. Configurer les variables d'environnement dans `.env.local`:
```
VITE_API_URL=http://localhost:8000/api
VITE_AUTH0_DOMAIN=votre-domaine.auth0.com
VITE_AUTH0_CLIENT_ID=votre-client-id
VITE_AUTH0_AUDIENCE=votre-api-audience
VITE_AUTH0_REDIRECT_URI=http://localhost:5173
```

## Installation

```bash
npm install
```

## Développement

Démarrer le serveur de développement:

```bash
npm run dev
```

L'application sera accessible sur `http://localhost:5173`

**Important**: Le backend Django doit être en cours d'exécution sur `http://localhost:8000` pour que l'API fonctionne.

## Build pour Production

```bash
npm run build
```

Les fichiers de production seront générés dans le dossier `dist/`.

## Prévisualisation du Build

```bash
npm run preview
```

## Structure du Projet

```
src/
├── components/         # Composants réutilisables
│   ├── DateRangeFilter.tsx
│   └── PlotlyChart.tsx
├── layouts/           # Layouts de l'application
│   └── MainLayout.tsx
├── pages/            # Pages de l'application
│   ├── HomePage.tsx
│   ├── ConsumptionPage.tsx
│   ├── ProductionPage.tsx
│   └── ExchangesPage.tsx
├── services/         # Services API
│   └── api.ts
├── types/           # Types TypeScript
│   └── api.ts
├── App.tsx          # Composant principal
├── main.tsx         # Point d'entrée
└── index.css        # Styles globaux
```

## Fonctionnalités

### Pages

- **Accueil**: Vue d'ensemble avec navigation vers les différentes sections
- **Consommation**: Visualisation de la consommation électrique (courbe de puissance, données annuelles et mensuelles)
- **Production**: Visualisation de la production par filière énergétique
- **Échanges**: Visualisation des échanges commerciaux avec les pays voisins

### Authentification

L'application utilise Auth0 pour l'authentification. Toutes les routes sont protégées et nécessitent une authentification.

### API

L'application communique avec le backend Django REST Framework via:
- `/api/consumption/*` - Endpoints de consommation
- `/api/production/*` - Endpoints de production
- `/api/exchanges/*` - Endpoints d'échanges

## Scripts Disponibles

- `npm run dev` - Démarrer le serveur de développement
- `npm run build` - Créer un build de production
- `npm run preview` - Prévisualiser le build de production
- `npm run lint` - Linter le code TypeScript

## Personnalisation des Couleurs

Les couleurs du thème sont définies dans `tailwind.config.js`:
- **Navy**: Couleur principale de la navigation et des éléments d'interface
- **Primary**: Couleur d'accentuation

Pour modifier les couleurs, éditez les valeurs dans le fichier de configuration Tailwind.
