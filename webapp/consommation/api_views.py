"""
API views for the Consommation app
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import HttpResponse
import pandas as pd
from datetime import datetime
import io

from .services import (
    get_puissance_data,
    get_annual_data,
    get_monthly_data,
    get_available_dates,
    get_production_data,
    get_production_annual_data,
    get_production_monthly_data,
    get_available_production_sectors,
    get_echanges_data,
    get_available_echanges_countries,
)
from .serializers import (
    DateRangeSerializer,
    SectorSerializer,
    CountrySerializer,
    AvailableDatesSerializer,
    MetadataSerializer,
)


def create_plotly_data(df, x_col, y_col, name=None, chart_type='scatter', mode='lines'):
    """
    Create Plotly trace data from DataFrame
    """
    trace = {
        'x': df[x_col].tolist() if x_col in df.columns else [],
        'y': df[y_col].tolist() if y_col in df.columns else [],
        'type': chart_type,
        'name': name or y_col,
    }

    if chart_type == 'scatter':
        trace['mode'] = mode
        trace['line'] = {'width': 2}

    return trace


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consumption_metadata(request):
    """Get metadata for consumption endpoints"""
    try:
        dates = get_available_dates()
        serializer = AvailableDatesSerializer(dates)
        return Response(serializer.data)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consumption_power_curve(request):
    """Get power consumption curve data"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_puissance_data(date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        trace = create_plotly_data(df, 'date_heure', 'consommation', 'Consommation')

        layout = {
            'title': 'Courbe de puissance',
            'xaxis': {'title': 'Date et heure'},
            'yaxis': {'title': 'Puissance (MW)'},
            'hovermode': 'x unified',
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': [trace],
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consumption_annual_chart(request):
    """Get annual consumption chart data"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_annual_data(date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        trace = {
            'x': df['annee'].tolist(),
            'y': df['consommation'].tolist(),
            'type': 'bar',
            'name': 'Consommation annuelle',
        }

        layout = {
            'title': 'Consommation énergétique annuelle',
            'xaxis': {'title': 'Année'},
            'yaxis': {'title': 'Énergie (MWh)'},
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': [trace],
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consumption_monthly_chart(request):
    """Get monthly consumption chart data"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_monthly_data(date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        df['mois_annee'] = df['annee'].astype(str) + '-' + df['mois'].astype(str).str.zfill(2)

        trace = {
            'x': df['mois_annee'].tolist(),
            'y': df['consommation'].tolist(),
            'type': 'bar',
            'name': 'Consommation mensuelle',
        }

        layout = {
            'title': 'Consommation énergétique mensuelle',
            'xaxis': {'title': 'Mois'},
            'yaxis': {'title': 'Énergie (MWh)'},
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': [trace],
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def production_metadata(request):
    """Get metadata for production endpoints"""
    try:
        sectors = get_available_production_sectors()
        dates = get_available_dates()

        return Response({
            'sectors': sectors,
            'available_dates': {
                'min_date': dates['min_date'],
                'max_date': dates['max_date'],
            }
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def production_power_curve(request):
    """Get production power curve by sector"""
    serializer = SectorSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        secteur = serializer.validated_data['secteur']
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_production_data(secteur, date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        trace = create_plotly_data(df, 'date_heure', 'production', secteur)

        layout = {
            'title': f'Courbe de production - {secteur}',
            'xaxis': {'title': 'Date et heure'},
            'yaxis': {'title': 'Production (MW)'},
            'hovermode': 'x unified',
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': [trace],
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def production_annual_chart(request):
    """Get annual production chart data"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_production_annual_data(date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        # Get all sectors dynamically from the dataframe
        sectors = [col for col in df.columns if col not in ['annee', 'production_totale']]

        traces = []
        for secteur in sectors:
            if secteur in df.columns:
                traces.append({
                    'x': df['annee'].tolist(),
                    'y': df[secteur].tolist(),
                    'type': 'bar',
                    'name': secteur,
                })

        layout = {
            'title': 'Production énergétique annuelle par filière',
            'xaxis': {'title': 'Année'},
            'yaxis': {'title': 'Production (MWh)'},
            'barmode': 'stack',
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': traces,
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def production_monthly_chart(request):
    """Get monthly production chart data"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_production_monthly_data(date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        df['mois_annee'] = df['annee'].astype(str) + '-' + df['mois'].astype(str).str.zfill(2)

        # Get all sectors dynamically from the dataframe
        sectors = [col for col in df.columns if col not in ['annee', 'mois', 'mois_annee', 'production_totale']]

        traces = []
        for secteur in sectors:
            if secteur in df.columns:
                traces.append({
                    'x': df['mois_annee'].tolist(),
                    'y': df[secteur].tolist(),
                    'type': 'bar',
                    'name': secteur,
                })

        layout = {
            'title': 'Production énergétique mensuelle par filière',
            'xaxis': {'title': 'Mois'},
            'yaxis': {'title': 'Production (MWh)'},
            'barmode': 'stack',
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': traces,
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exchanges_metadata(request):
    """Get metadata for exchanges endpoints"""
    try:
        countries = get_available_echanges_countries()
        dates = get_available_dates()

        return Response({
            'countries': countries,
            'available_dates': {
                'min_date': dates['min_date'],
                'max_date': dates['max_date'],
            }
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exchanges_curve(request):
    """Get exchanges curve by country"""
    serializer = CountrySerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        pays = serializer.validated_data['pays']
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_echanges_data(pays, date_debut, date_fin)

        if df.empty:
            return Response({'data': [], 'layout': {}, 'config': {}})

        trace = create_plotly_data(df, 'date_heure', 'echange', pays)

        layout = {
            'title': f'Échanges commerciaux - {pays}',
            'xaxis': {'title': 'Date et heure'},
            'yaxis': {'title': 'Échange (MW)'},
            'hovermode': 'x unified',
        }

        config = {
            'displayModeBar': True,
            'displaylogo': False,
        }

        return Response({
            'data': [trace],
            'layout': layout,
            'config': config,
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# CSV Export endpoints
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_consumption_power_csv(request):
    """Export power consumption data as CSV"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_puissance_data(date_debut, date_fin)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="consommation_puissance_{date_debut}_{date_fin}.csv"'

        df.to_csv(response, index=False, encoding='utf-8')
        return response

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_consumption_annual_csv(request):
    """Export annual consumption data as CSV"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_annual_data(date_debut, date_fin)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="consommation_annuelle_{date_debut}_{date_fin}.csv"'

        df.to_csv(response, index=False, encoding='utf-8')
        return response

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_consumption_monthly_csv(request):
    """Export monthly consumption data as CSV"""
    serializer = DateRangeSerializer(data=request.query_params)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_debut = serializer.validated_data['date_debut']
        date_fin = serializer.validated_data['date_fin']

        df = get_monthly_data(date_debut, date_fin)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="consommation_mensuelle_{date_debut}_{date_fin}.csv"'

        df.to_csv(response, index=False, encoding='utf-8')
        return response

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
