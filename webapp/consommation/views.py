from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from datetime import datetime, timedelta
import json
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import csv
from functools import wraps

from .services import (
    get_date_range, get_puissance_data, get_annual_data, get_monthly_data,
    get_production_date_range, get_production_filieres, get_production_data,
    get_production_data_multi,
    get_production_annual_data, get_production_monthly_data,
    get_echanges_date_range, get_echanges_pays, get_echanges_pays_commerciaux,
    get_echanges_data, get_echanges_data_multi,
    get_echanges_annual_import_export, get_echanges_annual_detail,
    get_dashboard_data, get_parc_installe_data,
)
from .constants import (
    Colors, ChartConfig, ProductionColors, FILIERE_COLORS, FILIERES,
    PAYS_ECHANGES_COLORS,
    get_production_colors_and_labels, get_filiere_columns, get_csv_header
)


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
def create_line_chart(df, x_col, y_col, color=None, y_label='Valeur'):
    """
    Creates a standardized Plotly line chart

    Args:
        df: DataFrame with data
        x_col: Column name for x-axis
        y_col: Column name for y-axis
        color: Line color (default: PRIMARY)
        y_label: Label for y-axis in hover tooltip

    Returns:
        HTML string of the chart
    """
    if color is None:
        color = Colors.PRIMARY

    fig = px.line(
        df,
        x=x_col,
        y=y_col,
        color_discrete_sequence=[color],
    )

    # Custom hover template (French locale: space as thousands separator)
    fig.update_layout(separators=", ")
    fig.update_traces(
        hovertemplate=f"Date: %{{x|%d/%m/%Y %H:%M}}<br>{y_label}: %{{y:,.0f}} MW<extra></extra>"
    )

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

    return fig.to_json()


def create_multi_line_chart(df, x_col, filieres, colors, labels):
    """
    Creates a Plotly line chart with one line per filière, each with its own
    color and a legend.

    Args:
        df: Wide DataFrame with x_col and one column per filière
        x_col: Column name for x-axis
        filieres: List of filière keys (also the column names in df)
        colors: dict {filiere_key: hex_color}
        labels: dict {filiere_key: French label}

    Returns:
        JSON string of the Plotly figure
    """
    fig = go.Figure()
    for filiere in filieres:
        if filiere not in df.columns:
            continue
        label = labels.get(filiere, filiere)
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=df[filiere],
            name=label,
            mode='lines',
            line=dict(color=colors.get(filiere, Colors.PRIMARY)),
            hovertemplate=f"Date: %{{x|%d/%m/%Y %H:%M}}<br>{label}: %{{y:,.0f}} MW<extra></extra>",
        ))

    fig.update_layout(separators=", ")
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation='h', yanchor='top', y=-0.12, xanchor='center', x=0.5),
        xaxis_title_text='',
        yaxis_title_text='MW',
        margin=ChartConfig.MARGIN_WITH_LEGEND,
        height=ChartConfig.LINE_CHART_HEIGHT,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
    )

    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR, zerolinecolor=ChartConfig.GRID_COLOR)

    return fig.to_json()


def create_bar_chart(df, x_col, y_col, color=None, tickangle=0, y_label='Consommation', x_date_format=None):
    """
    Creates a standardized Plotly bar chart

    Args:
        df: DataFrame with data
        x_col: Column name for x-axis
        y_col: Column name for y-axis
        color: Bar color (default: PRIMARY)
        tickangle: Angle for x-axis labels (default: 0)
        y_label: Label for y-axis in hover tooltip
        x_date_format: Optional d3 date format applied to both the axis ticks
            and the hover x value (e.g. '%B %Y' for full month + year). Use it
            for date axes to avoid the day and the abbreviated month names.

    Returns:
        HTML string of the chart
    """
    if color is None:
        color = Colors.PRIMARY

    # Convert MWh to TWh
    df = df.copy()
    df[y_col] = df[y_col] / 1_000_000

    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        color_discrete_sequence=[color],
    )

    # Custom hover template (French locale: space as thousands separator)
    x_hover = f"%{{x|{x_date_format}}}" if x_date_format else "%{x}"
    fig.update_layout(separators=", ")
    fig.update_traces(
        hovertemplate=f"Période: {x_hover}<br>{y_label}: %{{y:,.1f}} TWh<extra></extra>"
    )

    fig.update_layout(
        xaxis_title_text='',
        yaxis_title_text='TWh',
        margin=ChartConfig.MARGIN_DEFAULT,
        height=ChartConfig.BAR_CHART_HEIGHT,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR, tickangle=tickangle)
    if x_date_format:
        fig.update_xaxes(tickformat=x_date_format)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR)

    return fig.to_json()


