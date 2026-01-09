"""
API URL Configuration for Consommation app
"""
from django.urls import path
from . import api_views

app_name = 'api_consommation'

urlpatterns = [
    # Consumption endpoints
    path('consumption/metadata/', api_views.consumption_metadata, name='consumption-metadata'),
    path('consumption/power-curve/', api_views.consumption_power_curve, name='consumption-power-curve'),
    path('consumption/annual/', api_views.consumption_annual_chart, name='consumption-annual'),
    path('consumption/monthly/', api_views.consumption_monthly_chart, name='consumption-monthly'),

    # Consumption CSV exports
    path('consumption/export/power/', api_views.export_consumption_power_csv, name='export-power'),
    path('consumption/export/annual/', api_views.export_consumption_annual_csv, name='export-annual'),
    path('consumption/export/monthly/', api_views.export_consumption_monthly_csv, name='export-monthly'),

    # Production endpoints
    path('production/metadata/', api_views.production_metadata, name='production-metadata'),
    path('production/power-curve/', api_views.production_power_curve, name='production-power-curve'),
    path('production/annual/', api_views.production_annual_chart, name='production-annual'),
    path('production/monthly/', api_views.production_monthly_chart, name='production-monthly'),

    # Exchanges endpoints
    path('exchanges/metadata/', api_views.exchanges_metadata, name='exchanges-metadata'),
    path('exchanges/curve/', api_views.exchanges_curve, name='exchanges-curve'),
]
