from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('consommation/', views.index, name='index'),
    path('production/', views.production, name='production'),
    path('echanges/', views.echanges, name='echanges'),
]