def create_stacked_bar_chart(df, x_col, y_cols, colors, labels, unit='MWh', divisor=1, decimals=0, x_date_format=None):
    """
    Creates a stacked bar chart with Plotly

    Args:
        df: DataFrame with data (values in MWh)
        x_col: Column name for x-axis
        y_cols: List of column names to stack
        colors: Dict mapping column names to colors
        labels: Dict mapping column names to display labels
        unit: Unit label displayed on the y-axis and in the hover (e.g. 'TWh')
        divisor: Factor to divide raw MWh values by to reach `unit`
        decimals: Number of decimals shown in the hover
        x_date_format: Optional d3 date format applied to the axis ticks and the
            unified hover header (e.g. '%B %Y'). Requires x_col to be a date.

    Returns:
        HTML string of the chart
    """
    fig = go.Figure()

    # Add a trace for each filiere
    for col in y_cols:
        if col in df.columns:
            fig.add_trace(go.Bar(
                x=df[x_col],
                y=df[col] / divisor,
                name=labels.get(col, col),
                marker_color=colors.get(col, Colors.PRIMARY),
                hovertemplate=f'{labels.get(col, col)}: %{{y:,.{decimals}f}} {unit}<extra></extra>',
            ))

    fig.update_layout(
        barmode='stack',
        separators=', ',
        xaxis_title_text='',
        yaxis_title_text=unit,
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
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='#1E293B',
            bordercolor='#475569',
            font=dict(color='#F1F5F9', size=11),
        ),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    if x_date_format:
        fig.update_xaxes(tickformat=x_date_format, hoverformat=x_date_format)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR)

    return fig.to_json()


def create_import_export_chart(df, x_col, import_col, export_col, unit='TWh', divisor=1_000_000, decimals=2, x_date_format='%B %Y'):
    """
    Creates a diverging bar chart: exports above the zero line, imports below.

    Args:
        df: DataFrame with positive volumes (MWh) in both columns
        x_col: Column name for x-axis (a date)
        import_col: Column holding the imported volume (plotted downward)
        export_col: Column holding the exported volume (plotted upward)
        unit: Unit label displayed on the y-axis and in the hover (e.g. 'TWh')
        divisor: Factor to divide raw MWh values by to reach `unit`
        decimals: Number of decimals shown in the hover
        x_date_format: d3 date format for the axis ticks and unified hover header

    Returns:
        JSON string of the chart
    """
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df[x_col],
        y=df[export_col] / divisor,
        name='Export',
        marker_color=Colors.PRIMARY,
        hovertemplate=f'Export : %{{y:,.{decimals}f}} {unit}<extra></extra>',
    ))
    # Imports plotted as negative so they diverge below zero; hover shows the
    # positive magnitude via customdata.
    fig.add_trace(go.Bar(
        x=df[x_col],
        y=-df[import_col] / divisor,
        customdata=df[import_col] / divisor,
        name='Import',
        marker_color=Colors.SECONDARY,
        hovertemplate=f'Import : %{{customdata:,.{decimals}f}} {unit}<extra></extra>',
    ))
    # Net balance line (export − import): positive = net exporter.
    fig.add_trace(go.Scatter(
        x=df[x_col],
        y=(df[export_col] - df[import_col]) / divisor,
        name='Solde',
        mode='lines+markers',
        line=dict(color='#F1F5F9', width=2),
        marker=dict(size=6),
        hovertemplate=f'Solde : %{{y:,.{decimals}f}} {unit}<extra></extra>',
    ))

    fig.update_layout(
        barmode='relative',
        separators=', ',
        xaxis_title_text='',
        yaxis_title_text=unit,
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
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='#1E293B',
            bordercolor='#475569',
            font=dict(color='#F1F5F9', size=11),
        ),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    if x_date_format:
        fig.update_xaxes(tickformat=x_date_format, hoverformat=x_date_format)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR, zeroline=True, zerolinecolor=ChartConfig.AXIS_COLOR)

    return fig.to_json()


