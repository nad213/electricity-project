from django.contrib import admin
from django.urls import path, include

from consommation.api import api

urlpatterns = [
    path('admin/', admin.site.urls),
    # API publique JSON (Ninja). Déclarée avant l'include racine pour ne pas
    # entrer en conflit avec la page portail '/api/' de consommation.urls.
    path('api/v1/', api.urls),
    path('', include('consommation.urls')),  # Redirect to our app
]