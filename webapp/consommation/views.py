from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest
from datetime import datetime, timedelta
import plotly.express as px
import plotly.io as pio
import csv
from functools import wraps
from .services import (
    get_date_range, get_puissance_data, get_annual_data, get_monthly_data,
    get_production_date_range, get_production_filieres, get_production_data
)


# ========== Constants ==========
class Colors:
    """Tabler color palette"""
    PRIMARY = '#206bc4'      # Tabler primary blue
    SECONDARY = '#6366f1'    # Tabler indigo
    SUCCESS = '#10b981'      # Tabler green


class ChartConfig:
    """Default configuration for charts"""
    GRID_COLOR = '#E5E7EB'
    BACKGROUND_COLOR = 'white'
    LINE_CHART_HEIGHT = 450
    BAR_CHART_HEIGHT = 400
    MARGIN_WITH_LEGEND = dict(l=50, r=20, t=20, b=60)
    MARGIN_DEFAULT = dict(l=50, r=20, t=20, b=40)


# ========== Decorators ==========
def handle_validation_errors(func):
    """
    Decorator to handle validation errors uniformly
    Catches ValueError exceptions and returns HttpResponseBadRequest
    """
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))
    return wrapper


# ========== Validators ==========
def validate_date(date_str, param_name):
    """
    Validates a date string and returns a date object or None
    Raises ValueError with a user-friendly message if invalid
    """
    if not date_str:
        return None

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        # Check if date is not in the future
        if date_obj > datetime.now().date():
            raise ValueError(f"{param_name} ne peut pas être dans le futur")
        # Check if date is reasonable (not before 2000)
        if date_obj.year < 2000:
            raise ValueError(f"{param_name} doit être après l'année 2000")
        return date_obj
    except ValueError as e:
        if "does not match format" in str(e):
            raise ValueError(f"{param_name} doit être au format AAAA-MM-JJ")
        raise


def validate_and_get_dates(request, min_date, max_date):
    """
    Validates and returns start_date and end_date from request
    Returns tuple (start_date, end_date) or raises HttpResponseBadRequest
    """
    # Default dates (last 90 days)
    default_start = max_date - timedelta(days=90)

    # Get dates from URL query parameters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    # Validate dates
    start_date = validate_date(start_date_str, "Date de début")
    if start_date is None:
        start_date = default_start

    end_date = validate_date(end_date_str, "Date de fin")
    if end_date is None:
        end_date = max_date

    # Check date range validity
    if start_date > end_date:
        raise ValueError("La date de début doit être antérieure à la date de fin")

    # Check if dates are within available range
    if start_date < min_date or end_date > max_date:
        raise ValueError(f"Les dates doivent être entre {min_date} et {max_date}")

    return start_date, end_date


# ========== Chart Creation ==========
def create_line_chart(df, x_col, y_col, source_col='source', source_labels=None):
    """
    Creates a standardized Plotly line chart

    Args:
        df: DataFrame with data
        x_col: Column name for x-axis
        y_col: Column name for y-axis
        source_col: Column name for color grouping (default: 'source')
        source_labels: Dict mapping source values to display labels

    Returns:
        HTML string of the chart
    """
    # Default source labels mapping
    if source_labels is None:
        source_labels = {
            'Données Consolidées': Colors.PRIMARY,
            'Temps Réel': Colors.SECONDARY,
            'Consolidated Data': Colors.PRIMARY,
            'Real-Time Data': Colors.SECONDARY
        }

    fig = px.line(
        df,
        x=x_col,
        y=y_col,
        color=source_col,
        color_discrete_map=source_labels,
    )
    fig.update_layout(
        legend_title_text='',
        legend=dict(
            orientation="h",
            x=1.0,
            y=-0.15,
            xanchor="right",
        ),
        xaxis_title_text='',
        yaxis_title_text='MW',
        margin=ChartConfig.MARGIN_WITH_LEGEND,
        height=ChartConfig.LINE_CHART_HEIGHT,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR)

    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')


def create_bar_chart(df, x_col, y_col, color=None, tickangle=0):
    """
    Creates a standardized Plotly bar chart

    Args:
        df: DataFrame with data
        x_col: Column name for x-axis
        y_col: Column name for y-axis
        color: Bar color (default: PRIMARY)
        tickangle: Angle for x-axis labels (default: 0)

    Returns:
        HTML string of the chart
    """
    if color is None:
        color = Colors.PRIMARY

    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        color_discrete_sequence=[color],
    )
    fig.update_layout(
        xaxis_title_text='',
        yaxis_title_text='MWh',
        margin=ChartConfig.MARGIN_DEFAULT,
        height=ChartConfig.BAR_CHART_HEIGHT,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR, tickangle=tickangle)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR)

    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


