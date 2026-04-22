import os
import io
import requests
import boto3
import pandas as pd

PMAX_URL = "https://d1bn3skqiiw1jp.cloudfront.net/pmax"
OUT_KEY = "02_clean/rte_pmax.parquet"


def lambda_handler(event, context):
    bucket = os.environ["BUCKET_NAME"]
    s3 = boto3.client("s3")
    try:
        print(f"INFO: Fetching {PMAX_URL}")
        resp = requests.get(PMAX_URL, timeout=30)
        resp.raise_for_status()
        df = pd.DataFrame(resp.json())
        df = df.rename(columns={"pmax": "pmax_mw"})
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
