from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import csv
from functools import wraps
from .services import (
    get_date_range, get_puissance_data, get_annual_data, get_monthly_data,
    get_production_date_range, get_production_filieres, get_production_data,
    get_production_annual_data, get_production_monthly_data,
    get_echanges_date_range, get_echanges_pays, get_echanges_data
)


# ========== Constants ==========
class Colors:
    """Dark modern color palette for charts"""
    PRIMARY = '#22D3EE'      # Cyan electric
    SECONDARY = '#67E8F9'    # Cyan light
    ACCENT = '#FBBF24'       # Amber
    SUCCESS = '#10B981'      # Emerald


class ProductionColors:
    """Color palette for production sectors - vibrant on dark"""
    NUCLEAIRE = '#F59E0B'      # Amber
    HYDRAULIQUE = '#06B6D4'    # Cyan
    EOLIEN = '#10B981'         # Emerald
    SOLAIRE = '#FBBF24'        # Yellow
    GAZ = '#EF4444'            # Red
    CHARBON = '#6B7280'        # Gray
    FIOUL = '#A78BFA'          # Violet
    BIOENERGIES = '#34D399'    # Teal


class ChartConfig:
    """Default configuration for charts - dark transparent background"""
    GRID_COLOR = '#27272A'
    BACKGROUND_COLOR = 'rgba(0,0,0,0)'
    PAPER_COLOR = 'rgba(0,0,0,0)'
    TEXT_COLOR = '#A1A1AA'
    AXIS_COLOR = '#3F3F46'
    LINE_CHART_HEIGHT = 450
    BAR_CHART_HEIGHT = 400
    MARGIN_WITH_LEGEND = dict(l=50, r=20, t=20, b=60)
    MARGIN_NO_LEGEND = dict(l=50, r=20, t=20, b=40)
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
    # Default dates (last 15 days)
    default_start = max_date - timedelta(days=15)

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

    # Check if there are multiple unique values in the source column
    unique_sources = df[source_col].nunique() if source_col in df.columns else 1
    show_legend = unique_sources > 1

    fig = px.line(
        df,
        x=x_col,
        y=y_col,
        color=source_col if show_legend else None,
        color_discrete_map=source_labels if show_legend else None,
    )

    # Configure layout based on whether legend is needed
    if show_legend:
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
            paper_bgcolor=ChartConfig.PAPER_COLOR,
            font=dict(color=ChartConfig.TEXT_COLOR),
        )
    else:
        fig.update_layout(
            showlegend=False,
            xaxis_title_text='',
            yaxis_title_text='MW',
            margin=ChartConfig.MARGIN_NO_LEGEND,
            height=ChartConfig.LINE_CHART_HEIGHT,
            plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
            paper_bgcolor=ChartConfig.PAPER_COLOR,
            font=dict(color=ChartConfig.TEXT_COLOR),
        )

    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR, zerolinecolor=ChartConfig.GRID_COLOR)

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
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR, tickangle=tickangle)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR)

    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


