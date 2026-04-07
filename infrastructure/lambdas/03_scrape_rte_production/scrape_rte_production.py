import os
import io
import json
import boto3
import pandas as pd
import urllib.request
from datetime import datetime

PAGE_URL = "https://analysesetdonnees.rte-france.com/production/synthese"

FILIERE_LABELS = {
    "Nucleaire": "Nucléaire",
    "Hydraulique": "Hydraulique",
    "Eolien": "Éolien",
    "Solaire": "Solaire",
    "Thermique": "Thermique",
    "Bioenergies": "Bioénergies",
}


def fetch_page_json():
    """Fetches the RTE production page and extracts the embedded JSON dataset."""
    req = urllib.request.Request(
        PAGE_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8")

    marker = "JSON.parse('"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError(f"Could not find '{marker}' in page HTML")
    idx += len(marker)

    chars = []
    i = idx
    while i < len(html):
        if html[i] == "'" and html[i - 1] != "\\":
            break
        chars.append(html[i])
        i += 1

    raw_json = "".join(chars).replace("\\'", "'")
    return json.loads(raw_json)


def build_dataframes(data):
    """Flattens the nested JSON into monthly and yearly DataFrames."""
    monthly_rows = []
    yearly_rows = []

    for filiere_key, fdata in data.items():
        # Display name is available directly in 'name'
        label = fdata.get("name") or filiere_key.split("_", 1)[-1]
        data_status = fdata.get("dataStatus", {})
        uncompleted_year = fdata.get("uncompletedYear", {})

        inner = fdata.get("data", {}).get("filiere", {})

        for year_str, months in inner.get("monthlyData", {}).items():
            for month_str, value in months.items():
                # Get nature from dataStatus[year][month]['statut']
                month_entry = data_status.get(year_str, {}).get(month_str.zfill(2), {})
                statut = month_entry.get("statut", "") if isinstance(month_entry, dict) else ""
                if statut == "definitive":
                    nature = "Données Consolidées"
                elif statut:
                    nature = "Données Provisoires"
                else:
                    # Fallback: uncompleted years are provisional
                    is_uncompleted = uncompleted_year.get(year_str, False) if isinstance(uncompleted_year, dict) else False
                    nature = "Données Provisoires" if is_uncompleted else "Données Consolidées"

                monthly_rows.append({
                    "date": f"{year_str}-{month_str.zfill(2)}",
                    "filiere": label,
                    "valeur_twh": float(value) if value is not None else None,
                    "nature": nature,
                })

        for year_str, value in inner.get("yearlyData", {}).items():
            yearly_rows.append({
                "annee": int(year_str),
                "filiere": label,
                "valeur_twh": float(value) if value is not None else None,
            })

    df_monthly = pd.DataFrame(monthly_rows).sort_values(["date", "filiere"]).reset_index(drop=True)
    df_yearly = pd.DataFrame(yearly_rows).sort_values(["annee", "filiere"]).reset_index(drop=True)
    return df_monthly, df_yearly


def lambda_handler(event, context):
    S3_BUCKET = os.environ["BUCKET_NAME"]
    s3 = boto3.client("s3")

    try:
        print(f"Fetching {PAGE_URL}")
        data = fetch_page_json()
        print(f"Found {len(data)} filières: {list(data.keys())}")

        df_monthly, df_yearly = build_dataframes(data)
        print(f"Monthly: {len(df_monthly)} rows | Yearly: {len(df_yearly)} rows")

        for key, df in [
            ("02_clean/rte_production_mensuelle.parquet", df_monthly),
            ("02_clean/rte_production_annuelle.parquet", df_yearly),
        ]:
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            buf.seek(0)
            s3.upload_fileobj(Fileobj=buf, Bucket=S3_BUCKET, Key=key)
            print(f"Saved {key} ({len(df)} rows)")

        return {
            "statusCode": 200,
            "body": f"Done. Monthly: {len(df_monthly)} rows, Yearly: {len(df_yearly)} rows.",
        }

    except Exception as e:
        print(f"ERROR: {e}")
        return {"statusCode": 500, "body": str(e)}
