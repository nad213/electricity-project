import duckdb
import pandas as pd
from django.conf import settings
from datetime import datetime, timedelta
import re


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


def get_duckdb_connection():
    """
    Creates and configures a DuckDB connection with S3 access
    Uses validated credentials to prevent SQL injection
    """
    # Validate credentials before using them
    region = _validate_s3_credential(settings.AWS_CONFIG['region'], 'AWS region')
    access_key = _validate_s3_credential(settings.AWS_CONFIG['access_key'], 'AWS access key')
    secret_key = _validate_s3_credential(settings.AWS_CONFIG['secret_key'], 'AWS secret key')

    conn = duckdb.connect()

    # Install and load httpfs
    conn.execute("INSTALL httpfs")
    conn.execute("LOAD httpfs")

    # Set S3 credentials using parameterized approach
    # Note: DuckDB's SET doesn't support parameterized queries, so we validate inputs strictly
    conn.execute(f"SET s3_region='{region}'")
    conn.execute(f"SET s3_access_key_id='{access_key}'")
    conn.execute(f"SET s3_secret_access_key='{secret_key}'")

    return conn


def get_date_range():
    """
    Retrieves the min and max dates from the dataset
    """
    conn = get_duckdb_connection()
    query = """
        SELECT MIN(date_heure) as min_date, MAX(date_heure) as max_date
        FROM read_parquet(?);
    """
    result = conn.execute(query, [settings.S3_PATHS['puissance']]).fetchdf()
    conn.close()

    min_date = pd.to_datetime(result['min_date'].iloc[0]).date()
    max_date = pd.to_datetime(result['max_date'].iloc[0]).date()

    return min_date, max_date


def get_puissance_data(start_date, end_date):
    """
    Loads power data for a date range
    Uses parameterized queries to prevent SQL injection
    """
    conn = get_duckdb_connection()

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    query = """
        SELECT date_heure, consommation, source
        FROM read_parquet(?)
        WHERE date_heure BETWEEN ? AND ?
        ORDER BY date_heure;
    """
    result = conn.execute(
        query,
        [settings.S3_PATHS['puissance'], start_str, f"{end_str} 23:59:59"]
    ).fetchdf()
    conn.close()

    return result


def get_annual_data():
    """
    Loads annual data
    """
    conn = get_duckdb_connection()
    query = "SELECT * FROM read_parquet(?)"
    result = conn.execute(query, [settings.S3_PATHS['annuel']]).fetchdf()
    conn.close()
    return result


def get_monthly_data():
    """
    Loads monthly data
    """
    conn = get_duckdb_connection()
    query = "SELECT * FROM read_parquet(?)"
    df = conn.execute(query, [settings.S3_PATHS['mensuel']]).fetchdf()
    conn.close()
    df['annee_mois_str'] = df['annee_mois'].astype(str)
    return df