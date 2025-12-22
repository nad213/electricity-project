import duckdb
import pandas as pd
from django.conf import settings
from datetime import datetime, timedelta


def get_duckdb_connection():
    """
    Creates and configures a DuckDB connection with S3 access
    """
    conn = duckdb.connect()
    conn.execute(f"""
        INSTALL httpfs;
        LOAD httpfs;
        SET s3_region='{settings.AWS_CONFIG['region']}';
        SET s3_access_key_id='{settings.AWS_CONFIG['access_key']}';
        SET s3_secret_access_key='{settings.AWS_CONFIG['secret_key']}';
    """)
    return conn


def get_date_range():
    """
    Retrieves the min and max dates from the dataset
    """
    conn = get_duckdb_connection()
    query = f"""
        SELECT MIN(date_heure) as min_date, MAX(date_heure) as max_date
        FROM read_parquet('{settings.S3_PATHS['puissance']}');
    """
    result = conn.execute(query).fetchdf()
    
    min_date = pd.to_datetime(result['min_date'].iloc[0]).date()
    max_date = pd.to_datetime(result['max_date'].iloc[0]).date()
    
    return min_date, max_date


def get_puissance_data(start_date, end_date):
    """
    Loads power data for a date range
    """
    conn = get_duckdb_connection()
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    query = f"""
        SELECT date_heure, consommation, source
        FROM read_parquet('{settings.S3_PATHS['puissance']}')
        WHERE date_heure BETWEEN '{start_str}' AND '{end_str} 23:59:59'
        ORDER BY date_heure;
    """
    return conn.execute(query).fetchdf()


def get_annual_data():
    """
    Loads annual data
    """
    conn = get_duckdb_connection()
    query = f"SELECT * FROM read_parquet('{settings.S3_PATHS['annuel']}')"
    return conn.execute(query).fetchdf()


def get_monthly_data():
    """
    Loads monthly data
    """
    conn = get_duckdb_connection()
    query = f"SELECT * FROM read_parquet('{settings.S3_PATHS['mensuel']}')"
    df = conn.execute(query).fetchdf()
    df['annee_mois_str'] = df['annee_mois'].astype(str)
    return df