def accueil(request):
    """
    Home page - welcome page
    """
    return render(request, 'consommation/accueil.html')


# ========== Views ==========
@handle_validation_errors
def index(request):
    """
    Main view - displays consumption data with Plotly charts
    """
    # Get available min/max dates
    min_date, max_date = get_date_range()

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load data
    df_puissance = get_puissance_data(start_date, end_date)
    df_annuel = get_annual_data()
    df_mensuel = get_monthly_data()

    # ========== CHART 1: Power curve ==========
    graph_puissance = create_line_chart(
        df_puissance,
        x_col='date_heure',
        y_col='consommation',
        source_labels={
            'Données Consolidées': Colors.PRIMARY,
            'Temps Réel': Colors.SECONDARY
        }
    )

    # ========== CHART 2: Annual consumption ==========
    graph_annuel = create_bar_chart(
        df_annuel,
        x_col='annee',
        y_col='consommation_annuelle',
        color=Colors.PRIMARY
    )

    # ========== CHART 3: Monthly consumption ==========
    graph_mensuel = create_bar_chart(
        df_mensuel,
        x_col='annee_mois_str',
        y_col='consommation_mensuelle',
        color=Colors.SECONDARY,
        tickangle=45
    )
    
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


@handle_validation_errors
def production(request):
    """
    Production page - displays production data with load curve by sector
    """
    # Get available min/max dates
    min_date, max_date = get_production_date_range()

    # Validate filiere
    filiere = request.GET.get('filiere', 'nucleaire')
    filieres = get_production_filieres()
    if filiere not in filieres:
        return HttpResponseBadRequest(f"Filière invalide. Choisissez parmi: {', '.join(filieres.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load production data
    df_production = get_production_data(start_date, end_date, filiere)

    # Create production curve chart
    graph_production = create_line_chart(
        df_production,
        x_col='date_heure',
        y_col='production'
    )

    context = {
        'titre': 'Production',
        'min_date': min_date,
        'max_date': max_date,
        'start_date': start_date,
        'end_date': end_date,
        'filiere': filiere,
        'filieres': filieres,
        'graph_production': graph_production,
        'nb_lignes': len(df_production),
    }

    return render(request, 'consommation/production.html', context)


def echanges(request):
    """
    Échanges page - placeholder for future exchange data
    """
    return render(request, 'consommation/echanges.html')


# ========== Export Functions ==========
def _export_to_csv(df, filename, columns):
    """
    Generic CSV export function

    Args:
        df: DataFrame to export
        filename: Name of the CSV file
        columns: List of column names to export

    Returns:
        HttpResponse with CSV content
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(columns)

    # Performance: use values.tolist() instead of iterrows()
    writer.writerows(df[columns].values.tolist())

    return response


@handle_validation_errors
def export_puissance_csv(request):
    """
    Export power consumption data to CSV
    """
    # Get available min/max dates
    min_date, max_date = get_date_range()

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load data
    df = get_puissance_data(start_date, end_date)

    # Export to CSV
    filename = f'consommation_puissance_{start_date}_{end_date}.csv'
    return _export_to_csv(df, filename, ['date_heure', 'consommation', 'source'])


def export_annuel_csv(request):
    """
    Export annual consumption data to CSV
    """
    df = get_annual_data()
    return _export_to_csv(df, 'consommation_annuelle.csv', ['annee', 'consommation_annuelle'])


def export_mensuel_csv(request):
    """
    Export monthly consumption data to CSV
    """
    df = get_monthly_data()
    return _export_to_csv(df, 'consommation_mensuelle.csv', ['annee_mois_str', 'consommation_mensuelle'])


@handle_validation_errors
def export_production_csv(request):
    """
    Export production data to CSV
    """
    # Get available min/max dates
    min_date, max_date = get_production_date_range()

    # Validate filiere
    filiere = request.GET.get('filiere', 'nucleaire')
    filieres = get_production_filieres()
    if filiere not in filieres:
        return HttpResponseBadRequest(f"Filière invalide. Choisissez parmi: {', '.join(filieres.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load data
    df = get_production_data(start_date, end_date, filiere)

    # Export to CSV
    filename = f'production_{filiere}_{start_date}_{end_date}.csv'
    return _export_to_csv(df, filename, ['date_heure', 'production', 'source'])