def create_parc_prod_sankey(parc_mw, prod_mwh):
    """Diagramme parc installé (MW) ↔ production annuelle (MWh), par filière.

    Implémenté avec des formes Plotly (rectangles + trapèzes) pour garantir
    des barres continues sans gaps, avec des liens qui peuvent se croiser.
    """
    filieres = [f for f in FILIERES if parc_mw.get(f, 0) > 0 and prod_mwh.get(f, 0) > 0]
    if not filieres:
        return go.Figure().to_json()

    total_parc = sum(parc_mw[f] for f in filieres)
    total_prod = sum(prod_mwh[f] for f in filieres)

    parc_frac = {f: parc_mw[f] / total_parc for f in filieres}
    prod_frac = {f: prod_mwh[f] / total_prod for f in filieres}

    # Empiler de haut (y=1) vers bas (y=0) dans l'ordre de FILIERES
    def build_segments(fracs):
        segs = {}
        cum = 1.0
        for f in filieres:
            h = fracs[f]
            segs[f] = (cum - h, cum)  # (y_bas, y_haut)
            cum -= h
        return segs

    left_segs = build_segments(parc_frac)
    right_segs = build_segments(prod_frac)

    BAR_W = 0.14
    LX0, LX1 = 0.0, BAR_W
    RX0, RX1 = 1.0 - BAR_W, 1.0
    GAP = 0.004  # léger espace entre barre et lien

    shapes = []
    annotations = []

    for f in filieres:
        fc = FILIERE_COLORS[f]
        r, g, b = int(fc[1:3], 16), int(fc[3:5], 16), int(fc[5:7], 16)

        lb, lt = left_segs[f]
        rb, rt = right_segs[f]

        # Trapèze reliant le segment gauche au segment droit
        # Mélange vers blanc pour obtenir une teinte claire/pastel
        alpha = 0.60
        mr = int(r * alpha + 255 * (1 - alpha))
        mg = int(g * alpha + 255 * (1 - alpha))
        mb = int(b * alpha + 255 * (1 - alpha))
        shapes.append(dict(
            type='path',
            path=(
                f'M {LX1 + GAP:.4f} {lb:.6f} '
                f'L {LX1 + GAP:.4f} {lt:.6f} '
                f'L {RX0 - GAP:.4f} {rt:.6f} '
                f'L {RX0 - GAP:.4f} {rb:.6f} Z'
            ),
            fillcolor=f'rgb({mr},{mg},{mb})',
            line=dict(color='rgba(0,0,0,0)', width=0),
            layer='below',
            xref='x', yref='y',
        ))

        # Barre gauche (parc)
        shapes.append(dict(
            type='rect',
            x0=LX0, y0=lb, x1=LX1, y1=lt,
            fillcolor=fc,
            line=dict(color='rgba(255,255,255,0.15)', width=0.5),
            xref='x', yref='y',
        ))

        # Barre droite (prod)
        shapes.append(dict(
            type='rect',
            x0=RX0, y0=rb, x1=RX1, y1=rt,
            fillcolor=fc,
            line=dict(color='rgba(255,255,255,0.15)', width=0.5),
            xref='x', yref='y',
        ))

        # Labels gauche (parc) — uniquement si le segment est assez haut
        if (lt - lb) >= 0.045:
            annotations.append(dict(
                x=-0.01, y=(lb + lt) / 2,
                xref='paper', yref='y',
                text=f'{FILIERES[f]} {parc_mw[f]/1000:.0f} GW ({parc_frac[f]*100:.0f}%)',
                xanchor='right', yanchor='middle',
                showarrow=False,
                font=dict(color=ChartConfig.TEXT_COLOR, size=11),
            ))

        # Labels droite (prod) — uniquement si le segment est assez haut
        if (rt - rb) >= 0.045:
            annotations.append(dict(
                x=1.01, y=(rb + rt) / 2,
                xref='paper', yref='y',
                text=f'{FILIERES[f]} {prod_mwh[f]/1e6:.0f} TWh ({prod_frac[f]*100:.0f}%)',
                xanchor='left', yanchor='middle',
                showarrow=False,
                font=dict(color=ChartConfig.TEXT_COLOR, size=11),
            ))

    # Titres des colonnes
    annotations += [
        dict(
            x=(LX0 + LX1) / 2, y=1.04,
            xref='x', yref='y',
            text='<b>Parc installé</b>',
            xanchor='center', yanchor='bottom',
            showarrow=False,
            font=dict(color=ChartConfig.TEXT_COLOR, size=12),
        ),
        dict(
            x=(RX0 + RX1) / 2, y=1.04,
            xref='x', yref='y',
            text='<b>Production</b>',
            xanchor='center', yanchor='bottom',
            showarrow=False,
            font=dict(color=ChartConfig.TEXT_COLOR, size=12),
        ),
    ]

    fig = go.Figure()
    fig.update_layout(
        shapes=shapes,
        annotations=annotations,
        xaxis=dict(range=[0, 1], visible=False, fixedrange=True),
        yaxis=dict(range=[0, 1.08], visible=False, fixedrange=True),
        height=330,
        margin=dict(l=180, r=180, t=30, b=20),
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR, size=11),
        hovermode=False,
    )
    return fig.to_json()


