from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('consommation/', views.index, name='index'),
    path('consommation/export-puissance/', views.export_puissance_csv, name='export_puissance'),
    path('consommation/export-annuel/', views.export_annuel_csv, name='export_annuel'),
    path('consommation/export-mensuel/', views.export_mensuel_csv, name='export_mensuel'),
    path('production/', views.production, name='production'),
    path('echanges/', views.echanges, name='echanges'),
]