def create_stacked_bar_chart(df, x_col, y_cols, colors, labels):
    """
    Creates a stacked bar chart with Plotly

    Args:
        df: DataFrame with data
        x_col: Column name for x-axis
        y_cols: List of column names to stack
        colors: Dict mapping column names to colors
        labels: Dict mapping column names to display labels

    Returns:
        HTML string of the chart
    """
    fig = go.Figure()

    # Add a trace for each filiere
    for col in y_cols:
        if col in df.columns:
            fig.add_trace(go.Bar(
                x=df[x_col],
                y=df[col],
                name=labels.get(col, col),
                marker_color=colors.get(col, Colors.PRIMARY),
            ))

    fig.update_layout(
        barmode='stack',
        xaxis_title_text='',
        yaxis_title_text='MWh',
        margin=ChartConfig.MARGIN_WITH_LEGEND,
        height=ChartConfig.BAR_CHART_HEIGHT,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
        legend=dict(
            orientation="h",
            x=0.5,
            y=-0.2,
            xanchor="center",
        ),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
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
        x_col='year',
        y_col='yearly_consumption',
        color=Colors.PRIMARY
    )

    # ========== CHART 3: Monthly consumption ==========
    graph_mensuel = create_bar_chart(
        df_mensuel,
        x_col='year_month',
        y_col='monthly_consumption',
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
    Production page - displays production data with load curve by sector and stacked bar charts
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

    # Load production data for the line chart
    df_production = get_production_data(start_date, end_date, filiere)

    # Create production curve chart
    graph_production = create_line_chart(
        df_production,
        x_col='date_heure',
        y_col='production'
    )

    # Load annual and monthly aggregated data
    df_annual = get_production_annual_data()
    df_monthly = get_production_monthly_data()

    # Define filiere columns, colors and labels for stacked charts
    filiere_cols_annual = ['nucleaire_yearly_mwh', 'hydraulique_yearly_mwh', 'eolien_yearly_mwh',
                           'solaire_yearly_mwh', 'gaz_yearly_mwh', 'charbon_yearly_mwh',
                           'fioul_yearly_mwh', 'bioenergies_yearly_mwh']

    filiere_cols_monthly = ['nucleaire_mwh', 'hydraulique_mwh', 'eolien_mwh',
                            'solaire_mwh', 'gaz_mwh', 'charbon_mwh',
                            'fioul_mwh', 'bioenergies_mwh']

    colors = {
        'nucleaire_yearly_mwh': ProductionColors.NUCLEAIRE,
        'hydraulique_yearly_mwh': ProductionColors.HYDRAULIQUE,
        'eolien_yearly_mwh': ProductionColors.EOLIEN,
        'solaire_yearly_mwh': ProductionColors.SOLAIRE,
        'gaz_yearly_mwh': ProductionColors.GAZ,
        'charbon_yearly_mwh': ProductionColors.CHARBON,
        'fioul_yearly_mwh': ProductionColors.FIOUL,
        'bioenergies_yearly_mwh': ProductionColors.BIOENERGIES,
        'nucleaire_mwh': ProductionColors.NUCLEAIRE,
        'hydraulique_mwh': ProductionColors.HYDRAULIQUE,
        'eolien_mwh': ProductionColors.EOLIEN,
        'solaire_mwh': ProductionColors.SOLAIRE,
        'gaz_mwh': ProductionColors.GAZ,
        'charbon_mwh': ProductionColors.CHARBON,
        'fioul_mwh': ProductionColors.FIOUL,
        'bioenergies_mwh': ProductionColors.BIOENERGIES,
    }

    labels = {
        'nucleaire_yearly_mwh': 'Nucléaire',
        'hydraulique_yearly_mwh': 'Hydraulique',
        'eolien_yearly_mwh': 'Éolien',
        'solaire_yearly_mwh': 'Solaire',
        'gaz_yearly_mwh': 'Gaz',
        'charbon_yearly_mwh': 'Charbon',
        'fioul_yearly_mwh': 'Fioul',
        'bioenergies_yearly_mwh': 'Bioénergies',
        'nucleaire_mwh': 'Nucléaire',
        'hydraulique_mwh': 'Hydraulique',
        'eolien_mwh': 'Éolien',
        'solaire_mwh': 'Solaire',
        'gaz_mwh': 'Gaz',
        'charbon_mwh': 'Charbon',
        'fioul_mwh': 'Fioul',
        'bioenergies_mwh': 'Bioénergies',
    }

    # Create stacked bar charts
    graph_production_annuel = create_stacked_bar_chart(
        df_annual,
        x_col='year',
        y_cols=filiere_cols_annual,
        colors=colors,
        labels=labels
    )

    # Create year-month label for monthly chart
    df_monthly['annee_mois'] = df_monthly['year'].astype(str) + '-' + df_monthly['month'].astype(str).str.zfill(2)

    graph_production_mensuel = create_stacked_bar_chart(
        df_monthly,
        x_col='annee_mois',
        y_cols=filiere_cols_monthly,
        colors=colors,
        labels=labels
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
        'graph_production_annuel': graph_production_annuel,
        'graph_production_mensuel': graph_production_mensuel,
        'nb_lignes': len(df_production),
    }

    return render(request, 'consommation/production.html', context)


@handle_validation_errors
def echanges(request):
    """
    Échanges page - displays commercial exchange data with load curve by country
    """
    # Get available min/max dates
    min_date, max_date = get_echanges_date_range()

    # Validate pays
    pays = request.GET.get('pays', 'ech_physiques')
    pays_disponibles = get_echanges_pays()
    if pays not in pays_disponibles:
        return HttpResponseBadRequest(f"Pays invalide. Choisissez parmi: {', '.join(pays_disponibles.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load echanges data for the line chart
    df_echanges = get_echanges_data(start_date, end_date, pays)

    # Create echanges curve chart
    graph_echanges = create_line_chart(
        df_echanges,
        x_col='date_heure',
        y_col='echange'
    )

    context = {
        'titre': 'Échanges commerciaux',
        'min_date': min_date,
        'max_date': max_date,
        'start_date': start_date,
        'end_date': end_date,
        'pays': pays,
        'pays_options': pays_disponibles,
        'selected_pays': pays,
        'graph_echanges': graph_echanges,
        'row_count': len(df_echanges),
    }

    return render(request, 'consommation/echanges.html', context)


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
    return _export_to_csv(df, 'consommation_annuelle.csv', ['year', 'yearly_consumption'])


def export_mensuel_csv(request):
    """
    Export monthly consumption data to CSV
    """
    df = get_monthly_data()
    return _export_to_csv(df, 'consommation_mensuelle.csv', ['year_month', 'monthly_consumption'])


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


def export_production_annuel_csv(request):
    """
    Export annual production data by sector to CSV
    """
    df = get_production_annual_data()
    columns = ['year', 'nucleaire_yearly_mwh', 'hydraulique_yearly_mwh', 'eolien_yearly_mwh',
               'solaire_yearly_mwh', 'gaz_yearly_mwh', 'charbon_yearly_mwh',
               'fioul_yearly_mwh', 'bioenergies_yearly_mwh']
    return _export_to_csv(df, 'production_annuelle.csv', columns)


def export_production_mensuel_csv(request):
    """
    Export monthly production data by sector to CSV
    """
    df = get_production_monthly_data()
    columns = ['year', 'month', 'nucleaire_mwh', 'hydraulique_mwh', 'eolien_mwh',
               'solaire_mwh', 'gaz_mwh', 'charbon_mwh', 'fioul_mwh', 'bioenergies_mwh']
    return _export_to_csv(df, 'production_mensuelle.csv', columns)


@handle_validation_errors
def export_echanges_csv(request):
    """
    Export echanges data to CSV
    """
    # Get available min/max dates
    min_date, max_date = get_echanges_date_range()

    # Validate pays
    pays = request.GET.get('pays', 'ech_physiques')
    pays_disponibles = get_echanges_pays()
    if pays not in pays_disponibles:
        return HttpResponseBadRequest(f"Pays invalide. Choisissez parmi: {', '.join(pays_disponibles.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load data
    df = get_echanges_data(start_date, end_date, pays)

    # Export to CSV
    filename = f'echanges_{pays}_{start_date}_{end_date}.csv'
    return _export_to_csv(df, filename, ['date_heure', 'echange', 'source'])