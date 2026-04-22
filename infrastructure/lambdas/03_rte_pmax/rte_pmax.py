import os
import io
import requests
import boto3
import pandas as pd

PMAX_URL = "https://d1bn3skqiiw1jp.cloudfront.net/pmax"
OUT_KEY = "02_clean/rte_pmax.parquet"

CATEGORY_FR = {
    "HYDRAULICS": "Hydraulique fil de l'eau",
    "HYDRO_PUMPED_STORAGE": "Hydraulique STEP",
    "HYDRO_WATER_RESERVOIR": "Hydraulique lacs",
    "BIOMASS": "Bioénergies",
    "FOSSIL_GAS": "Gaz",
    "FOSSIL_HARD_COAL": "Charbon",
    "FOSSIL_OIL": "Fioul",
    "WIND": "Éolien",
    "TIDAL": "Énergies marines",
    "NUCLEAR": "Nucléaire",
    "SOLAR": "Solaire",
    "ALL": "Total",
}

HYDRO_CATEGORIES = {"HYDRAULICS", "HYDRO_PUMPED_STORAGE", "HYDRO_WATER_RESERVOIR"}


def lambda_handler(event, context):
    bucket = os.environ["BUCKET_NAME"]
    s3 = boto3.client("s3")
    try:
        print(f"INFO: Fetching {PMAX_URL}")
        resp = requests.get(PMAX_URL, timeout=30)
        resp.raise_for_status()
        raw = pd.DataFrame(resp.json())

        hydro_sum = int(raw.loc[raw["productionCategory"].isin(HYDRO_CATEGORIES), "pmax"].sum())

        df = raw.copy()
        df["filiere"] = df["productionCategory"].map(CATEGORY_FR)
        df = df.rename(columns={"pmax": "puissance_max_mw"})[["filiere", "puissance_max_mw"]]

        hydro_total = pd.DataFrame([{"filiere": "Hydraulique (total)", "puissance_max_mw": hydro_sum}])
        df = pd.concat([df, hydro_total], ignore_index=True)

        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        s3.upload_fileobj(Fileobj=buf, Bucket=bucket, Key=OUT_KEY)
        print(f"SUCCESS: s3://{bucket}/{OUT_KEY} ({len(df)} rows)")
        return {"statusCode": 200, "body": f"{len(df)} rows"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"statusCode": 500, "body": str(e)}
