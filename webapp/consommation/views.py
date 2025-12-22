from django.shortcuts import render
from datetime import datetime, timedelta
import plotly.express as px
import plotly.io as pio
from .services import get_date_range, get_puissance_data, get_annual_data, get_monthly_data


def accueil(request):
    """
    Home page - welcome page
    """
    return render(request, 'consommation/accueil.html')


def index(request):
    """
    Main view - displays consumption data with Plotly charts
    """
    # Get available min/max dates
    min_date, max_date = get_date_range()

    # Default dates (last 90 days)
    default_start = max_date - timedelta(days=90)

    # Get dates from URL query parameters (GET)
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    else:
        start_date = default_start
        
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = max_date
    
    # Load data
    df_puissance = get_puissance_data(start_date, end_date)
    df_annuel = get_annual_data()
    df_mensuel = get_monthly_data()

    # Harmonized color palette (Tabler colors)
    COLOR_PRIMARY = '#206bc4'      # Tabler primary blue
    COLOR_SECONDARY = '#6366f1'    # Tabler indigo
    COLOR_SUCCESS = '#10b981'      # Tabler green

    # ========== CHART 1: Power curve ==========
    fig1 = px.line(
        df_puissance,
        x='date_heure',
        y='consommation',
        color='source',
        color_discrete_map={
            'Données Consolidées': COLOR_PRIMARY,
            'Temps Réel': COLOR_SECONDARY
        },
    )
    fig1.update_layout(
        legend_title_text='',
        legend=dict(
            orientation="h",
            x=1.0,
            y=-0.15,
            xanchor="right",
        ),
        xaxis_title_text='',
        yaxis_title_text='MW',
        margin=dict(l=50, r=20, t=20, b=60),
        height=450,
        plot_bgcolor='white',
    )
    fig1.update_xaxes(gridcolor='#E5E7EB')
    fig1.update_yaxes(gridcolor='#E5E7EB')

    # ========== CHART 2: Annual consumption ==========
    fig2 = px.bar(
        df_annuel,
        x='annee',
        y='consommation_annuelle',
        color_discrete_sequence=[COLOR_PRIMARY],
    )
    fig2.update_layout(
        xaxis_title_text='',
        yaxis_title_text='MWh',
        margin=dict(l=50, r=20, t=20, b=40),
        height=400,
        plot_bgcolor='white',
    )
    fig2.update_xaxes(gridcolor='#E5E7EB')
    fig2.update_yaxes(gridcolor='#E5E7EB')

    # ========== CHART 3: Monthly consumption ==========
    fig3 = px.bar(
        df_mensuel,
        x='annee_mois_str',
        y='consommation_mensuelle',
        color_discrete_sequence=[COLOR_SECONDARY],
    )
    fig3.update_layout(
        xaxis_title_text='',
        yaxis_title_text='MWh',
        margin=dict(l=50, r=20, t=20, b=40),
        height=400,
        plot_bgcolor='white',
    )
    fig3.update_xaxes(gridcolor='#E5E7EB', tickangle=45)
    fig3.update_yaxes(gridcolor='#E5E7EB')
    
    # Convert charts to HTML
    graph_puissance = pio.to_html(fig1, full_html=False, include_plotlyjs='cdn')
    graph_annuel = pio.to_html(fig2, full_html=False, include_plotlyjs=False)
    graph_mensuel = pio.to_html(fig3, full_html=False, include_plotlyjs=False)
    
    context = {
        'titre': 'Consommation',
        'min_date': min_date,
        'max_date': max_date,
        'start_date': start_date,
        'end_date': end_date,
        'graph_puissance': graph_puissance,
        'graph_annuel': graph_annuel,
        'graph_mensuel': graph_mensuel,
        'nb_lignes': len(df_puissance),
    }

    return render(request, 'consommation/index.html', context)


def production(request):
    """
    Production page - placeholder for future production data
    """
    return render(request, 'consommation/production.html')


def echanges(request):
    """
    Échanges page - placeholder for future exchange data
    """
    return render(request, 'consommation/echanges.html')