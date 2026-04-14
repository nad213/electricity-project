import duckdb
import pandas as pd
from django.conf import settings
from datetime import datetime, timedelta
from contextlib import contextmanager

from .constants import FILIERES
from . import data_cache


def _validate_s3_credential(value, name):
    """
    Validates AWS credentials to prevent SQL injection
    Raises ValueError if the credential contains suspicious characters
    """
    if not value:
        raise ValueError(f"{name} is required")

    # Check for SQL injection patterns
    suspicious_patterns = [';', '--', '/*', '*/', 'DROP', 'DELETE', 'INSERT', 'UPDATE']
    value_upper = value.upper()

    for pattern in suspicious_patterns:
        if pattern in value_upper:
            raise ValueError(f"Invalid character or keyword in {name}")

    return value


@contextmanager
def get_duckdb_connection(*paths):
    """
    Creates a DuckDB connection.  Configures S3 access (httpfs + credentials)
    only if any of the supplied *paths* is an s3:// URL — i.e. when the local
    cache is unavailable and we fall back to reading directly from S3.

    Usage:
        path = data_cache.get_local_path('puissance')
        with get_duckdb_connection(path) as conn:
            df = conn.execute(query, [path]).fetchdf()
    """
    needs_s3 = any(p and isinstance(p, str) and p.startswith("s3://") for p in paths)

    conn = duckdb.connect()
    try:
        if needs_s3:
            # Validate credentials before using them
            region = _validate_s3_credential(settings.AWS_CONFIG['region'], 'AWS region')
            access_key = _validate_s3_credential(settings.AWS_CONFIG['access_key'], 'AWS access key')
            secret_key = _validate_s3_credential(settings.AWS_CONFIG['secret_key'], 'AWS secret key')

            conn.execute("INSTALL httpfs")
            conn.execute("LOAD httpfs")
            # Note: DuckDB's SET doesn't support parameterized queries, so we validate inputs strictly
            conn.execute(f"SET s3_region='{region}'")
            conn.execute(f"SET s3_access_key_id='{access_key}'")
            conn.execute(f"SET s3_secret_access_key='{secret_key}'")

        yield conn
    finally:
        conn.close()


def get_date_range():
    """
    Retrieves the min and max dates from the dataset
    """
    path = data_cache.get_local_path('puissance')
    with get_duckdb_connection(path) as conn:
        query = """
            SELECT MIN(date_heure) as min_date, MAX(date_heure) as max_date
            FROM read_parquet(?);
        """
        result = conn.execute(query, [path]).fetchdf()

    min_date = pd.to_datetime(result['min_date'].iloc[0]).date()
    max_date = pd.to_datetime(result['max_date'].iloc[0]).date()

    return min_date, max_date


