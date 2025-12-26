# Guide de déploiement sur Render

## Prérequis

- Un compte Render (gratuit ou payant)
- Votre repository GitHub : https://github.com/nad213/electricity-project.git
- Vos credentials AWS pour accéder au bucket S3

## Étapes de déploiement

### 1. Pousser les fichiers de configuration sur GitHub

Les fichiers suivants ont été créés pour le déploiement :
- `build.sh` : Script de build exécuté par Render
- `render.yaml` : Configuration automatique du service

```bash
git add build.sh render.yaml .gitignore webapp/config/settings.py
git commit -m "Configuration pour déploiement sur Render"
git push origin master
```

### 2. Créer un nouveau Web Service sur Render

1. Connectez-vous sur [Render](https://dashboard.render.com/)
2. Cliquez sur **"New +"** puis **"Web Service"**
3. Connectez votre repository GitHub : `nad213/electricity-project`
4. Render détectera automatiquement le fichier `render.yaml`

### 3. Configuration des variables d'environnement

Render va créer automatiquement les variables d'environnement. Vous devez les remplir :

#### Variables obligatoires à configurer :

1. **ALLOWED_HOSTS**
   - Valeur : `votre-app.onrender.com` (remplacez par votre URL Render)
   - Ou : `votre-app.onrender.com,localhost,127.0.0.1`

2. **AWS_S3_REGION**
   - Valeur : `eu-west-3` (ou votre région)

3. **AWS_ACCESS_KEY_ID**
   - Votre clé d'accès AWS

4. **AWS_SECRET_ACCESS_KEY**
   - Votre clé secrète AWS

5. **S3_PATH_PUISSANCE**
   - Exemple : `s3://your-bucket-name/consommation_france_puissance.parquet`

6. **S3_PATH_ANNUEL**
   - Exemple : `s3://your-bucket-name/consommation_annuelle.parquet`

7. **S3_PATH_MENSUEL**
   - Exemple : `s3://your-bucket-name/consommation_mensuelle.parquet`

8. **S3_PATH_PRODUCTION**
   - Exemple : `s3://your-bucket-name/production_data.parquet`

#### Variables auto-générées :

- **SECRET_KEY** : Généré automatiquement par Render (ne pas modifier)
- **DEBUG** : Déjà configuré à `False` (production)

### 4. Déploiement

1. Vérifiez la configuration dans l'onglet **"Environment"**
2. Cliquez sur **"Create Web Service"**
3. Render va automatiquement :
   - Cloner votre repository
   - Exécuter `build.sh` (installation des dépendances + collecte des fichiers statiques)
   - Démarrer l'application avec Gunicorn

### 5. Vérification

Une fois le déploiement terminé :
- Votre application sera accessible à l'URL : `https://votre-app.onrender.com`
- Vérifiez les logs dans l'onglet **"Logs"** de Render
- Testez l'accès à votre application

## Configuration avancée

### Plan gratuit vs Plan payant

**Plan gratuit** :
- L'application se met en veille après 15 min d'inactivité
- Redémarrage lent (peut prendre 30-60 secondes)
- 750 heures/mois gratuites
- Suffisant pour un prototype ou démo

**Plan Starter ($7/mois)** :
- Toujours actif
- Performances constantes
- Recommandé pour production

### Domaine personnalisé

1. Dans Render, allez dans **"Settings"** → **"Custom Domain"**
2. Ajoutez votre domaine
3. Configurez les DNS selon les instructions Render
4. Mettez à jour la variable `ALLOWED_HOSTS` avec votre nouveau domaine

### Surveillance et logs

- **Logs en temps réel** : Onglet "Logs" dans Render
- **Métriques** : CPU, mémoire, requêtes dans "Metrics"
- **Alertes** : Configurables dans les paramètres du service

## Dépannage

### Erreur "DisallowedHost"
- Vérifiez que `ALLOWED_HOSTS` contient l'URL de votre app Render

### Erreur AWS S3
- Vérifiez vos credentials AWS
- Vérifiez que les chemins S3 sont corrects
- Vérifiez les permissions IAM de votre utilisateur AWS

### Fichiers statiques ne se chargent pas
- Vérifiez que `build.sh` s'est bien exécuté
- Consultez les logs de build dans Render

### Application lente à démarrer
- Normal sur le plan gratuit (mise en veille)
- Upgrader vers un plan payant pour résoudre

## Commandes utiles

### Forcer un redéploiement
```bash
git commit --allow-empty -m "Force redeploy"
git push origin master
```

### Voir les logs localement avant de déployer
```bash
cd webapp
python manage.py collectstatic --no-input
gunicorn config.wsgi:application
```

## Sécurité

Les paramètres de sécurité Django suivants sont activés en production :
- ✅ HTTPS obligatoire
- ✅ Cookies sécurisés
- ✅ Protection CSRF
- ✅ Protection XSS
- ✅ HSTS (HTTP Strict Transport Security)

## Prochaines étapes

1. Configurer un monitoring (ex: UptimeRobot)
2. Mettre en place des sauvegardes
3. Configurer des alertes email
4. Ajouter un CDN si nécessaire (Cloudflare)

## Support

- Documentation Render : https://render.com/docs
- Documentation Django : https://docs.djangoproject.com/
