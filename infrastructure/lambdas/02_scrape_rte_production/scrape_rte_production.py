import os
import io
import json
import boto3
import pandas as pd
import urllib.request

EOLIEN_URL = "https://analysesetdonnees.rte-france.com/production/eolien"
SOLAIRE_URL = "https://analysesetdonnees.rte-france.com/production/solaire"


def fetch_all_page_json(url):
    """Fetches a page and returns all non-trivial embedded JSON.parse('...') datasets."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8")

    results = []
    marker = "JSON.parse('"
    pos = 0
    while True:
        idx = html.find(marker, pos)
        if idx == -1:
            break
        idx += len(marker)
        chars = []
        i = idx
        while i < len(html):
            if html[i] == "'" and html[i - 1] != "\\":
                break
            chars.append(html[i])
            i += 1
        raw_json = "".join(chars).replace("\\'", "'")
        pos = i + 1
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and parsed:
                results.append(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    return results


def _get_inner(fdata):
    """Returns inner data dict, handling both data.filiere and data.global."""
    data = fdata.get("data", {})
    return data.get("filiere") or data.get("global") or {}


def build_production_mensuelle(blob):
    """Builds monthly production DataFrame from a production JSON blob."""
    rows = []
    for key, fdata in blob.items():
        if not isinstance(fdata, dict):
            continue
        label = fdata.get("name") or key.split("_", 1)[-1]
        inner = _get_inner(fdata)
        for year_str, months in inner.get("monthlyData", {}).items():
            if not isinstance(months, dict):
                continue
            for month_str, value in months.items():
                rows.append({
                    "date": f"{year_str}-{month_str.zfill(2)}",
                    "filiere": label,
                    "valeur_mwh": float(value) * 1_000_000 if value is not None else None,
                })
    return (
        pd.DataFrame(rows).sort_values(["date", "filiere"]).reset_index(drop=True)
        if rows else pd.DataFrame(columns=["date", "filiere", "valeur_mwh"])
    )


def build_facteur_charge_mensuel(blob):
    """Builds monthly capacity factor DataFrame (%)."""
    rows = []
    for key, fdata in blob.items():
        if not isinstance(fdata, dict):
            continue
        label = fdata.get("name") or key
        inner = _get_inner(fdata)
        for year_str, months in inner.get("monthlyData", {}).items():
            if not isinstance(months, dict):
                continue
            for month_str, value in months.items():
                if value is not None:
                    rows.append({
                        "date": f"{year_str}-{month_str.zfill(2)}",
                        "type": label,
                        "facteur_charge_pct": float(value),
                    })
    return (
        pd.DataFrame(rows).sort_values(["date", "type"]).reset_index(drop=True)
        if rows else pd.DataFrame(columns=["date", "type", "facteur_charge_pct"])
    )


def _find_blob(blobs, key_prefix=None, key_contains=None):
    """Finds the first blob whose keys match the given criteria."""
    for blob in blobs:
        keys = list(blob.keys())
        if key_prefix is not None and any(k.startswith(key_prefix) for k in keys):
            return blob
        if key_contains is not None and any(key_contains.lower() in k.lower() for k in keys):
            return blob
    return None


def lambda_handler(event, context):
    S3_BUCKET = os.environ["BUCKET_NAME"]
    s3 = boto3.client("s3")
    uploads = []

    try:
        # --- Éolien ---
        print(f"Fetching {EOLIEN_URL}")
        eolien_blobs = fetch_all_page_json(EOLIEN_URL)
        print(f"Éolien: {len(eolien_blobs)} blobs, clés: {[list(b.keys())[:3] for b in eolien_blobs]}")

        eol_prod = _find_blob(eolien_blobs, key_prefix="01_Eolien")
        if eol_prod:
            df = build_production_mensuelle(eol_prod)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_eolien_production_mensuelle.parquet", df))

        eol_fc = _find_blob(eolien_blobs, key_contains="facteur")
        if eol_fc:
            # Les noms ("Facteur de charge max/moyen") sont génériques — on utilise les clés
            # pour conserver la distinction terrestre/en mer
            eol_fc_keyed = {k.split("_", 1)[-1]: {**v, "name": None} for k, v in eol_fc.items() if isinstance(v, dict)}
            df = build_facteur_charge_mensuel(eol_fc_keyed)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_eolien_facteur_charge_mensuel.parquet", df))

        # --- Solaire ---
        print(f"Fetching {SOLAIRE_URL}")
        solaire_blobs = fetch_all_page_json(SOLAIRE_URL)
        print(f"Solaire: {len(solaire_blobs)} blobs, clés: {[list(b.keys())[:3] for b in solaire_blobs]}")

        sol_prod = _find_blob(solaire_blobs, key_prefix="01_Solaire")
        if sol_prod:
            df = build_production_mensuelle(sol_prod)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_solaire_production_mensuelle.parquet", df))

        sol_fc = _find_blob(solaire_blobs, key_contains="facteur")
        if sol_fc:
            df = build_facteur_charge_mensuel(sol_fc)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_solaire_facteur_charge_mensuel.parquet", df))

        # --- Upload S3 ---
        saved = []
        for s3_key, df in uploads:
            if df is not None and len(df) > 0:
                buf = io.BytesIO()
                df.to_parquet(buf, index=False)
                buf.seek(0)
                s3.upload_fileobj(Fileobj=buf, Bucket=S3_BUCKET, Key=s3_key)
                print(f"Saved {s3_key} ({len(df)} rows)")
                saved.append(f"{s3_key.split('/')[-1]}: {len(df)}")

        return {"statusCode": 200, "body": "Done. " + " | ".join(saved)}

    except Exception as e:
        import traceback
        print(f"ERROR: {e}\n{traceback.format_exc()}")
        return {"statusCode": 500, "body": str(e)}
