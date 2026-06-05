from django.urls import path
from . import views
from . import auth_views
from . import chat_views
from . import api_key_views

app_name = 'consommation'

urlpatterns = [
    # Auth routes
    path('login/', auth_views.login, name='login'),
    path('callback/', auth_views.callback, name='callback'),
    path('logout/', auth_views.logout, name='logout'),

    # Chatbot
    path('chat/', chat_views.chat_page, name='chat'),
    path('chat/message/', chat_views.chat_message, name='chat_message'),

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
    path('production/export-parc-installe/', views.export_parc_installe_csv, name='export_parc_installe'),
    path('echanges/', views.echanges, name='echanges'),
    path('echanges/export/', views.export_echanges_csv, name='export_echanges'),
    path('echanges/export-annuel/', views.export_echanges_annuel_csv, name='export_echanges_annuel'),
    path('api/', views.api, name='api'),
    path('api/keys/generate/', api_key_views.generate_api_key, name='generate_api_key'),
    path('api/keys/<int:key_id>/revoke/', api_key_views.revoke_api_key, name='revoke_api_key'),
]