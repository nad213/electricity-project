from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from datetime import date, datetime, timedelta
import json
import math
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
    get_echanges_net_by_border,
    get_dashboard_data, get_parc_installe_data,
)
from .constants import (
    Colors, ChartConfig, ProductionColors, FILIERE_COLORS, FILIERES,
    PAYS_ECHANGES, PAYS_ECHANGES_COLORS,
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


def _dates_from_session(request, session_key, min_date, max_date):
    """
    Returns the (start_date, end_date) remembered for this page, clamped to
    the currently available range, or None if nothing usable is stored
    (never raises: a stale or corrupted session must not break the page).
    """
    stored = request.session.get(session_key)
    try:
        start_date = date.fromisoformat(stored['start'])
        end_date = date.fromisoformat(stored['end'])
    except (TypeError, KeyError, ValueError):
        return None

    # max_date moves forward every day: clamp silently rather than erroring
    start_date = max(start_date, min_date)
    end_date = min(end_date, max_date)
    if start_date > end_date:
        # Stored range entirely outside the available history
        return None
    return start_date, end_date


def validate_and_get_dates(request, min_date, max_date, session_key=None):
    """
    Validates and returns start_date and end_date from request
    Returns tuple (start_date, end_date) or raises HttpResponseBadRequest

    If session_key is given, the page remembers its last explicitly
    submitted period: GET parameters are stored in the session, and a
    request without them reuses the stored period instead of the default.
    """
    # Default dates (last 15 days)
    default_start = max_date - timedelta(days=15)

    explicit = 'start_date' in request.GET or 'end_date' in request.GET
    if not explicit and session_key:
        stored = _dates_from_session(request, session_key, min_date, max_date)
        if stored:
            return stored

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

    if explicit and session_key:
        request.session[session_key] = {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
        }

    return start_date, end_date


def resolve_multi_filter(request, param, session_key, options, default, label):
    """
    Resolves a multi-select filter with per-page memory: an explicit form
    submission wins and is remembered in the session, otherwise the
    remembered selection is reused, silently filtered against the currently
    valid options (a stale session must not break the page).

    The filter form always submits the dates, so their presence tells an
    explicit submission apart from a bare navigation — including the
    "everything unchecked" case, where the param itself is absent.
    Raises ValueError on invalid explicit input (→ 400 via decorator).
    """
    explicit = (param in request.GET or 'start_date' in request.GET
                or 'end_date' in request.GET)
    if explicit:
        selected = request.GET.getlist(param) or list(default)
        for value in selected:
            if value not in options:
                raise ValueError(f"{label} invalide. Choisissez parmi: {', '.join(options.keys())}")
        request.session[session_key] = selected
        return selected

    stored = request.session.get(session_key)
    if not isinstance(stored, list):
        stored = []
    return [value for value in stored if value in options] or list(default)


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


# Position angulaire (degrés) de chaque frontière autour de la France, choisie
# pour évoquer la géographie réelle (Angleterre au NO, Espagne au SO, etc.).
ECHANGES_FLOW_ANGLES = {
    'ech_comm_angleterre': 128,
    'ech_comm_allemagne_belgique': 52,
    'ech_comm_suisse': -8,
    'ech_comm_italie': -68,
    'ech_comm_espagne': -145,
}


def create_echanges_flow_map(net_by_border, year=None):
    """Carte de flux radiale : la France au centre, les frontières commerciales
    en polygone autour, et une flèche par frontière indiquant le sens net du
    solde (export = depuis la France, import = vers la France) avec une
    épaisseur proportionnelle au volume échangé sur la période.

    Args:
        net_by_border: dict {col: {'import_mwh', 'export_mwh', 'net_mwh'}}
            tel que renvoyé par services.get_echanges_net_by_border.
        year: année affichée dans la légende (facultatif).

    Convention reprise du graphe import/export : Export = cyan, Import = amber.
    """
    borders = [c for c in ECHANGES_FLOW_ANGLES if c in net_by_border]
    if not borders:
        return go.Figure().to_json()

    EXPORT_COLOR = Colors.PRIMARY    # cyan — la France fournit
    IMPORT_COLOR = Colors.SECONDARY  # amber — la France reçoit

    max_mag = max(abs(net_by_border[c]['net_mwh']) for c in borders) or 1.0

    # Disposition : nœuds pays sur une ellipse (étirée horizontalement pour
    # remplir une carte large). La France est à l'origine.
    RX, RY = 1.55, 1.0

    fig = go.Figure()
    annotations = []

    node_x, node_y, node_text, node_pos, node_hover = [], [], [], [], []
    for col in borders:
        d = net_by_border[col]
        net = d['net_mwh']
        twh = abs(net) / 1_000_000
        is_import = net > 0
        color = IMPORT_COLOR if is_import else EXPORT_COLOR

        theta = math.radians(ECHANGES_FLOW_ANGLES[col])
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        cx, cy = RX * cos_t, RY * sin_t

        # Flèche fine reliant la France au pays, le long du segment centre→nœud.
        # f_in juste hors du nœud France, f_out juste avant le nœud du pays.
        f_in, f_out = 0.16, 0.86
        tail = (f_in * cx, f_in * cy)
        head = (f_out * cx, f_out * cy)
        if is_import:        # pays → France : on inverse tête et queue
            head, tail = tail, head

        width = 2.0 + 3.5 * (abs(net) / max_mag)
        annotations.append(dict(
            x=head[0], y=head[1], ax=tail[0], ay=tail[1],
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1.0,
            arrowwidth=width, arrowcolor=color,
        ))

        node_x.append(cx)
        node_y.append(cy)
        name = PAYS_ECHANGES.get(col, col)
        node_text.append(
            f"<b>{name}</b><br>"
            f"<span style='color:{color}'>{twh:.1f} TWh</span>".replace('.', ',')
        )
        # Texte placé du côté extérieur du nœud pour ne pas chevaucher.
        if abs(cos_t) > 0.5:
            node_pos.append('middle right' if cos_t > 0 else 'middle left')
        else:
            node_pos.append('top center' if sin_t >= 0 else 'bottom center')
        sens = 'importés depuis' if is_import else 'exportés vers'
        node_hover.append(
            f"<b>{name}</b><br>"
            f"Solde : {twh:,.1f} TWh {sens} la France<br>"
            f"Import : {d['import_mwh']/1_000_000:,.1f} TWh"
            f" · Export : {d['export_mwh']/1_000_000:,.1f} TWh"
            .replace(',', ' ').replace('.', ',')
        )

    # --- Nœuds pays (marqueur + libellé) ---
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        marker=dict(size=12, color='#475569', line=dict(color='#94A3B8', width=1)),
        text=node_text,
        textposition=node_pos,
        textfont=dict(color='#CBD5E1', size=12),
        customdata=node_hover,
        hovertemplate='%{customdata}<extra></extra>',
        showlegend=False,
    ))

    # --- Nœud central France (par-dessus les flèches) ---
    fig.add_trace(go.Scatter(
        x=[0], y=[0],
        mode='markers+text',
        marker=dict(size=58, color='#1E293B', line=dict(color='#64748B', width=2)),
        text=['<b>France</b>'],
        textposition='middle center',
        textfont=dict(color='#F8FAFC', size=14),
        hoverinfo='skip',
        showlegend=False,
    ))

    # --- Légende de la convention (deux traces fantômes) ---
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode='lines', line=dict(color=EXPORT_COLOR, width=4),
        name='Export (France → pays)',
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode='lines', line=dict(color=IMPORT_COLOR, width=4),
        name='Import (pays → France)',
    ))

    fig.update_layout(
        annotations=annotations,
        xaxis=dict(range=[-2.55, 2.55], visible=False, fixedrange=True),
        yaxis=dict(range=[-1.6, 1.6], visible=False, fixedrange=True),
        height=420,
        margin=dict(l=20, r=20, t=20, b=50),
        paper_bgcolor=ChartConfig.PAPER_COLOR,
        plot_bgcolor=ChartConfig.BACKGROUND_COLOR,
        font=dict(color=ChartConfig.TEXT_COLOR, size=11),
        legend=dict(orientation='h', x=0.5, y=-0.04, xanchor='center'),
        hoverlabel=dict(bgcolor='#1E293B', bordercolor='#475569',
                        font=dict(color='#F1F5F9', size=11)),
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
            # Carte de flux des échanges commerciaux de l'année courante
            # (France au centre, voisins autour). Isolée pour qu'une panne des
            # données d'échanges ne casse pas le reste du tableau de bord.
            graph_echanges_flux = None
            try:
                from datetime import date as _date
                _year = data['peak_year_datetime'].year
                net_by_border = get_echanges_net_by_border(
                    _date(_year, 1, 1), data['dashboard_date']
                )
                if net_by_border:
                    graph_echanges_flux = create_echanges_flow_map(net_by_border, year=_year)
            except Exception:
                graph_echanges_flux = None

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
                            return f"{'+' if d >= 0 else ''}{d:.1f}".replace('.', ',')
                        now_row = parc_by_month.loc[latest]
                        prev_row = parc_by_month.loc[prev]
                        parc_enr_ctx = {
                            'parc_eolien_delta': _fmt_pct(now_row['eolien'], prev_row['eolien']),
                            'parc_eolien_gw': f"{now_row['eolien'] / 1000:.1f}".replace('.', ','),
                            'parc_solaire_delta': _fmt_pct(now_row['solaire'], prev_row['solaire']),
                            'parc_solaire_gw': f"{now_row['solaire'] / 1000:.1f}".replace('.', ','),
                        }
            except Exception:
                pass

            # Current-year exchange balance. Convention of the detail file:
            # positive = import, negative = export (France is a net exporter →
            # negative balance expected). Isolated so an exchanges outage does
            # not break the rest of the dashboard.
            echanges_ctx = {}
            try:
                from datetime import date as _date
                year = data['peak_year_datetime'].year
                df_ech = get_echanges_annual_import_export(
                    _date(year, 1, 1), data['dashboard_date'], pays='total'
                )
                row = df_ech[df_ech['annee'] == str(year)]
                if not row.empty:
                    solde_mwh = float(row['import_mwh'].iloc[0]) - float(row['export_mwh'].iloc[0])
                    echanges_ctx = {
                        'solde_echanges_twh': f"{abs(solde_mwh) / 1_000_000:.1f}".replace('.', ','),
                        'solde_exportateur': solde_mwh < 0,
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
                **echanges_ctx,
                'graph_conso_jour': graph_conso_jour,
                'graph_production_jour': graph_production_jour,
                'graph_echanges_flux': graph_echanges_flux,
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
    start_date, end_date = validate_and_get_dates(
        request, min_date, max_date, session_key='dates_conso'
    )

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
    filieres_selected = resolve_multi_filter(
        request, 'filiere', 'filiere_production', filieres,
        default=['nucleaire'], label="Filière"
    )

    # Validate and get dates from request
    start_date, end_date = validate_and_get_dates(
        request, min_date, max_date, session_key='dates_production'
    )

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
    pays_selected = resolve_multi_filter(
        request, 'pays', 'pays_echanges', pays_disponibles,
        default=['ech_comm_allemagne_belgique'], label="Pays"
    )

    # Country for the annual chart (bottom) — its own selector, fully
    # independent of the top filters (dates and curve country). Adds a 'total'
    # option (sum of all commercial borders). Its form only ever submits
    # `pays_annuel`, so that param alone tells an explicit choice apart from
    # a bare navigation (which reuses the remembered one).
    pays_annuel_options = {'total': 'Total', **pays_disponibles}
    if 'pays_annuel' in request.GET:
        pays_annuel = request.GET['pays_annuel']
        if pays_annuel not in pays_annuel_options:
            return HttpResponseBadRequest(f"Pays invalide. Choisissez parmi: {', '.join(pays_annuel_options.keys())}")
        request.session['pays_annuel_echanges'] = pays_annuel
    else:
        pays_annuel = request.session.get('pays_annuel_echanges', 'total')
        if pays_annuel not in pays_annuel_options:
            pays_annuel = 'total'

    # Validate and get dates from request (drives the load curve only)
    start_date, end_date = validate_and_get_dates(
        request, min_date, max_date, session_key='dates_echanges'
    )

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
def _humanize_rate(rate):
    """Transforme un taux de throttle ("1/2s", "10/min") en texte FR lisible."""
    units = [('sec', 'seconde'), ('min', 'minute'), ('hour', 'heure'),
             ('day', 'jour'), ('s', 'seconde'), ('m', 'minute'),
             ('h', 'heure'), ('d', 'jour')]
    count, rest = rate.split('/', 1)
    count = int(count)
    req = 'requête' if count == 1 else 'requêtes'
    for unit, label in units:
        if rest.endswith(unit):
            mult = int(rest[:-len(unit)]) if rest[:-len(unit)] else 1
            if mult == 1:
                return f"{count} {req} par {label}"
            return f"{count} {req} toutes les {mult} {label}s"
    return rate


def api(request):
    # Page portail : doc réservée aux utilisateurs connectés (le template
    # affiche sinon une invitation à se connecter/s'inscrire). Les endpoints
    # JSON sous /api/v1/ sont, eux, publics en phase 1.
    from .api import THROTTLE_BURST, THROTTLE_SUSTAINED
    from .api_key_views import MAX_ACTIVE_KEYS

    api_base = request.build_absolute_uri('/api/v1/').rstrip('/')
    context = {
        'api_base': api_base,
        'throttle_burst': _humanize_rate(THROTTLE_BURST),
        'throttle_sustained': _humanize_rate(THROTTLE_SUSTAINED),
        'max_active_keys': MAX_ACTIVE_KEYS,
    }

    # Gestion des clés d'API de l'utilisateur connecté (génération/révocation
    # dans api_key_views.py). `new_api_key` est la clé brute fraîchement créée,
    # affichée une seule fois puis effacée de la session.
    from .auth import get_user_from_session
    from .models import ApiKey
    user = get_user_from_session(request)
    if user:
        # On n'affiche que les clés actives : les révoquées restent en base
        # (soft-delete = trace d'audit) mais n'encombrent plus la liste.
        context['api_keys'] = ApiKey.objects.filter(
            user_sub=user['sub'], revoked_at__isnull=True
        )
        context['new_api_key'] = request.session.pop('new_api_key', None)

    return render(request, 'consommation/api.html', context)