import re

import duckdb
import pandas as pd
from django.conf import settings
from datetime import datetime, timedelta
from contextlib import contextmanager

from .constants import FILIERES, PAYS_ECHANGES
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

            # Endpoint S3-compatible hors AWS (ex. Scaleway) : hôte sans schéma
            # pour DuckDB, et style path (le virtual-host est propre à AWS).
            # Validation positive hôte[:port] — la blocklist de
            # _validate_s3_credential laisse passer ' et /, dangereux dans un SET.
            endpoint_url = settings.AWS_CONFIG.get('endpoint_url')
            if endpoint_url:
                host = endpoint_url.split('://', 1)[-1].rstrip('/')
                if not re.fullmatch(r"[A-Za-z0-9.-]+(:\d{1,5})?", host):
                    raise ValueError(f"Invalid S3 endpoint host: {host!r}")
                conn.execute(f"SET s3_endpoint='{host}'")
                conn.execute("SET s3_url_style='path'")

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


def get_production_data_multi(start_date, end_date, filieres):
    """
    Loads production data for a date range and several sectors (filières).
    Returns a wide DataFrame with one column per filière (named by its key).
    Uses validated column names to prevent SQL injection.
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Validate filieres to prevent SQL injection (before opening connection)
    valid_filieres = list(get_production_filieres().keys())
    for filiere in filieres:
        if filiere not in valid_filieres:
            raise ValueError(f"Filière invalide. Choisissez parmi: {', '.join(valid_filieres)}")

    if not filieres:
        raise ValueError("Au moins une filière doit être sélectionnée.")

    # Columns are validated keys, safe to interpolate (like get_production_data)
    cols = ", ".join(filieres)

    path = data_cache.get_local_path('production')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {cols}, source
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
            ORDER BY date_heure;
        """
        result = conn.execute(
            query,
            [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    # Translate source labels to French for consistency with consumption
    source_map = {
        'Consolidated Data': 'Données Consolidées',
        'Real-Time Data': 'Temps Réel'
    }
    result['source'] = result['source'].map(source_map).fillna(result['source'])

    return result


def get_consommation_peaks(start_date, end_date, n=5, direction='max'):
    """
    Top-N peaks (or troughs) of consumption with their exact datetime.
    Used by the chatbot to answer "pic / record / minimum" questions without
    downsampling.
    """
    if direction not in ('max', 'min'):
        raise ValueError("direction doit être 'max' ou 'min'")
    n = max(1, min(int(n), 20))
    order = 'DESC' if direction == 'max' else 'ASC'

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    path = data_cache.get_local_path('puissance')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, consommation AS value
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
              AND consommation IS NOT NULL
            ORDER BY consommation {order}
            LIMIT ?;
        """
        return conn.execute(
            query, [path, start_str, f"{end_str} 23:59:59", n]
        ).fetchdf()


def get_production_peaks(filiere, start_date, end_date, n=5, direction='max'):
    """Top-N peaks (or troughs) of production for a given filière."""
    if direction not in ('max', 'min'):
        raise ValueError("direction doit être 'max' ou 'min'")
    valid_filieres = list(get_production_filieres().keys())
    if filiere not in valid_filieres:
        raise ValueError(f"Filière invalide. Choisissez parmi: {', '.join(valid_filieres)}")
    n = max(1, min(int(n), 20))
    order = 'DESC' if direction == 'max' else 'ASC'

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    path = data_cache.get_local_path('production')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {filiere} AS value
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
              AND {filiere} IS NOT NULL
            ORDER BY {filiere} {order}
            LIMIT ?;
        """
        return conn.execute(
            query, [path, start_str, f"{end_str} 23:59:59", n]
        ).fetchdf()


def get_echanges_peaks(pays, start_date, end_date, n=5, direction='max'):
    """Top-N peaks (or troughs) of cross-border exchanges for a given country."""
    if direction not in ('max', 'min'):
        raise ValueError("direction doit être 'max' ou 'min'")
    valid_pays = list(get_echanges_pays().keys())
    if pays not in valid_pays:
        raise ValueError(f"Pays invalide. Choisissez parmi: {', '.join(valid_pays)}")
    n = max(1, min(int(n), 20))
    order = 'DESC' if direction == 'max' else 'ASC'

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {pays} AS value
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
              AND {pays} IS NOT NULL
            ORDER BY {pays} {order}
            LIMIT ?;
        """
        return conn.execute(
            query, [path, start_str, f"{end_str} 23:59:59", n]
        ).fetchdf()


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
    Returns the list of available exchange countries.
    Single source of truth: PAYS_ECHANGES in constants.py.
    """
    return dict(PAYS_ECHANGES)


def get_echanges_pays_commerciaux():
    """
    Commercial-exchange countries only (excludes the physical total).
    Used by the Échanges page, which focuses on commercial flows per border.
    """
    return {k: v for k, v in get_echanges_pays().items() if k != 'ech_physiques'}


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

    # Validate pays to prevent SQL injection (before opening connection).
    # `total` = sum of the commercial borders at each step (France's overall
    # commercial flow); column names come from our own dict, so the expression
    # built below is injection-free.
    valid_pays = list(get_echanges_pays().keys())
    if pays == 'total':
        commercial = list(get_echanges_pays_commerciaux().keys())
        col_expr = "(" + " + ".join(f"COALESCE({c}, 0)" for c in commercial) + ")"
    elif pays in valid_pays:
        col_expr = pays
    else:
        raise ValueError(f"Pays invalide. Choisissez parmi: total, {', '.join(valid_pays)}")

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {col_expr} AS echange, source
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
            ORDER BY date_heure;
        """
        result = conn.execute(
            query,
            [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    # Translate source labels to French for consistency
    source_map = {
        'Consolidated Data': 'Données Consolidées',
        'Real-Time Data': 'Temps Réel'
    }
    result['source'] = result['source'].map(source_map).fillna(result['source'])

    return result


def get_echanges_data_multi(start_date, end_date, pays_list):
    """
    Loads exchange data for a date range and several commercial borders.
    Returns a wide DataFrame with one column per country (named by its key),
    suitable for a multi-line chart. Uses validated column names to prevent
    SQL injection.
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Validate pays to prevent SQL injection (before opening connection)
    valid_pays = list(get_echanges_pays().keys())
    for pays in pays_list:
        if pays not in valid_pays:
            raise ValueError(f"Pays invalide. Choisissez parmi: {', '.join(valid_pays)}")

    if not pays_list:
        raise ValueError("Au moins un pays doit être sélectionné.")

    # Columns are validated keys, safe to interpolate (like get_echanges_data)
    cols = ", ".join(pays_list)

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            SELECT date_heure, {cols}, source
            FROM read_parquet(?)
            WHERE date_heure BETWEEN ? AND ?
            ORDER BY date_heure;
        """
        result = conn.execute(
            query,
            [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    # Translate source labels to French for consistency
    source_map = {
        'Consolidated Data': 'Données Consolidées',
        'Real-Time Data': 'Temps Réel'
    }
    result['source'] = result['source'].map(source_map).fillna(result['source'])

    return result


def get_echanges_annual_import_export(start_date, end_date, pays='total'):
    """
    Annual import/export volumes (MWh) for a commercial border, derived from the
    detailed exchange file.

    `pays` is either a single ech_comm_* column, or 'total' (sum of all
    commercial borders at each time step → France's overall commercial balance).

    The detail file stores signed power per time step (convention for this
    dataset: positive = import, negative = export). The energy carried by each
    step is power × its duration; the duration is read directly from the gap to
    the next sample (capped at 1h to absorb data gaps), so the result is correct
    whatever the sampling cadence — no per-source divisor to hard-code.

    Returns a DataFrame with columns:
        annee       – year (string, so the x-axis stays categorical)
        import_mwh  – positive volume imported (MWh)
        export_mwh  – positive volume exported (MWh)
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Build the value/filter expressions from our own (safe) column names — no
    # user input reaches the SQL string, so there is no injection surface.
    commercial = list(get_echanges_pays_commerciaux().keys())
    if pays == 'total':
        val_expr = "(" + " + ".join(f"COALESCE({c}, 0)" for c in commercial) + ")"
        notnull_expr = "(" + " OR ".join(f"{c} IS NOT NULL" for c in commercial) + ")"
    elif pays in commercial:
        val_expr = pays
        notnull_expr = f"{pays} IS NOT NULL"
    else:
        raise ValueError(f"Pays invalide. Choisissez parmi: total, {', '.join(commercial)}")

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            WITH stepped AS (
                SELECT
                    date_heure,
                    {val_expr} AS val,
                    LEAST(
                        date_diff('second', date_heure,
                            lead(date_heure) OVER (ORDER BY date_heure)) / 3600.0,
                        1.0
                    ) AS dt_h
                FROM read_parquet(?)
                WHERE date_heure BETWEEN ? AND ?
                  AND {notnull_expr}
            )
            SELECT
                CAST(year(date_heure) AS VARCHAR) AS annee,
                SUM(CASE WHEN val > 0 THEN val * dt_h ELSE 0 END) AS import_mwh,
                -SUM(CASE WHEN val < 0 THEN val * dt_h ELSE 0 END) AS export_mwh
            FROM stepped
            GROUP BY 1
            ORDER BY 1;
        """
        result = conn.execute(
            query, [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    return result


def get_echanges_net_by_border(start_date, end_date):
    """
    Import/export/solde volumes (MWh) over the whole period, one row per
    commercial border — used for the homepage flow map (France ↔ voisins).

    Same energy method as get_echanges_annual_import_export (signed power ×
    real step duration). Convention of the detail file: positive = import,
    negative = export.

    Returns a dict keyed by the ech_comm_* column name:
        {col: {'import_mwh': float, 'export_mwh': float, 'net_mwh': float}}
    where net_mwh = import − export (positive ⇒ France net importer on that
    border). Borders with no data over the period are omitted.
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Column names come from our own dict (safe) → no SQL injection surface.
    commercial = list(get_echanges_pays_commerciaux().keys())
    keep_cols = "".join(f", {c}" for c in commercial)
    notnull_expr = " OR ".join(f"{c} IS NOT NULL" for c in commercial)

    selects = []
    for col in commercial:
        selects.append(f"SUM(CASE WHEN {col} > 0 THEN {col} * dt_h ELSE 0 END) AS {col}_import")
        selects.append(f"-SUM(CASE WHEN {col} < 0 THEN {col} * dt_h ELSE 0 END) AS {col}_export")
    select_cols = ",\n                ".join(selects)

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            WITH stepped AS (
                SELECT
                    LEAST(
                        date_diff('second', date_heure,
                            lead(date_heure) OVER (ORDER BY date_heure)) / 3600.0,
                        1.0
                    ) AS dt_h{keep_cols}
                FROM read_parquet(?)
                WHERE date_heure BETWEEN ? AND ?
                  AND ({notnull_expr})
            )
            SELECT {select_cols}
            FROM stepped;
        """
        row = conn.execute(
            query, [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    result = {}
    if not row.empty:
        for col in commercial:
            imp = float(row[f"{col}_import"].iloc[0] or 0.0)
            exp = float(row[f"{col}_export"].iloc[0] or 0.0)
            if imp == 0.0 and exp == 0.0:
                continue
            result[col] = {
                'import_mwh': imp,
                'export_mwh': exp,
                'net_mwh': imp - exp,
            }
    return result


def get_echanges_annual_detail(start_date, end_date):
    """
    Annual import/export (MWh) for every commercial border plus the overall
    total, in a single wide table — used for the full CSV export.

    Same energy method as get_echanges_annual_import_export (power × real step
    duration). Returns columns: annee, then for each border and 'total':
    <name>_import_mwh, <name>_export_mwh. (Solde is derived by the caller.)
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Column names come from our own dict (safe), so building SQL is injection-free.
    commercial = list(get_echanges_pays_commerciaux().keys())
    total_expr = "(" + " + ".join(f"COALESCE({c}, 0)" for c in commercial) + ")"

    selects = []
    for col in commercial:
        short = col.replace("ech_comm_", "")
        selects.append(f"SUM(CASE WHEN {col} > 0 THEN {col} * dt_h ELSE 0 END) AS {short}_import_mwh")
        selects.append(f"-SUM(CASE WHEN {col} < 0 THEN {col} * dt_h ELSE 0 END) AS {short}_export_mwh")
    selects.append(f"SUM(CASE WHEN {total_expr} > 0 THEN {total_expr} * dt_h ELSE 0 END) AS total_import_mwh")
    selects.append(f"-SUM(CASE WHEN {total_expr} < 0 THEN {total_expr} * dt_h ELSE 0 END) AS total_export_mwh")

    notnull_expr = " OR ".join(f"{c} IS NOT NULL" for c in commercial)
    select_cols = ",\n                ".join(selects)
    keep_cols = "".join(f", {c}" for c in commercial)

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            WITH stepped AS (
                SELECT
                    date_heure,
                    LEAST(
                        date_diff('second', date_heure,
                            lead(date_heure) OVER (ORDER BY date_heure)) / 3600.0,
                        1.0
                    ) AS dt_h{keep_cols}
                FROM read_parquet(?)
                WHERE date_heure BETWEEN ? AND ?
                  AND ({notnull_expr})
            )
            SELECT
                CAST(year(date_heure) AS VARCHAR) AS annee,
                {select_cols}
            FROM stepped
            GROUP BY 1
            ORDER BY 1 DESC;
        """
        result = conn.execute(
            query, [path, start_str, f"{end_str} 23:59:59"]
        ).fetchdf()

    return result


# ===== Énergie mensuelle (API publique v1) =====
# Toutes ces fonctions intègrent puissance × durée réelle du pas (dt_h, plafonné
# à 1h pour absorber les trous de données) puis somment par mois calendaire. Pas
# de diviseur en dur : le résultat est correct quelle que soit la cadence
# (15/30 min). Même méthode que get_echanges_annual_import_export, mais groupée
# par mois. Les fichiers conso/production pouvant porter plusieurs sources pour
# un même horodatage, on déduplique d'abord par date_heure (AVG) pour ne pas
# fausser les durées de pas.

def get_consommation_energie_mensuelle(start_date, end_date):
    """Énergie consommée (MWh) par mois sur une plage. Colonnes: mois, energie_mwh."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    path = data_cache.get_local_path('puissance')

    with get_duckdb_connection(path) as conn:
        query = """
            WITH per_step AS (
                SELECT date_heure, AVG(consommation) AS val
                FROM read_parquet(?)
                WHERE date_heure BETWEEN ? AND ?
                  AND consommation IS NOT NULL
                GROUP BY date_heure
            ),
            stepped AS (
                SELECT date_heure, val,
                    LEAST(
                        date_diff('second', date_heure,
                            lead(date_heure) OVER (ORDER BY date_heure)) / 3600.0,
                        1.0
                    ) AS dt_h
                FROM per_step
            )
            SELECT strftime(date_heure, '%Y-%m') AS mois,
                   SUM(val * dt_h) AS energie_mwh
            FROM stepped
            GROUP BY 1
            ORDER BY 1;
        """
        result = conn.execute(query, [path, start_str, f"{end_str} 23:59:59"]).fetchdf()
    return result


def get_production_energie_mensuelle(start_date, end_date, filiere='nucleaire'):
    """Énergie produite (MWh) par mois pour une filière. Colonnes: mois, energie_mwh."""
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Validate filiere to prevent SQL injection (before opening connection).
    valid_filieres = list(get_production_filieres().keys())
    if filiere not in valid_filieres:
        raise ValueError(f"Filière invalide. Choisissez parmi: {', '.join(valid_filieres)}")

    path = data_cache.get_local_path('production')
    with get_duckdb_connection(path) as conn:
        query = f"""
            WITH per_step AS (
                SELECT date_heure, AVG({filiere}) AS val
                FROM read_parquet(?)
                WHERE date_heure BETWEEN ? AND ?
                  AND {filiere} IS NOT NULL
                GROUP BY date_heure
            ),
            stepped AS (
                SELECT date_heure, val,
                    LEAST(
                        date_diff('second', date_heure,
                            lead(date_heure) OVER (ORDER BY date_heure)) / 3600.0,
                        1.0
                    ) AS dt_h
                FROM per_step
            )
            SELECT strftime(date_heure, '%Y-%m') AS mois,
                   SUM(val * dt_h) AS energie_mwh
            FROM stepped
            GROUP BY 1
            ORDER BY 1;
        """
        result = conn.execute(query, [path, start_str, f"{end_str} 23:59:59"]).fetchdf()
    return result


def get_echanges_energie_mensuelle(start_date, end_date, pays='total'):
    """Import/export (MWh) par mois pour une frontière commerciale ou 'total'.

    Convention du jeu de données : puissance signée, positif = import vers la
    France, négatif = export. Colonnes: mois, import_mwh, export_mwh (volumes
    positifs). Même méthode d'énergie que get_echanges_annual_import_export.
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Expressions construites depuis nos propres noms de colonnes (sûr).
    commercial = list(get_echanges_pays_commerciaux().keys())
    if pays == 'total':
        val_expr = "(" + " + ".join(f"COALESCE({c}, 0)" for c in commercial) + ")"
        notnull_expr = "(" + " OR ".join(f"{c} IS NOT NULL" for c in commercial) + ")"
    elif pays in commercial:
        val_expr = pays
        notnull_expr = f"{pays} IS NOT NULL"
    else:
        raise ValueError(f"Pays invalide. Choisissez parmi: total, {', '.join(commercial)}")

    path = data_cache.get_local_path('echanges')
    with get_duckdb_connection(path) as conn:
        query = f"""
            WITH stepped AS (
                SELECT
                    date_heure,
                    {val_expr} AS val,
                    LEAST(
                        date_diff('second', date_heure,
                            lead(date_heure) OVER (ORDER BY date_heure)) / 3600.0,
                        1.0
                    ) AS dt_h
                FROM read_parquet(?)
                WHERE date_heure BETWEEN ? AND ?
                  AND {notnull_expr}
            )
            SELECT
                strftime(date_heure, '%Y-%m') AS mois,
                SUM(CASE WHEN val > 0 THEN val * dt_h ELSE 0 END) AS import_mwh,
                -SUM(CASE WHEN val < 0 THEN val * dt_h ELSE 0 END) AS export_mwh
            FROM stepped
            GROUP BY 1
            ORDER BY 1;
        """
        result = conn.execute(query, [path, start_str, f"{end_str} 23:59:59"]).fetchdf()
    return result


def get_parc_installe_data():
    """
    Computes monthly installed capacity (MW) for wind (onshore/offshore) and solar.
    Derived from: parc_mw = production_mwh / (capacity_factor * hours_in_month)
    """
    eol_prod_path = data_cache.get_local_path('rte_eolien_production')
    eol_fc_path = data_cache.get_local_path('rte_eolien_facteur_charge')
    sol_prod_path = data_cache.get_local_path('rte_solaire_production')
    sol_fc_path = data_cache.get_local_path('rte_solaire_facteur_charge')

    with get_duckdb_connection(eol_prod_path, eol_fc_path, sol_prod_path, sol_fc_path) as conn:
        eol_df = conn.execute("""
            SELECT
                p.date,
                p.filiere,
                p.valeur_mwh / (fc.facteur_charge_pct / 100.0
                    * day(last_day(strptime(p.date || '-01', '%Y-%m-%d'))) * 24) AS parc_mw
            FROM read_parquet(?) p
            JOIN read_parquet(?) fc
                ON p.date = fc.date
                AND p.filiere = regexp_replace(fc.type, ' - Facteur de charge moyen', '')
            WHERE p.filiere IN ('Eolien terrestre', 'Eolien en mer')
              AND fc.facteur_charge_pct > 0
            ORDER BY p.date, p.filiere
        """, [eol_prod_path, eol_fc_path]).fetchdf()

        sol_df = conn.execute("""
            SELECT
                p.date,
                'Solaire' AS filiere,
                p.valeur_mwh / (fc.facteur_charge_pct / 100.0
                    * day(last_day(strptime(p.date || '-01', '%Y-%m-%d'))) * 24) AS parc_mw
            FROM read_parquet(?) p
            JOIN read_parquet(?) fc ON p.date = fc.date
            WHERE p.filiere = 'Production solaire'
              AND fc.facteur_charge_pct > 0
            ORDER BY p.date
        """, [sol_prod_path, sol_fc_path]).fetchdf()

    df = pd.concat([eol_df, sol_df], ignore_index=True)
    return df.sort_values('date').reset_index(drop=True)


_PMAX_TO_FILIERE = {
    'Nucléaire': 'nucleaire',
    'Gaz': 'gaz',
    'Charbon': 'charbon',
    'Fioul': 'fioul',
    'Bioénergies': 'bioenergies',
    'Solaire': 'solaire',
    'Éolien': 'eolien',
    'Énergies marines': 'eolien',
    "Hydraulique fil de l'eau": 'hydraulique',
    'Hydraulique STEP': 'hydraulique',
    'Hydraulique lacs': 'hydraulique',
}


def get_parc_pmax():
    """Puissance max installée par filière (MW), mappée sur FILIERES."""
    path = data_cache.get_local_path('rte_pmax')
    result = {f: 0.0 for f in FILIERES}
    try:
        with get_duckdb_connection(path) as conn:
            df = conn.execute(
                "SELECT filiere, puissance_max_mw FROM read_parquet(?)", [path]
            ).fetchdf()
        for _, row in df.iterrows():
            key = _PMAX_TO_FILIERE.get(row['filiere'])
            if key:
                result[key] += float(row['puissance_max_mw'])
    except Exception:
        pass
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

    dashboard_date = pd.to_datetime(conso_ts['date_heure']).max().to_pydatetime()
    peak_year_value = int(round(float(peak_year_df['consommation'].iloc[0])))
    peak_year_datetime = pd.to_datetime(peak_year_df['date_heure'].iloc[0]).to_pydatetime()
    peak_all_value = int(round(float(peak_all_df['consommation'].iloc[0])))
    peak_all_datetime = pd.to_datetime(peak_all_df['date_heure'].iloc[0]).to_pydatetime()

    parc_pmax = get_parc_pmax()

    return {
        'dashboard_date': dashboard_date,
        'peak_year_value': peak_year_value,
        'peak_year_datetime': peak_year_datetime,
        'peak_all_value': peak_all_value,
        'peak_all_datetime': peak_all_datetime,
        'conso_ts': conso_ts,
        'production_ts': production_ts,
        'production_mix_year': production_mix_year,
        'parc_pmax': parc_pmax,
    }