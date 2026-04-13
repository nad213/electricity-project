import os
import io
import json
import boto3
import pandas as pd
import urllib.request

SYNTHESE_URL = "https://analysesetdonnees.rte-france.com/production/synthese"
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


def build_production_dataframes(blob):
    """Builds monthly and yearly production DataFrames from a production JSON blob."""
    monthly_rows, yearly_rows = [], []
    for key, fdata in blob.items():
        if not isinstance(fdata, dict):
            continue
        label = fdata.get("name") or key.split("_", 1)[-1]
        inner = _get_inner(fdata)
        for year_str, months in inner.get("monthlyData", {}).items():
            if not isinstance(months, dict):
                continue
            for month_str, value in months.items():
                monthly_rows.append({
                    "date": f"{year_str}-{month_str.zfill(2)}",
                    "filiere": label,
                    "valeur_mwh": float(value) * 1_000_000 if value is not None else None,
                })
        for year_str, value in inner.get("yearlyData", {}).items():
            if value is not None:
                yearly_rows.append({
                    "annee": int(year_str),
                    "filiere": label,
                    "valeur_mwh": float(value) * 1_000_000,
                })
    df_m = (
        pd.DataFrame(monthly_rows).sort_values(["date", "filiere"]).reset_index(drop=True)
        if monthly_rows else pd.DataFrame(columns=["date", "filiere", "valeur_mwh"])
    )
    df_y = (
        pd.DataFrame(yearly_rows).sort_values(["annee", "filiere"]).reset_index(drop=True)
        if yearly_rows else pd.DataFrame(columns=["annee", "filiere", "valeur_mwh"])
    )
    return df_m, df_y


def build_parc_installe_dataframe(blob):
    """Builds a quarterly installed capacity DataFrame (GW)."""
    rows = []
    for key, fdata in blob.items():
        if not isinstance(fdata, dict):
            continue
        label = fdata.get("name") or key.split("_", 1)[-1]
        inner = _get_inner(fdata)
        quarterly = inner.get("quarterlyData", {})
        # Structure: {T1: {year: val}, ...} ou {year: {T1: val}, ...}
        first_key = next(iter(quarterly), None)
        if first_key and str(first_key).startswith("T"):
            # Clé externe = trimestre, clé interne = année
            for trimestre, years_dict in quarterly.items():
                if not isinstance(years_dict, dict):
                    continue
                for year_str, value in years_dict.items():
                    if value is not None:
                        rows.append({
                            "annee": int(year_str),
                            "trimestre": trimestre,
                            "filiere": label,
                            "valeur_gw": float(value),
                        })
        else:
            # Clé externe = année, clé interne = trimestre
            for year_str, quarters_dict in quarterly.items():
                if not isinstance(quarters_dict, dict):
                    continue
                for trimestre, value in quarters_dict.items():
                    if value is not None:
                        rows.append({
                            "annee": int(year_str),
                            "trimestre": trimestre,
                            "filiere": label,
                            "valeur_gw": float(value),
                        })
    return (
        pd.DataFrame(rows).sort_values(["annee", "trimestre", "filiere"]).reset_index(drop=True)
        if rows else pd.DataFrame(columns=["annee", "trimestre", "filiere", "valeur_gw"])
    )


def build_facteur_charge_dataframes(blob):
    """Builds monthly and yearly capacity factor DataFrames (%)."""
    monthly_rows, yearly_rows = [], []
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
                    monthly_rows.append({
                        "date": f"{year_str}-{month_str.zfill(2)}",
                        "type": label,
                        "facteur_charge_pct": float(value),
                    })
        for year_str, value in inner.get("yearlyData", {}).items():
            if value is not None:
                yearly_rows.append({
                    "annee": int(year_str),
                    "type": label,
                    "facteur_charge_pct": float(value),
                })
    df_m = (
        pd.DataFrame(monthly_rows).sort_values(["date", "type"]).reset_index(drop=True)
        if monthly_rows else pd.DataFrame(columns=["date", "type", "facteur_charge_pct"])
    )
    df_y = (
        pd.DataFrame(yearly_rows).sort_values(["annee", "type"]).reset_index(drop=True)
        if yearly_rows else pd.DataFrame(columns=["annee", "type", "facteur_charge_pct"])
    )
    return df_m, df_y