def get_puissance_data(start_date, end_date):
    """
    Loads power data for a date range
    Uses parameterized queries to prevent SQL injection
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    path = data_cache.get_local_path('puissance')

    with get_duckdb_connection(path) as conn:
        query = """
            SELECT date_heure, consommation, source
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
            ORDER BY date_heure;
        """
        result = conn.execute(
            query,
            [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    return result


def get_annual_data():
    """
    Loads annual data
    """
    path = data_cache.get_local_path('annuel')
    with get_duckdb_connection(path) as conn:
        query = "SELECT * FROM read_parquet(?)"
        df = conn.execute(query, [path]).fetchdf()
    return df


def get_monthly_data():
    """
    Loads monthly data
    Aggregates by year_month to handle multiple sources (Consolidated/Real-Time)
    """
    path = data_cache.get_local_path('mensuel')
    with get_duckdb_connection(path) as conn:
        query = "SELECT * FROM read_parquet(?)"
        df = conn.execute(query, [path]).fetchdf()
    # Aggregate by year_month to sum values from different sources
    df = df.groupby('year_month', as_index=False)['monthly_consumption'].sum()
    return df


def get_production_date_range():
    """
    Retrieves the min and max dates from the production dataset
    """
    path = data_cache.get_local_path('production')
    with get_duckdb_connection(path) as conn:
        query = """
            SELECT MIN(date_heure) as min_date, MAX(date_heure) as max_date
            FROM read_parquet(?);
        """
        result = conn.execute(query, [path]).fetchdf()

    min_date = pd.to_datetime(result['min_date'].iloc[0]).date()
    max_date = pd.to_datetime(result['max_date'].iloc[0]).date()

    return min_date, max_date


def get_production_filieres():
    """
    Returns the list of available production sectors (filières)
    """
    # Based on the parquet structure, these are the main sectors
    filieres = {
        'nucleaire': 'Nucléaire',
        'hydraulique': 'Hydraulique',
        'eolien': 'Éolien',
        'solaire': 'Solaire',
        'gaz': 'Gaz',
        'charbon': 'Charbon',
        'fioul': 'Fioul',
        'bioenergies': 'Bioénergies',
    }
    return filieres


def get_production_data(start_date, end_date, filiere='nucleaire'):
    """
    Loads production data for a date range and specific sector
    Uses parameterized queries to prevent SQL injection
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Validate filiere to prevent SQL injection (before opening connection)
    valid_filieres = list(get_production_filieres().keys())
    if filiere not in valid_filieres:
        raise ValueError(f"Filière invalide. Choisissez parmi: {', '.join(valid_filieres)}")

    path = data_cache.get_local_path('production')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {filiere}, source
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
            ORDER BY date_heure;
        """
        result = conn.execute(
            query,
            [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    # Rename the filiere column to 'production' for consistency in templates
    result = result.rename(columns={filiere: 'production'})

    # Translate source labels to French for consistency with consumption
    source_map = {
        'Consolidated Data': 'Données Consolidées',
        'Real-Time Data': 'Temps Réel'
    }
    result['source'] = result['source'].map(source_map).fillna(result['source'])

    return result


def get_production_annual_data():
    """
    Loads annual production data aggregated by sector from S3
    """
    path = data_cache.get_local_path('production_annuel')
    with get_duckdb_connection(path) as conn:
        query = "SELECT * FROM read_parquet(?)"
        result = conn.execute(query, [path]).fetchdf()
    return result


def get_production_monthly_data():
    """
    Loads monthly production data aggregated by sector from S3
    """
    path = data_cache.get_local_path('production_mensuel')
    with get_duckdb_connection(path) as conn:
        query = "SELECT * FROM read_parquet(?)"
        result = conn.execute(query, [path]).fetchdf()
    return result


def get_echanges_pays():
    """
    Returns the list of available exchange countries
    """
    pays = {
        'ech_physiques': 'Échanges physiques (total)',
        'ech_comm_angleterre': 'Angleterre',
        'ech_comm_espagne': 'Espagne',
        'ech_comm_italie': 'Italie',
        'ech_comm_suisse': 'Suisse',
        'ech_comm_allemagne_belgique': 'Allemagne / Belgique',
    }
    return pays


def get_echanges_date_range():
    """
    Retrieves the min and max dates from the echanges dataset
    """
    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = """
            SELECT MIN(date_heure) as min_date, MAX(date_heure) as max_date
            FROM read_parquet(?);
        """
        result = conn.execute(query, [path]).fetchdf()

    min_date = pd.to_datetime(result['min_date'].iloc[0]).date()
    max_date = pd.to_datetime(result['max_date'].iloc[0]).date()

    return min_date, max_date


def get_echanges_data(start_date, end_date, pays='ech_physiques'):
    """
    Loads exchange data for a date range and specific country
    Uses parameterized queries to prevent SQL injection
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Validate pays to prevent SQL injection (before opening connection)
    valid_pays = list(get_echanges_pays().keys())
    if pays not in valid_pays:
        raise ValueError(f"Pays invalide. Choisissez parmi: {', '.join(valid_pays)}")

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {pays}, source
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
            ORDER BY date_heure;
        """
        result = conn.execute(
            query,
            [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    # Rename the pays column to 'echange' for consistency in templates
    result = result.rename(columns={pays: 'echange'})

    # Translate source labels to French for consistency
    source_map = {
        'Consolidated Data': 'Données Consolidées',
        'Real-Time Data': 'Temps Réel'
    }
    result['source'] = result['source'].map(source_map).fillna(result['source'])

    return result


def get_dashboard_data():
    """
    Returns data for the homepage dashboard.

    Returns a dict with:
        dashboard_date      : latest available date (date object)
        peak_year_value     : peak consumption of current year (int MW)
        peak_year_datetime  : datetime of that peak (datetime)
        peak_all_value      : peak consumption over all history (int MW)
        peak_all_datetime   : datetime of that peak (datetime)
        conso_ts            : DataFrame [date_heure, consommation] for latest day
        production_ts       : DataFrame [date_heure, nucleaire, ...] for latest day
        production_mix_year : dict {filiere_key: mwh (float)} for current year
    Returns None if data is unavailable.
    """
    latest_day_subquery = "SELECT MAX(CAST(date_heure AS DATE)) FROM read_parquet(?)"
    filieres = list(FILIERES.keys())
    filieres_sql = ', '.join(filieres)
    filieres_sum_sql = ', '.join([f"COALESCE(SUM({f}), 0) / 2.0 as {f}" for f in filieres])

    puissance_path = data_cache.get_local_path('puissance')
    production_path = data_cache.get_local_path('production')
    production_annuel_path = data_cache.get_local_path('production_annuel')

    with get_duckdb_connection(puissance_path, production_path, production_annuel_path) as conn:
        # Peak conso current year
        peak_year_df = conn.execute("""
            SELECT date_heure, consommation FROM read_parquet(?)
            WHERE EXTRACT(YEAR FROM date_heure) = EXTRACT(YEAR FROM CURRENT_DATE)
            ORDER BY consommation DESC LIMIT 1
        """, [puissance_path]).fetchdf()

        # Peak conso all history
        peak_all_df = conn.execute("""
            SELECT date_heure, consommation FROM read_parquet(?)
            ORDER BY consommation DESC LIMIT 1
        """, [puissance_path]).fetchdf()

        # Consumption time series for the latest available day
        conso_ts = conn.execute(f"""
            SELECT date_heure, consommation
            FROM read_parquet(?)
            WHERE CAST(date_heure AS DATE) = ({latest_day_subquery})
            ORDER BY date_heure
        """, [puissance_path, puissance_path]).fetchdf()

        if conso_ts.empty:
            return None

        # Production time series for the latest available day (all filieres)
        production_ts = conn.execute(f"""
            SELECT date_heure, {filieres_sql}
            FROM read_parquet(?)
            WHERE CAST(date_heure AS DATE) = ({latest_day_subquery})
            ORDER BY date_heure
        """, [production_path, production_path]).fetchdf()

        # Production mix for current year (annual parquet first, fallback on detail)
        production_mix_year = {}
        try:
            annual_df = conn.execute("""
                SELECT * FROM read_parquet(?)
                WHERE year = EXTRACT(YEAR FROM CURRENT_DATE)
            """, [production_annuel_path]).fetchdf()

            if not annual_df.empty:
                for f in filieres:
                    col = f"{f}_yearly_mwh"
                    production_mix_year[f] = float(annual_df[col].iloc[0]) if col in annual_df.columns else 0.0
            else:
                # Fallback: sum half-hourly MW values / 2 to get MWh
                fallback_df = conn.execute(f"""
                    SELECT {filieres_sum_sql}
                    FROM read_parquet(?)
                    WHERE EXTRACT(YEAR FROM date_heure) = EXTRACT(YEAR FROM CURRENT_DATE)
                """, [production_path]).fetchdf()
                production_mix_year = {f: float(fallback_df[f].iloc[0]) for f in filieres}
        except Exception:
            production_mix_year = {f: 0.0 for f in filieres}

    dashboard_date = pd.to_datetime(conso_ts['date_heure']).max().date()
    peak_year_value = int(round(float(peak_year_df['consommation'].iloc[0])))
    peak_year_datetime = pd.to_datetime(peak_year_df['date_heure'].iloc[0]).to_pydatetime()
    peak_all_value = int(round(float(peak_all_df['consommation'].iloc[0])))
    peak_all_datetime = pd.to_datetime(peak_all_df['date_heure'].iloc[0]).to_pydatetime()

    return {
        'dashboard_date': dashboard_date,
        'peak_year_value': peak_year_value,
        'peak_year_datetime': peak_year_datetime,
        'peak_all_value': peak_all_value,
        'peak_all_datetime': peak_all_datetime,
        'conso_ts': conso_ts,
        'production_ts': production_ts,
        'production_mix_year': production_mix_year,
    }