def create_mini_line_chart(df, x_col, y_col):
    """
    Creates a compact Plotly line chart for the homepage dashboard.

    Returns:
        JSON string of the Plotly figure
    """
    fig = px.line(df, x=x_col, y=y_col, color_discrete_sequence=[Colors.ACCENT])
    fig.update_layout(separators=", ")
    fig.update_traces(
        hovertemplate="Date: %{x|%H:%M}<br>Consommation: %{y:,.0f} MW<extra></extra>"
    )
    fig.update_layout(
        showlegend=False,
        xaxis_title_text='',
        yaxis_title_text='MW',
        margin=dict(l=50, r=10, t=10, b=40),
        height=300,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR, zerolinecolor=ChartConfig.GRID_COLOR)

    return fig.to_json()


def create_parc_installe_chart(df):
    """
    Stacked monthly bar chart of installed capacity (GW) by filière.
    df must have columns: date, filiere, parc_mw
    """
    filiere_colors = {
        'Eolien terrestre': ProductionColors.EOLIEN,
        'Eolien en mer': '#06D6A0',
        'Solaire': ProductionColors.SOLAIRE,
    }
    stack_order = ['Eolien terrestre', 'Eolien en mer', 'Solaire']

    fig = go.Figure()
    for filiere in stack_order:
        sub = df[df['filiere'] == filiere].sort_values('date')
        if sub.empty:
            continue
        fig.add_trace(go.Bar(
            x=sub['date'],
            y=(sub['parc_mw'] / 1000).round(2),
            name=filiere,
            marker=dict(
                color=filiere_colors.get(filiere, Colors.PRIMARY),
                line=dict(width=0),
            ),
            hovertemplate=f'{filiere}: %{{y:,.1f}} GW<extra></extra>',
        ))

    fig.update_layout(
        barmode='stack',
        bargap=0.05,
        separators=', ',
        xaxis_title_text='',
        yaxis_title_text='GW',
        margin=ChartConfig.MARGIN_WITH_LEGEND,
        height=ChartConfig.LINE_CHART_HEIGHT,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
        legend=dict(orientation='h', x=0.5, y=-0.2, xanchor='center'),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='#1E293B',
            bordercolor='#475569',
            font=dict(color='#F1F5F9', size=11),
        ),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR)
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR, zerolinecolor=ChartConfig.GRID_COLOR)

    return fig.to_json()


def create_stacked_area_chart(df, x_col, y_cols, colors, labels):
    """
    Creates a stacked area chart for intraday production by filière.

    Args:
        df     : DataFrame with x_col and y_cols columns
        x_col  : name of the timestamp column
        y_cols : list of filière column names (in stack order)
        colors : dict {col: hex_color}
        labels : dict {col: French label}

    Returns:
        JSON string of the Plotly figure
    """
    fig = go.Figure()
    for col in y_cols:
        if col not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=df[col].fillna(0),
            name=labels.get(col, col),
            stackgroup='one',
            mode='lines',
            line=dict(width=0.5, color=colors.get(col, '#888')),
            fillcolor=colors.get(col, '#888'),
            hovertemplate=f'{labels.get(col, col)}: %{{y:,.0f}} MW<extra></extra>',
        ))

    fig.update_layout(
        showlegend=False,
        xaxis_title_text='',
        yaxis_title_text='MW',
        margin=dict(l=50, r=10, t=10, b=10),
        height=350,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='#1E293B',
            bordercolor='#475569',
            font=dict(color='#F1F5F9', size=11),
        ),
    )
    fig.update_xaxes(gridcolor=ChartConfig.GRID_COLOR, tickformat='%H:%M')
    fig.update_yaxes(gridcolor=ChartConfig.GRID_COLOR, zerolinecolor=ChartConfig.GRID_COLOR)

    return fig.to_json()


