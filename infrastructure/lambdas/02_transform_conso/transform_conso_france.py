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

    try:
        # 1. Download files from S3
        tr_key = f"{S3_PREFIX_IN}/eco2mix-national-tr.parquet"
        cons_def_key = f"{S3_PREFIX_IN}/eco2mix-national-cons-def.parquet"
        tr_obj = s3.get_object(Bucket=S3_BUCKET, Key=tr_key)
        cons_def_obj = s3.get_object(Bucket=S3_BUCKET, Key=cons_def_key)
        df_tr_full = pd.read_parquet(io.BytesIO(tr_obj['Body'].read()))
        df_cons_def_full = pd.read_parquet(io.BytesIO(cons_def_obj['Body'].read()))

        # --- Logging des fichiers source ---
        log_entries = []
        for fname, df_src, s3_key in [
            ("eco2mix-national-tr.parquet", df_tr_full, tr_key),
            ("eco2mix-national-cons-def.parquet", df_cons_def_full, cons_def_key),
        ]:
            head = s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
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
            log_obj = s3.get_object(Bucket=S3_BUCKET, Key=LOG_KEY)
            df_log = pd.read_csv(io.BytesIO(log_obj['Body'].read()))
        except Exception:
            df_log = pd.DataFrame()

        df_log = pd.concat([df_log, pd.DataFrame(log_entries)], ignore_index=True)
        csv_buffer = io.StringIO()
        df_log.to_csv(csv_buffer, index=False)
        s3.put_object(Bucket=S3_BUCKET, Key=LOG_KEY, Body=csv_buffer.getvalue())
        print(f"Logged {len(log_entries)} entries to s3://{S3_BUCKET}/{LOG_KEY}")

        df_tr = df_tr_full[["date_heure", "consommation"]].dropna()
        df_cons_def = df_cons_def_full[["date_heure", "consommation"]].dropna()
        print(f"Size of df_tr after loading: {len(df_tr)}")
        print(f"Size of df_cons_def after loading: {len(df_cons_def)}")

        # 2. Cleaning and transformation
        df_tr["date_heure"] = pd.to_datetime(df_tr["date_heure"])
        df_cons_def["date_heure"] = pd.to_datetime(df_cons_def["date_heure"])
        df_tr.drop_duplicates(subset="date_heure", inplace=True)
        df_cons_def.drop_duplicates(subset="date_heure", inplace=True)
        common_dates = pd.merge(df_tr, df_cons_def, on="date_heure", how="inner")["date_heure"]
        print(f"Number of common dates: {len(common_dates)}")

        df_tr_unique = df_tr[~df_tr["date_heure"].isin(common_dates)]
        df_tr_unique["source"] = "Real-Time Data"
        df_cons_def_unique = df_cons_def[~df_cons_def["date_heure"].isin(common_dates)]
        df_cons_def_unique["source"] = "Consolidated Data"
        print(f"Size of df_tr_unique: {len(df_tr_unique)}")
        print(f"Size of df_cons_def_unique: {len(df_cons_def_unique)}")

        df_result = pd.concat([df_cons_def_unique, df_tr_unique], ignore_index=True)

        # Save df_result
        result_buffer = io.BytesIO()
        df_result.to_parquet(result_buffer, index=False)
        result_buffer.seek(0)
        s3.upload_fileobj(
            Fileobj=result_buffer,
            Bucket=S3_BUCKET,
            Key=f"{S3_PREFIX_OUT}/consommation_france_puissance.parquet"
        )
        print(f"File consommation_france_puissance saved with {len(df_result)} rows.")
        print(f"Size of df_result: {len(df_result)}")

        df_result["year"] = df_result["date_heure"].dt.year
        df_result["month"] = df_result["date_heure"].dt.month
        df_monthly = df_result.groupby(["year", "month", "source"])["consommation"].sum().reset_index()
        df_monthly["monthly_consumption"] = df_monthly.apply(
            lambda x: x["consommation"] / 2 if x["source"] == "Consolidated Data" else x["consommation"] / 4,
            axis=1
        )
        df_monthly["year_month"] = df_monthly["year"].astype(str) + "-" + df_monthly["month"].astype(str).str.zfill(2)

        # 3. Save results to S3
        monthly_buffer = io.BytesIO()
        df_monthly[["year_month", "monthly_consumption"]].to_parquet(monthly_buffer, index=False)
        monthly_buffer.seek(0)
        s3.upload_fileobj(
            Fileobj=monthly_buffer,
            Bucket=S3_BUCKET,
            Key=f"{S3_PREFIX_OUT}/consommation_mensuelle.parquet"
        )

        df_yearly = df_monthly.groupby("year")["monthly_consumption"].sum().reset_index()
        df_yearly.rename(columns={"monthly_consumption": "yearly_consumption"}, inplace=True)
        yearly_buffer = io.BytesIO()
        df_yearly.to_parquet(yearly_buffer, index=False)
        yearly_buffer.seek(0)
        s3.upload_fileobj(
            Fileobj=yearly_buffer,
            Bucket=S3_BUCKET,
            Key=f"{S3_PREFIX_OUT}/consommation_annuelle.parquet"
        )

        return {
            'statusCode': 200,
            'body': f"Processing completed. Files saved in s3://{S3_BUCKET}/{S3_PREFIX_OUT}/"
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f"Error during processing: {str(e)}"
        }
