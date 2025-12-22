import os
import io
import pandas as pd
import boto3
from datetime import datetime

def lambda_handler(event, context):
    S3_BUCKET = os.environ['BUCKET_NAME']
    S3_PREFIX_IN = '01_downloaded'
    S3_PREFIX_OUT = '02_clean'
    s3 = boto3.client('s3')

    # Colonnes de production à extraire
    PRODUCTION_COLUMNS = [
        "date_heure",
        # Énergies principales
        "nucleaire",
        "charbon",
        "gaz",
        "fioul",
        "eolien",
        "solaire",
        "hydraulique",
        "bioenergies",
        # Détails gaz
        "gaz_tac",
        "gaz_cogen",
        "gaz_ccg",
        "gaz_autres",
        # Détails fioul
        "fioul_tac",
        "fioul_cogen",
        "fioul_autres",
        # Détails hydraulique
        "hydraulique_fil_eau_eclusee",
        "hydraulique_lacs",
        "hydraulique_step_turbinage",
        # Détails bioénergies
        "bioenergies_dechets",
        "bioenergies_biomasse",
        "bioenergies_biogaz",
        # Pompage et stockage
        "pompage",
    ]

    try:
        # 1. Download files from S3
        tr_key = f"{S3_PREFIX_IN}/eco2mix-national-tr.parquet"
        cons_def_key = f"{S3_PREFIX_IN}/eco2mix-national-cons-def.parquet"
        tr_obj = s3.get_object(Bucket=S3_BUCKET, Key=tr_key)
        cons_def_obj = s3.get_object(Bucket=S3_BUCKET, Key=cons_def_key)

        # Charger les dataframes et sélectionner les colonnes disponibles
        df_tr_full = pd.read_parquet(io.BytesIO(tr_obj['Body'].read()))
        df_cons_def_full = pd.read_parquet(io.BytesIO(cons_def_obj['Body'].read()))

        # Sélectionner uniquement les colonnes qui existent dans chaque fichier
        cols_tr = [col for col in PRODUCTION_COLUMNS if col in df_tr_full.columns]
        cols_cons_def = [col for col in PRODUCTION_COLUMNS if col in df_cons_def_full.columns]

        df_tr = df_tr_full[cols_tr].dropna(subset=["date_heure"]).copy()
        df_cons_def = df_cons_def_full[cols_cons_def].dropna(subset=["date_heure"]).copy()

        # Convertir les colonnes numériques en float pour gérer les NaN correctement
        numeric_cols_tr = [col for col in cols_tr if col != "date_heure"]
        numeric_cols_cons_def = [col for col in cols_cons_def if col != "date_heure"]

        for col in numeric_cols_tr:
            df_tr[col] = pd.to_numeric(df_tr[col], errors='coerce')
        for col in numeric_cols_cons_def:
            df_cons_def[col] = pd.to_numeric(df_cons_def[col], errors='coerce')

        print(f"Size of df_tr after loading: {len(df_tr)}")
        print(f"Size of df_cons_def after loading: {len(df_cons_def)}")
        print(f"Columns in df_tr: {cols_tr}")
        print(f"Columns in df_cons_def: {cols_cons_def}")

        # 2. Cleaning and transformation
        df_tr["date_heure"] = pd.to_datetime(df_tr["date_heure"])
        df_cons_def["date_heure"] = pd.to_datetime(df_cons_def["date_heure"])
        df_tr.drop_duplicates(subset="date_heure", inplace=True)
        df_cons_def.drop_duplicates(subset="date_heure", inplace=True)

        # Identifier les dates communes
        common_dates = pd.merge(df_tr, df_cons_def, on="date_heure", how="inner")["date_heure"]
        print(f"Number of common dates: {len(common_dates)}")

        # Garder uniquement les dates uniques de chaque source
        df_tr_unique = df_tr[~df_tr["date_heure"].isin(common_dates)].copy()
        df_tr_unique["source"] = "Real-Time Data"
        df_cons_def_unique = df_cons_def[~df_cons_def["date_heure"].isin(common_dates)].copy()
        df_cons_def_unique["source"] = "Consolidated Data"
        print(f"Size of df_tr_unique: {len(df_tr_unique)}")
        print(f"Size of df_cons_def_unique: {len(df_cons_def_unique)}")

        # Fusionner les deux sources
        # Aligner les colonnes avant concat
        all_columns = sorted(list(set(df_tr_unique.columns) | set(df_cons_def_unique.columns)))
        for col in all_columns:
            if col not in df_tr_unique.columns:
                df_tr_unique[col] = None
            if col not in df_cons_def_unique.columns:
                df_cons_def_unique[col] = None

        df_result = pd.concat([df_cons_def_unique, df_tr_unique], ignore_index=True)
        df_result = df_result[all_columns]  # Réordonner les colonnes

        # 3. Sauvegarder le fichier principal avec toutes les données
        result_buffer = io.BytesIO()
        df_result.to_parquet(result_buffer, index=False)
        result_buffer.seek(0)
        s3.upload_fileobj(
            Fileobj=result_buffer,
            Bucket=S3_BUCKET,
            Key=f"{S3_PREFIX_OUT}/production_france_detail.parquet"
        )
        print(f"File production_france_detail saved with {len(df_result)} rows.")

        # 4. Créer des agrégations mensuelles et annuelles
        df_result["year"] = df_result["date_heure"].dt.year
        df_result["month"] = df_result["date_heure"].dt.month

        # Colonnes numériques à agréger (exclure date_heure, source, year, month)
        numeric_cols = [col for col in df_result.columns
                       if col not in ["date_heure", "source", "year", "month"]]

        # Agrégation mensuelle
        agg_dict = {col: "sum" for col in numeric_cols}
        df_monthly = df_result.groupby(["year", "month"]).agg(agg_dict).reset_index()

        # Conversion en MWh (énergie) selon la source
        # Données consolidées: points toutes les 30 min (division par 2)
        # Données temps réel: points toutes les 15 min (division par 4)
        # Simplification: on divise par 2 (approximation moyenne)
        for col in numeric_cols:
            if col in df_monthly.columns:
                df_monthly[f"{col}_mwh"] = df_monthly[col] / 2

        df_monthly["year_month"] = df_monthly["year"].astype(str) + "-" + df_monthly["month"].astype(str).str.zfill(2)

        # Sauvegarder l'agrégation mensuelle
        monthly_buffer = io.BytesIO()
        df_monthly.to_parquet(monthly_buffer, index=False)
        monthly_buffer.seek(0)
        s3.upload_fileobj(
            Fileobj=monthly_buffer,
            Bucket=S3_BUCKET,
            Key=f"{S3_PREFIX_OUT}/production_mensuelle.parquet"
        )
        print(f"File production_mensuelle saved with {len(df_monthly)} rows.")

        # Agrégation annuelle
        mwh_cols = [col for col in df_monthly.columns if col.endswith("_mwh")]
        agg_dict_yearly = {col: "sum" for col in mwh_cols}
        df_yearly = df_monthly.groupby("year").agg(agg_dict_yearly).reset_index()

        # Renommer les colonnes (enlever _mwh du nom)
        rename_dict = {col: col.replace("_mwh", "_yearly_mwh") for col in mwh_cols}
        df_yearly.rename(columns=rename_dict, inplace=True)

        yearly_buffer = io.BytesIO()
        df_yearly.to_parquet(yearly_buffer, index=False)
        yearly_buffer.seek(0)
        s3.upload_fileobj(
            Fileobj=yearly_buffer,
            Bucket=S3_BUCKET,
            Key=f"{S3_PREFIX_OUT}/production_annuelle.parquet"
        )
        print(f"File production_annuelle saved with {len(df_yearly)} rows.")

        return {
            'statusCode': 200,
            'body': f"Processing completed. Files saved in s3://{S3_BUCKET}/{S3_PREFIX_OUT}/"
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f"Error during processing: {str(e)}"
        }