def accueil(request):
    """
    Home page - welcome page with latest day dashboard data.
    Falls back gracefully if S3 data is unavailable.
    """
    context = {}
    try:
        data = get_dashboard_data()
        if data:
            filieres_list = list(FILIERES.keys())
            graph_conso_jour = create_mini_line_chart(
                data['conso_ts'], x_col='date_heure', y_col='consommation'
            )
            graph_production_jour = create_stacked_area_chart(
                data['production_ts'],
                x_col='date_heure',
                y_cols=filieres_list,
                colors=FILIERE_COLORS,
                labels=FILIERES,
            )
            graph_sankey = create_parc_prod_sankey(data['parc_pmax'], data['production_mix_year'])

            DECARBONEES = ('nucleaire', 'hydraulique', 'bioenergies', 'solaire', 'eolien')
            mix = data['production_mix_year']
            total_mwh = sum(mix.values())
            decarbonees_mwh = sum(mix.get(f, 0.0) for f in DECARBONEES)
            pct_decarbonee = (decarbonees_mwh / total_mwh * 100) if total_mwh > 0 else 0.0

            parc_enr_ctx = {}
            try:
                df_parc = get_parc_installe_data().copy()
                df_parc['groupe'] = df_parc['filiere'].map({
                    'Eolien terrestre': 'eolien',
                    'Eolien en mer': 'eolien',
                    'Solaire': 'solaire',
                })
                parc_by_month = (df_parc.groupby(['date', 'groupe'])['parc_mw']
                                          .sum()
                                          .unstack('groupe')
                                          .sort_index())
                if len(parc_by_month) >= 13:
                    latest = parc_by_month.index[-1]
                    y, m = latest.split('-')
                    prev = f"{int(y) - 1}-{m}"
                    if prev in parc_by_month.index and 'eolien' in parc_by_month.columns and 'solaire' in parc_by_month.columns:
                        def _fmt_pct(now, before):
                            d = (now - before) / before * 100
                            return f"{'+' if d >= 0 else ''}{d:.1f}".replace('.', ','), d >= 0
                        now_row = parc_by_month.loc[latest]
                        prev_row = parc_by_month.loc[prev]
                        eol_pct, eol_pos = _fmt_pct(now_row['eolien'], prev_row['eolien'])
                        sol_pct, sol_pos = _fmt_pct(now_row['solaire'], prev_row['solaire'])
                        parc_enr_ctx = {
                            'parc_eolien_delta': eol_pct,
                            'parc_eolien_positive': eol_pos,
                            'parc_eolien_gw': f"{now_row['eolien'] / 1000:.1f}".replace('.', ','),
                            'parc_solaire_delta': sol_pct,
                            'parc_solaire_positive': sol_pos,
                            'parc_solaire_gw': f"{now_row['solaire'] / 1000:.1f}".replace('.', ','),
                        }
            except Exception:
                pass

            context = {
                'has_dashboard_data': True,
                'dashboard_date': data['dashboard_date'],
                'current_year': data['peak_year_datetime'].year,
                'peak_year_value': f"{data['peak_year_value']:,}".replace(',', '\u202f'),
                'peak_year_date': data['peak_year_datetime'].strftime('%d/%m/%Y'),
                'peak_year_time': data['peak_year_datetime'].strftime('%H:%M'),
                'peak_all_value': f"{data['peak_all_value']:,}".replace(',', '\u202f'),
                'peak_all_date': data['peak_all_datetime'].strftime('%d/%m/%Y'),
                'peak_all_time': data['peak_all_datetime'].strftime('%H:%M'),
                'pct_decarbonee': f"{pct_decarbonee:.1f}".replace('.', ','),
                'decarbonees_twh': f"{decarbonees_mwh / 1_000_000:.1f}".replace('.', ','),
                **parc_enr_ctx,
                'graph_conso_jour': graph_conso_jour,
                'graph_production_jour': graph_production_jour,
                'graph_sankey': graph_sankey,
            }
    except Exception:
        pass

    return render(request, 'consommation/accueil.html', context)


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
        color=Colors.ACCENT,
        y_label='Consommation'
    )

    # ========== CHART 2: Annual consumption ==========
    graph_annuel = create_bar_chart(
        df_annuel,
        x_col='year',
        y_col='yearly_consumption',
        color=Colors.ACCENT  # Amber
    )

    # ========== CHART 3: Monthly consumption ==========
    graph_mensuel = create_bar_chart(
        df_mensuel,
        x_col='year_month',
        y_col='monthly_consumption',
        color=Colors.SECONDARY,
        tickangle=45,
        x_date_format='%B %Y'
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'charts': {
            'chart-puissance': json.loads(graph_puissance),
            'chart-annuel': json.loads(graph_annuel),
            'chart-mensuel': json.loads(graph_mensuel),
        }})

    context = {
        'titre': 'Consommation',
        'min_date': min_date,
        'max_date': max_date,
        'start_date': start_date,
        'end_date': end_date,
        'graph_puissance': graph_puissance,
        'graph_annuel': graph_annuel,
        'graph_mensuel': graph_mensuel,
    }

    return render(request, 'consommation/index.html', context)


