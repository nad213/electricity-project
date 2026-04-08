import os
import io
import csv
import requests
import boto3
import pandas as pd
from datetime import datetime

ODRE_FILES = [
    {
        "url": "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-national-tr/exports/parquet?lang=fr&timezone=Europe%2FBerlin",
        "file_name": "eco2mix-national-tr.parquet",
    },
    {
        "url": "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-national-cons-def/exports/parquet?lang=fr&timezone=Europe%2FBerlin",
        "file_name": "eco2mix-national-cons-def.parquet",
    },
]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_files(s3, bucket):
    """Telecharge les fichiers ODRE et les stocke dans 01_downloaded/."""
    for entry in ODRE_FILES:
        url = entry["url"]
        file_name = entry["file_name"]
        print(f"INFO: Downloading {file_name} from {url}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        buffer = io.BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            buffer.write(chunk)
        buffer.seek(0)
        s3_key = f"01_downloaded/{file_name}"
        s3.upload_fileobj(Fileobj=buffer, Bucket=bucket, Key=s3_key)
        print(f"SUCCESS: Uploaded to s3://{bucket}/{s3_key}")


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def merge_with_existing(s3, bucket, key, new_df, merge_key):
    """
    Merge new_df avec le fichier existant sur S3.
    new_df a la priorite (updates), l'ancien comble les trous (donnees supprimees par ODRE).
    """
    try:
        old_obj = s3.get_object(Bucket=bucket, Key=key)
        old_df = pd.read_parquet(io.BytesIO(old_obj['Body'].read()))
    except s3.exceptions.NoSuchKey:
        return new_df

    new_keys = set(new_df[merge_key].unique())
    old_only = old_df[~old_df[merge_key].isin(new_keys)]
    print(f"Merge {key}: {len(new_df)} new rows + {len(old_only)} preserved old rows")

    result = pd.concat([new_df, old_only], ignore_index=True)
    return result.sort_values(merge_key).reset_index(drop=True)


def load_source_files(s3, bucket, prefix_in):
    """Lit les 2 fichiers parquet source une seule fois."""
    tr_key = f"{prefix_in}/eco2mix-national-tr.parquet"
    cons_def_key = f"{prefix_in}/eco2mix-national-cons-def.parquet"
    df_tr = pd.read_parquet(io.BytesIO(s3.get_object(Bucket=bucket, Key=tr_key)['Body'].read()))
    df_def = pd.read_parquet(io.BytesIO(s3.get_object(Bucket=bucket, Key=cons_def_key)['Body'].read()))
    print(f"Source loaded: {len(df_tr)} rows (TR), {len(df_def)} rows (CONS_DEF)")
    return df_tr, df_def, tr_key, cons_def_key


def log_sources(s3, bucket, df_tr, df_def, tr_key, cons_def_key):
    """Logue les metadonnees des fichiers source dans logs/download_log.csv."""
    log_entries = []
    for fname, df_src, s3_key in [
        ("eco2mix-national-tr.parquet", df_tr, tr_key),
        ("eco2mix-national-cons-def.parquet", df_def, cons_def_key),
    ]:
        head = s3.head_object(Bucket=bucket, Key=s3_key)
        log_entries.append({
            "file_name": fname,
            "log_datetime": datetime.utcnow().isoformat(),
            "nb_rows": len(df_src),
            "nb_columns": len(df_src.columns),
            "date_min": str(df_src["date_heure"].min()),
            "date_max": str(df_src["date_heure"].max()),
            "file_size_bytes": head["ContentLength"],
        })

    LOG_KEY = "logs/download_log.csv"
    try:
        log_obj = s3.get_object(Bucket=bucket, Key=LOG_KEY)
        df_log = pd.read_csv(io.BytesIO(log_obj['Body'].read()))
    except Exception:
        df_log = pd.DataFrame()

    df_log = pd.concat([df_log, pd.DataFrame(log_entries)], ignore_index=True)
    csv_buffer = io.StringIO()
    df_log.to_csv(csv_buffer, index=False)
    s3.put_object(Bucket=bucket, Key=LOG_KEY, Body=csv_buffer.getvalue())
    print(f"Logged {len(log_entries)} entries to s3://{bucket}/{LOG_KEY}")


def transform_conso(s3, bucket, prefix_out, df_tr_full, df_cons_def_full):
    """Transforme les donnees de consommation et ecrit 3 fichiers parquet."""
    df_tr = df_tr_full[["date_heure", "consommation"]].dropna().copy()
    df_cons_def = df_cons_def_full[["date_heure", "consommation"]].dropna().copy()
    print(f"[conso] df_tr: {len(df_tr)} rows, df_cons_def: {len(df_cons_def)} rows")

    df_tr["date_heure"] = pd.to_datetime(df_tr["date_heure"])
    df_cons_def["date_heure"] = pd.to_datetime(df_cons_def["date_heure"])
    df_tr.drop_duplicates(subset="date_heure", inplace=True)
    df_cons_def.drop_duplicates(subset="date_heure", inplace=True)
    common_dates = pd.merge(df_tr, df_cons_def, on="date_heure", how="inner")["date_heure"]
    print(f"[conso] Common dates: {len(common_dates)}")

    df_tr_unique = df_tr[~df_tr["date_heure"].isin(common_dates)].copy()
    df_tr_unique["source"] = "Real-Time Data"
    df_cons_def_unique = df_cons_def[~df_cons_def["date_heure"].isin(common_dates)].copy()
    df_cons_def_unique["source"] = "Consolidated Data"

    df_result = pd.concat([df_cons_def_unique, df_tr_unique], ignore_index=True)

    df_result = merge_with_existing(s3, bucket, f"{prefix_out}/consommation_france_puissance.parquet", df_result, "date_heure")
    buf = io.BytesIO()
    df_result.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/consommation_france_puissance.parquet")
    print(f"[conso] consommation_france_puissance saved with {len(df_result)} rows.")

    df_result["year"] = df_result["date_heure"].dt.year
    df_result["month"] = df_result["date_heure"].dt.month

    df_monthly_by_source = df_result.groupby(["year", "month", "source"])["consommation"].sum().reset_index()
    df_monthly_by_source["monthly_consumption"] = df_monthly_by_source.apply(
        lambda x: x["consommation"] / 2 if x["source"] == "Consolidated Data" else x["consommation"] / 4,
        axis=1
    )
    df_monthly = df_monthly_by_source.groupby(["year", "month"])["monthly_consumption"].sum().reset_index()
    df_monthly["year_month"] = df_monthly["year"].astype(str) + "-" + df_monthly["month"].astype(str).str.zfill(2)

    df_monthly_out = df_monthly[["year_month", "monthly_consumption"]]
    df_monthly_out = merge_with_existing(s3, bucket, f"{prefix_out}/consommation_mensuelle.parquet", df_monthly_out, "year_month")
    buf = io.BytesIO()
    df_monthly_out.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/consommation_mensuelle.parquet")

    df_yearly = df_monthly.groupby("year")["monthly_consumption"].sum().reset_index()
    df_yearly.rename(columns={"monthly_consumption": "yearly_consumption"}, inplace=True)
    df_yearly = merge_with_existing(s3, bucket, f"{prefix_out}/consommation_annuelle.parquet", df_yearly, "year")
    buf = io.BytesIO()
    df_yearly.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/consommation_annuelle.parquet")
    print(f"[conso] mensuelle + annuelle saved.")


def transform_production(s3, bucket, prefix_out, df_tr_full, df_cons_def_full):
    """Transforme les donnees de production par filiere et ecrit 3 fichiers parquet."""
    PRODUCTION_COLUMNS = [
        "date_heure",
        "nucleaire", "charbon", "gaz", "fioul", "eolien", "solaire", "hydraulique", "bioenergies",
        "gaz_tac", "gaz_cogen", "gaz_ccg", "gaz_autres",
        "fioul_tac", "fioul_cogen", "fioul_autres",
        "hydraulique_fil_eau_eclusee", "hydraulique_lacs", "hydraulique_step_turbinage",
        "bioenergies_dechets", "bioenergies_biomasse", "bioenergies_biogaz",
        "pompage",
    ]

    cols_tr = [col for col in PRODUCTION_COLUMNS if col in df_tr_full.columns]
    cols_cons_def = [col for col in PRODUCTION_COLUMNS if col in df_cons_def_full.columns]

    df_tr = df_tr_full[cols_tr].dropna(subset=["date_heure"]).copy()
    df_cons_def = df_cons_def_full[cols_cons_def].dropna(subset=["date_heure"]).copy()

    for col in [c for c in cols_tr if c != "date_heure"]:
        df_tr[col] = pd.to_numeric(df_tr[col], errors='coerce')
    for col in [c for c in cols_cons_def if c != "date_heure"]:
        df_cons_def[col] = pd.to_numeric(df_cons_def[col], errors='coerce')

    print(f"[production] df_tr: {len(df_tr)} rows, df_cons_def: {len(df_cons_def)} rows")

    df_tr["date_heure"] = pd.to_datetime(df_tr["date_heure"])
    df_cons_def["date_heure"] = pd.to_datetime(df_cons_def["date_heure"])
    df_tr.drop_duplicates(subset="date_heure", inplace=True)
    df_cons_def.drop_duplicates(subset="date_heure", inplace=True)
    common_dates = pd.merge(df_tr, df_cons_def, on="date_heure", how="inner")["date_heure"]
    print(f"[production] Common dates: {len(common_dates)}")

    df_tr_unique = df_tr[~df_tr["date_heure"].isin(common_dates)].copy()
    df_tr_unique["source"] = "Real-Time Data"
    df_cons_def_unique = df_cons_def[~df_cons_def["date_heure"].isin(common_dates)].copy()
    df_cons_def_unique["source"] = "Consolidated Data"

    all_columns = sorted(list(set(df_tr_unique.columns) | set(df_cons_def_unique.columns)))
    for col in all_columns:
        if col not in df_tr_unique.columns:
            df_tr_unique[col] = None
        if col not in df_cons_def_unique.columns:
            df_cons_def_unique[col] = None

    df_result = pd.concat([df_cons_def_unique, df_tr_unique], ignore_index=True)
    df_result = df_result[all_columns]

    main_production_cols = ["nucleaire", "charbon", "gaz", "fioul", "eolien", "solaire", "hydraulique", "bioenergies"]
    cols_to_check = [col for col in main_production_cols if col in df_result.columns]
    df_result = df_result.dropna(subset=cols_to_check, how='all')
    print(f"[production] After NULL filter: {len(df_result)} rows")

    df_result = merge_with_existing(s3, bucket, f"{prefix_out}/production_france_detail.parquet", df_result, "date_heure")
    buf = io.BytesIO()
    df_result.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/production_france_detail.parquet")
    print(f"[production] production_france_detail saved with {len(df_result)} rows.")

    df_result["year"] = df_result["date_heure"].dt.year
    df_result["month"] = df_result["date_heure"].dt.month

    numeric_cols = [col for col in df_result.columns if col not in ["date_heure", "source", "year", "month"]]
    agg_dict = {col: "sum" for col in numeric_cols}
    df_monthly_by_source = df_result.groupby(["year", "month", "source"]).agg(agg_dict).reset_index()

    for col in numeric_cols:
        if col in df_monthly_by_source.columns:
            df_monthly_by_source[f"{col}_mwh"] = df_monthly_by_source.apply(
                lambda x: x[col] / 2 if x["source"] == "Consolidated Data" else x[col] / 4,
                axis=1
            )

    mwh_cols = [f"{col}_mwh" for col in numeric_cols if f"{col}_mwh" in df_monthly_by_source.columns]
    df_monthly = df_monthly_by_source.groupby(["year", "month"]).agg({col: "sum" for col in mwh_cols}).reset_index()
    df_monthly["year_month"] = df_monthly["year"].astype(str) + "-" + df_monthly["month"].astype(str).str.zfill(2)

    df_monthly = merge_with_existing(s3, bucket, f"{prefix_out}/production_mensuelle.parquet", df_monthly, "year_month")
    buf = io.BytesIO()
    df_monthly.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/production_mensuelle.parquet")
    print(f"[production] production_mensuelle saved with {len(df_monthly)} rows.")

    mwh_cols = [col for col in df_monthly.columns if col.endswith("_mwh")]
    df_yearly = df_monthly.groupby("year").agg({col: "sum" for col in mwh_cols}).reset_index()
    df_yearly.rename(columns={col: col.replace("_mwh", "_yearly_mwh") for col in mwh_cols}, inplace=True)

    df_yearly = merge_with_existing(s3, bucket, f"{prefix_out}/production_annuelle.parquet", df_yearly, "year")
    buf = io.BytesIO()
    df_yearly.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/production_annuelle.parquet")
    print(f"[production] production_annuelle saved with {len(df_yearly)} rows.")


def transform_echanges(s3, bucket, prefix_out, df_tr_full, df_cons_def_full):
    """Transforme les donnees d'echanges commerciaux et ecrit 3 fichiers parquet."""
    EXCHANGE_COLUMNS = [
        "date_heure",
        "ech_physiques",
        "ech_comm_angleterre",
        "ech_comm_espagne",
        "ech_comm_italie",
        "ech_comm_suisse",
        "ech_comm_allemagne_belgique",
    ]

    cols_tr = [col for col in EXCHANGE_COLUMNS if col in df_tr_full.columns]
    cols_cons_def = [col for col in EXCHANGE_COLUMNS if col in df_cons_def_full.columns]

    df_tr = df_tr_full[cols_tr].dropna(subset=["date_heure"]).copy()
    df_cons_def = df_cons_def_full[cols_cons_def].dropna(subset=["date_heure"]).copy()

    for col in [c for c in cols_tr if c != "date_heure"]:
        df_tr[col] = pd.to_numeric(df_tr[col], errors='coerce')
    for col in [c for c in cols_cons_def if c != "date_heure"]:
        df_cons_def[col] = pd.to_numeric(df_cons_def[col], errors='coerce')

    print(f"[echanges] df_tr: {len(df_tr)} rows, df_cons_def: {len(df_cons_def)} rows")

    df_tr["date_heure"] = pd.to_datetime(df_tr["date_heure"])
    df_cons_def["date_heure"] = pd.to_datetime(df_cons_def["date_heure"])
    df_tr.drop_duplicates(subset="date_heure", inplace=True)
    df_cons_def.drop_duplicates(subset="date_heure", inplace=True)
    common_dates = pd.merge(df_tr, df_cons_def, on="date_heure", how="inner")["date_heure"]
    print(f"[echanges] Common dates: {len(common_dates)}")

    df_tr_unique = df_tr[~df_tr["date_heure"].isin(common_dates)].copy()
    df_tr_unique["source"] = "Real-Time Data"
    df_cons_def_unique = df_cons_def[~df_cons_def["date_heure"].isin(common_dates)].copy()
    df_cons_def_unique["source"] = "Consolidated Data"

    all_columns = sorted(list(set(df_tr_unique.columns) | set(df_cons_def_unique.columns)))
    for col in all_columns:
        if col not in df_tr_unique.columns:
            df_tr_unique[col] = None
        if col not in df_cons_def_unique.columns:
            df_cons_def_unique[col] = None

    df_result = pd.concat([df_cons_def_unique, df_tr_unique], ignore_index=True)
    df_result = df_result[all_columns]

    exchange_cols_to_check = [col for col in EXCHANGE_COLUMNS if col != "date_heure" and col in df_result.columns]
    df_result = df_result.dropna(subset=exchange_cols_to_check, how='all')
    print(f"[echanges] After NULL filter: {len(df_result)} rows")

    df_result = merge_with_existing(s3, bucket, f"{prefix_out}/echanges_france_detail.parquet", df_result, "date_heure")
    buf = io.BytesIO()
    df_result.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/echanges_france_detail.parquet")
    print(f"[echanges] echanges_france_detail saved with {len(df_result)} rows.")

    df_result["year"] = df_result["date_heure"].dt.year
    df_result["month"] = df_result["date_heure"].dt.month

    numeric_cols = [col for col in df_result.columns if col not in ["date_heure", "source", "year", "month"]]
    agg_dict = {col: "sum" for col in numeric_cols}
    df_monthly_by_source = df_result.groupby(["year", "month", "source"]).agg(agg_dict).reset_index()

    for col in numeric_cols:
        if col in df_monthly_by_source.columns:
            df_monthly_by_source[f"{col}_mwh"] = df_monthly_by_source.apply(
                lambda x: x[col] / 2 if x["source"] == "Consolidated Data" else x[col] / 4,
                axis=1
            )

    mwh_cols = [f"{col}_mwh" for col in numeric_cols if f"{col}_mwh" in df_monthly_by_source.columns]
    df_monthly = df_monthly_by_source.groupby(["year", "month"]).agg({col: "sum" for col in mwh_cols}).reset_index()
    df_monthly["year_month"] = df_monthly["year"].astype(str) + "-" + df_monthly["month"].astype(str).str.zfill(2)

    df_monthly = merge_with_existing(s3, bucket, f"{prefix_out}/echanges_mensuels.parquet", df_monthly, "year_month")
    buf = io.BytesIO()
    df_monthly.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/echanges_mensuels.parquet")
    print(f"[echanges] echanges_mensuels saved with {len(df_monthly)} rows.")

    mwh_cols = [col for col in df_monthly.columns if col.endswith("_mwh")]
    df_yearly = df_monthly.groupby("year").agg({col: "sum" for col in mwh_cols}).reset_index()
    df_yearly.rename(columns={col: col.replace("_mwh", "_yearly_mwh") for col in mwh_cols}, inplace=True)

    df_yearly = merge_with_existing(s3, bucket, f"{prefix_out}/echanges_annuels.parquet", df_yearly, "year")
    buf = io.BytesIO()
    df_yearly.to_parquet(buf, index=False)
    buf.seek(0)
    s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=f"{prefix_out}/echanges_annuels.parquet")
    print(f"[echanges] echanges_annuels saved with {len(df_yearly)} rows.")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    S3_BUCKET = os.environ['BUCKET_NAME']
    S3_PREFIX_IN = '01_downloaded'
    S3_PREFIX_OUT = '02_clean'
    s3 = boto3.client('s3')

    try:
        download_files(s3, S3_BUCKET)

        df_tr_full, df_cons_def_full, tr_key, cons_def_key = load_source_files(s3, S3_BUCKET, S3_PREFIX_IN)
        log_sources(s3, S3_BUCKET, df_tr_full, df_cons_def_full, tr_key, cons_def_key)
        transform_conso(s3, S3_BUCKET, S3_PREFIX_OUT, df_tr_full, df_cons_def_full)
        transform_production(s3, S3_BUCKET, S3_PREFIX_OUT, df_tr_full, df_cons_def_full)
        transform_echanges(s3, S3_BUCKET, S3_PREFIX_OUT, df_tr_full, df_cons_def_full)

        return {
            'statusCode': 200,
            'body': f"All steps completed. Files in s3://{S3_BUCKET}/{S3_PREFIX_OUT}/"
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f"Error: {str(e)}"
        }
