from django.urls import path
from . import views
from . import auth_views

app_name = 'consommation'

urlpatterns = [
    # Auth routes
    path('login/', auth_views.login, name='login'),
    path('callback/', auth_views.callback, name='callback'),
    path('logout/', auth_views.logout, name='logout'),

    # App routes
    path('', views.accueil, name='accueil'),
    path('consommation/', views.index, name='index'),
    path('consommation/export-puissance/', views.export_puissance_csv, name='export_puissance'),
    path('consommation/export-annuel/', views.export_annuel_csv, name='export_annuel'),
    path('consommation/export-mensuel/', views.export_mensuel_csv, name='export_mensuel'),
    path('production/', views.production, name='production'),
    path('production/export-production/', views.export_production_csv, name='export_production'),
    path('production/export-annuel/', views.export_production_annuel_csv, name='export_production_annuel'),
    path('production/export-mensuel/', views.export_production_mensuel_csv, name='export_production_mensuel'),
    path('echanges/', views.echanges, name='echanges'),
    path('echanges/export/', views.export_echanges_csv, name='export_echanges'),
]