@handle_validation_errors
def production(request):
    """
    Production page - displays production data with load curve by sector and stacked bar charts
    """
    # Get available min/max dates
    min_date, max_date = get_production_date_range()

    # Validate filieres (multi-selection)
    filieres = get_production_filieres()
    filieres_selected = request.GET.getlist('filiere') or ['nucleaire']
    for filiere in filieres_selected:
        if filiere not in filieres:
            return HttpResponseBadRequest(f"Filière invalide. Choisissez parmi: {', '.join(filieres.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load production data for the line chart
    df_production = get_production_data_multi(start_date, end_date, filieres_selected)

    # Create production curve chart (one line per selected filière)
    graph_production = create_multi_line_chart(
        df_production,
        x_col='date_heure',
        filieres=filieres_selected,
        colors=FILIERE_COLORS,
        labels=filieres
    )

    # Load annual and monthly aggregated data
    df_annual = get_production_annual_data()
    df_monthly = get_production_monthly_data()

    # Load installed capacity data
    df_parc = get_parc_installe_data()
    graph_parc_installe = create_parc_installe_chart(df_parc)

    # Get colors and labels from centralized constants (cached)
    colors, labels = get_production_colors_and_labels()

    # Create stacked bar charts
    graph_production_annuel = create_stacked_bar_chart(
        df_annual,
        x_col='year',
        y_cols=get_filiere_columns('annual'),
        colors=colors,
        labels=labels,
        unit='TWh',
        divisor=1_000_000,
        decimals=1,
    )

    # Real date (first of month) so the axis/hover can show French month names
    df_monthly['annee_mois'] = pd.to_datetime(
        df_monthly['year'].astype(str) + '-' + df_monthly['month'].astype(str).str.zfill(2) + '-01'
    )

    graph_production_mensuel = create_stacked_bar_chart(
        df_monthly,
        x_col='annee_mois',
        y_cols=get_filiere_columns('monthly'),
        colors=colors,
        labels=labels,
        unit='TWh',
        divisor=1_000_000,
        decimals=1,
        x_date_format='%B %Y',
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'charts': {
            'chart-production': json.loads(graph_production),
            'chart-production-annuel': json.loads(graph_production_annuel),
            'chart-production-mensuel': json.loads(graph_production_mensuel),
            'chart-parc-installe': json.loads(graph_parc_installe),
        }})

    context = {
        'titre': 'Production',
        'min_date': min_date,
        'max_date': max_date,
        'start_date': start_date,
        'end_date': end_date,
        'filieres_selected': filieres_selected,
        'filieres': filieres,
        'graph_production': graph_production,
        'graph_production_annuel': graph_production_annuel,
        'graph_production_mensuel': graph_production_mensuel,
        'graph_parc_installe': graph_parc_installe,
    }

    return render(request, 'consommation/production.html', context)