def _find_blob(blobs, key_prefix=None, key_contains=None):
    """Finds the first blob whose keys match the given criteria."""
    for blob in blobs:
        keys = list(blob.keys())
        if key_prefix is not None and any(k.startswith(key_prefix) for k in keys):
            return blob
        if key_contains is not None and any(key_contains.lower() in k.lower() for k in keys):
            return blob
    return None


def _has_quarterly(blob):
    """Returns True if any entry in the blob contains quarterlyData."""
    for fdata in blob.values():
        if not isinstance(fdata, dict):
            continue
        if "quarterlyData" in _get_inner(fdata):
            return True
    return False


def lambda_handler(event, context):
    S3_BUCKET = os.environ["BUCKET_NAME"]
    s3 = boto3.client("s3")
    uploads = []

    try:
        # --- Synthèse (toutes filières, agrégé) ---
        print(f"Fetching {SYNTHESE_URL}")
        synthese_blobs = fetch_all_page_json(SYNTHESE_URL)
        synthese_blob = synthese_blobs[0] if synthese_blobs else {}
        print(f"Synthèse: {len(synthese_blob)} filières: {list(synthese_blob.keys())}")
        df_m, df_y = build_production_dataframes(synthese_blob)
        uploads += [
            ("01_downloaded/portail_analyse_et_donnees/rte_production_mensuelle.parquet", df_m),
            ("01_downloaded/portail_analyse_et_donnees/rte_production_annuelle.parquet", df_y),
        ]

        # --- Éolien ---
        print(f"Fetching {EOLIEN_URL}")
        eolien_blobs = fetch_all_page_json(EOLIEN_URL)
        print(f"Éolien: {len(eolien_blobs)} blobs, clés: {[list(b.keys())[:3] for b in eolien_blobs]}")

        eol_prod = _find_blob(eolien_blobs, key_prefix="01_Eolien")
        if eol_prod:
            df_m, df_y = build_production_dataframes(eol_prod)
            uploads += [
                ("01_downloaded/portail_analyse_et_donnees/rte_eolien_production_mensuelle.parquet", df_m),
                ("01_downloaded/portail_analyse_et_donnees/rte_eolien_production_annuelle.parquet", df_y),
            ]

        eol_parc = next((b for b in eolien_blobs if b is not eol_prod and _has_quarterly(b)), None)
        if eol_parc:
            df = build_parc_installe_dataframe(eol_parc)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_eolien_parc_installe.parquet", df))

        eol_fc = _find_blob(eolien_blobs, key_contains="facteur")
        if eol_fc:
            # Les noms ("Facteur de charge max/moyen") sont génériques — on utilise les clés
            # pour conserver la distinction terrestre/en mer
            eol_fc_keyed = {k.split("_", 1)[-1]: {**v, "name": None} for k, v in eol_fc.items() if isinstance(v, dict)}
            df_m, _ = build_facteur_charge_dataframes(eol_fc_keyed)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_eolien_facteur_charge_mensuel.parquet", df_m))

        # --- Solaire ---
        print(f"Fetching {SOLAIRE_URL}")
        solaire_blobs = fetch_all_page_json(SOLAIRE_URL)
        print(f"Solaire: {len(solaire_blobs)} blobs, clés: {[list(b.keys())[:3] for b in solaire_blobs]}")

        sol_prod = _find_blob(solaire_blobs, key_prefix="01_Solaire")
        if sol_prod:
            df_m, df_y = build_production_dataframes(sol_prod)
            uploads += [
                ("01_downloaded/portail_analyse_et_donnees/rte_solaire_production_mensuelle.parquet", df_m),
                ("01_downloaded/portail_analyse_et_donnees/rte_solaire_production_annuelle.parquet", df_y),
            ]

        sol_parc = next((b for b in solaire_blobs if b is not sol_prod and _has_quarterly(b)), None)
        if sol_parc:
            df = build_parc_installe_dataframe(sol_parc)
            uploads.append(("01_downloaded/portail_analyse_et_donnees/rte_solaire_parc_installe.parquet", df))

        sol_fc = _find_blob(solaire_blobs, key_contains="facteur")
        if sol_fc:
            df_m, df_y = build_facteur_charge_dataframes(sol_fc)
            uploads += [
                ("01_downloaded/portail_analyse_et_donnees/rte_solaire_facteur_charge_mensuel.parquet", df_m),
                ("01_downloaded/portail_analyse_et_donnees/rte_solaire_facteur_charge_annuel.parquet", df_y),
            ]

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