@handle_validation_errors
def echanges(request):
    """
    Échanges page - displays commercial exchange data with load curve by country
    """
    # Get available min/max dates
    min_date, max_date = get_echanges_date_range()

    # Commercial flows only on this page
    pays_disponibles = get_echanges_pays_commerciaux()

    # Countries for the load curve (top filter) — multi-selection
    pays_selected = request.GET.getlist('pays') or ['ech_comm_allemagne_belgique']
    for pays in pays_selected:
        if pays not in pays_disponibles:
            return HttpResponseBadRequest(f"Pays invalide. Choisissez parmi: {', '.join(pays_disponibles.keys())}")

    # Country for the annual chart (bottom) — its own selector, fully
    # independent of the top filters (dates and curve country). Adds a 'total'
    # option (sum of all commercial borders).
    pays_annuel_options = {'total': 'Total', **pays_disponibles}
    pays_annuel = request.GET.get('pays_annuel', 'total')
    if pays_annuel not in pays_annuel_options:
        return HttpResponseBadRequest(f"Pays invalide. Choisissez parmi: {', '.join(pays_annuel_options.keys())}")

    # Validate and get dates from request (drives the load curve only)
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load echanges data for the line chart (one column per selected country)
    df_echanges = get_echanges_data_multi(start_date, end_date, pays_selected)

    # Create echanges curve chart (one line per selected country)
    graph_echanges = create_multi_line_chart(
        df_echanges,
        x_col='date_heure',
        filieres=pays_selected,
        colors=PAYS_ECHANGES_COLORS,
        labels=pays_disponibles,
    )

    # Annual import/export volumes — always over the full available history and
    # for its own selected country, independent of the top filters.
    df_echanges_annuel = get_echanges_annual_import_export(min_date, max_date, pays_annuel)
    graph_echanges_annuel = create_import_export_chart(
        df_echanges_annuel,
        x_col='annee',
        import_col='import_mwh',
        export_col='export_mwh',
        x_date_format=None,
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Each form refreshes only its own chart, so the two stay independent:
        # the bottom selector sends `pays_annuel`, the top form does not.
        if 'pays_annuel' in request.GET:
            return JsonResponse({'charts': {
                'chart-echanges-annuel': json.loads(graph_echanges_annuel),
            }})
        return JsonResponse({'charts': {
            'chart-echanges': json.loads(graph_echanges),
        }})

    context = {
        'titre': 'Échanges commerciaux',
        'min_date': min_date,
        'max_date': max_date,
        'start_date': start_date,
        'end_date': end_date,
        'pays': pays_selected,
        'pays_options': pays_disponibles,
        'selected_pays': pays_selected,
        'pays_annuel_options': pays_annuel_options,
        'selected_pays_annuel': pays_annuel,
        'graph_echanges': graph_echanges,
        'graph_echanges_annuel': graph_echanges_annuel,
        'row_count': len(df_echanges),
    }

    return render(request, 'consommation/echanges.html', context)


# ========== Export Functions ==========
def _format_value(value):
    """
    Formate une valeur pour l'export CSV.

    Supprime le '.0' superflu des floats entiers (ex: 2012.0 → 2012,
    486560097.0 → 486560097) tout en conservant les décimales réelles (12.5).
    """
    if isinstance(value, float):
        if value != value:  # NaN n'est jamais égal à lui-même
            return ''
        if value.is_integer():
            return int(value)
    return value


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
    # En-têtes français unifiés, données lues via les clés techniques
    writer.writerow([get_csv_header(col) for col in columns])

    # Performance: use values.tolist() instead of iterrows()
    rows = df[columns].values.tolist()
    writer.writerows([_format_value(v) for v in row] for row in rows)

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
    return _export_to_csv(df, filename, ['date_heure', 'consommation'])


def export_annuel_csv(request):
    """
    Export annual consumption data to CSV
    """
    df = get_annual_data()
    # Arrondir : les décimales viennent de l'agrégation des sources, sans sens en MWh annuels
    df = df.copy()
    df['yearly_consumption'] = df['yearly_consumption'].round()
    # Années récentes en premier
    df = df.sort_values('year', ascending=False)
    return _export_to_csv(df, 'consommation_annuelle.csv', ['year', 'yearly_consumption'])


def export_mensuel_csv(request):
    """
    Export monthly consumption data to CSV
    """
    df = get_monthly_data()
    # Découper 'year_month' (ex: '2012-01') en colonnes annee/mois, comme la production
    df = df.copy()
    df[['year', 'month']] = df['year_month'].str.split('-', expand=True).astype(int)
    # Mois récents en premier
    df = df.sort_values('year_month', ascending=False)
    # Arrondir : les décimales viennent de l'agrégation des sources, sans sens en MWh
    df['monthly_consumption'] = df['monthly_consumption'].round()
    return _export_to_csv(df, 'consommation_mensuelle.csv', ['year', 'month', 'monthly_consumption'])


@handle_validation_errors
def export_production_csv(request):
    """
    Export production data to CSV
    """
    # Get available min/max dates
    min_date, max_date = get_production_date_range()

    # Validate filieres (multi-selection)
    filieres = get_production_filieres()
    filieres_selected = request.GET.getlist('filiere') or ['nucleaire']
    for filiere in filieres_selected:
        if filiere not in filieres:
            return HttpResponseBadRequest(f"Filière invalide. Choisissez parmi: {', '.join(filieres.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load data (wide format: one column per selected filière)
    df = get_production_data_multi(start_date, end_date, filieres_selected)

    # Export to CSV (date_heure + one column per filière)
    filieres_slug = '-'.join(filieres_selected)
    filename = f'production_{filieres_slug}_{start_date}_{end_date}.csv'
    return _export_to_csv(df, filename, ['date_heure'] + filieres_selected)


def export_production_annuel_csv(request):
    """
    Export annual production data by sector to CSV
    """
    df = get_production_annual_data()
    filiere_cols = get_filiere_columns('annual')
    # Arrondir : les décimales viennent de l'agrégation des sources, sans sens en MWh
    df = df.copy()
    df[filiere_cols] = df[filiere_cols].round()
    # Années récentes en premier
    df = df.sort_values('year', ascending=False)
    columns = ['year'] + filiere_cols
    return _export_to_csv(df, 'production_annuelle.csv', columns)


def export_production_mensuel_csv(request):
    """
    Export monthly production data by sector to CSV
    """
    df = get_production_monthly_data()
    filiere_cols = get_filiere_columns('monthly')
    # Arrondir : les décimales viennent de l'agrégation des sources, sans sens en MWh
    df = df.copy()
    df[filiere_cols] = df[filiere_cols].round()
    # Mois récents en premier
    df = df.sort_values(['year', 'month'], ascending=False)
    columns = ['year', 'month'] + filiere_cols
    return _export_to_csv(df, 'production_mensuelle.csv', columns)


def export_parc_installe_csv(request):
    """
    Export installed wind/solar capacity data to CSV
    """
    df = get_parc_installe_data()
    # Long → wide : une colonne par filière (valeurs en MW)
    wide = (df.pivot(index='date', columns='filiere', values='parc_mw')
              .reset_index()
              .rename(columns={
                  'Eolien terrestre': 'eolien_terrestre',
                  'Eolien en mer': 'eolien_en_mer',
                  'Solaire': 'solaire',
              }))
    # Découper 'date' (ex: '2012-01') en colonnes annee/mois, comme les autres exports
    wide[['year', 'month']] = wide['date'].str.split('-', expand=True).astype(int)
    # Mois récents en premier
    wide = wide.sort_values('date', ascending=False)
    # Arrondir : la capacité déduite n'a pas de sens au-delà du MW entier
    filiere_cols = [c for c in ('eolien_terrestre', 'eolien_en_mer', 'solaire') if c in wide.columns]
    wide[filiere_cols] = wide[filiere_cols].round()
    columns = ['year', 'month'] + filiere_cols
    return _export_to_csv(wide, 'parc_installe_eolien_solaire.csv', columns)


@handle_validation_errors
def export_echanges_csv(request):
    """
    Export echanges data to CSV
    """
    # Get available min/max dates
    min_date, max_date = get_echanges_date_range()

    # Validate pays (commercial flows only on this page) — multi-selection
    pays_disponibles = get_echanges_pays_commerciaux()
    pays_selected = request.GET.getlist('pays') or ['ech_comm_allemagne_belgique']
    for pays in pays_selected:
        if pays not in pays_disponibles:
            return HttpResponseBadRequest(f"Pays invalide. Choisissez parmi: {', '.join(pays_disponibles.keys())}")

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(request, min_date, max_date)

    # Load data (wide: one column per selected country)
    df = get_echanges_data_multi(start_date, end_date, pays_selected)

    # Export to CSV
    pays_slug = '_'.join(pays_selected)
    filename = f'echanges_{pays_slug}_{start_date}_{end_date}.csv'
    return _export_to_csv(df, filename, ['date_heure', *pays_selected])


@handle_validation_errors
def export_echanges_annuel_csv(request):
    """
    Export the full annual detail to CSV: import/export/solde for every
    commercial border and the overall total, all years. Independent of the
    page filters.
    """
    min_date, max_date = get_echanges_date_range()

    df = get_echanges_annual_detail(min_date, max_date).copy()

    # Derive the solde for each border (and total), and build the column order:
    # annee, then import/export/solde grouped per border, total last.
    bases = [c[:-len('_import_mwh')] for c in df.columns if c.endswith('_import_mwh')]
    columns = ['annee']
    for base in bases:
        df[f'{base}_solde_mwh'] = df[f'{base}_export_mwh'] - df[f'{base}_import_mwh']
        columns += [f'{base}_import_mwh', f'{base}_export_mwh', f'{base}_solde_mwh']

    # Round: decimals come from the source aggregation, meaningless in MWh.
    value_cols = [c for c in columns if c != 'annee']
    df[value_cols] = df[value_cols].round()

    return _export_to_csv(df, 'echanges_annuels_detail.csv', columns)


# ========== API ==========
def api(request):
    # Page portail : doc réservée aux utilisateurs connectés (le template
    # affiche sinon une invitation à se connecter/s'inscrire). Les endpoints
    # JSON sous /api/v1/ sont, eux, publics en phase 1.
    api_base = request.build_absolute_uri('/api/v1/').rstrip('/')
    return render(request, 'consommation/api.html', {'api_base': api_base})