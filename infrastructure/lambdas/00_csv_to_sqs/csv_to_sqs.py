import boto3
import os
import csv
import json
import urllib.request

s3 = boto3.client('s3')
sqs = boto3.client('sqs')

CATALOG_API = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"


def get_data_processed(dataset_id):
    """Fetch the data_processed timestamp from the OpenDataSoft catalog API."""
    url = f"{CATALOG_API}?where=dataset_id%3D%27{dataset_id}%27&limit=1"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['results'][0]['metas']['default']['data_processed']


def get_stored_data_processed(bucket_name, file_name):
    """Read the data_processed metadata from the existing S3 object, or None if missing."""
    try:
        head = s3.head_object(Bucket=bucket_name, Key=f"01_downloaded/{file_name}")
        return head.get('Metadata', {}).get('data_processed')
    except s3.exceptions.ClientError:
        return None


def lambda_handler(event, context):
    bucket_name = os.environ['BUCKET_NAME']
    queue_url = os.environ['QUEUE_URL']
    file_key = '99_params/filelist.csv'

    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    csv_content = response['Body'].read().decode('utf-8').splitlines()

    sent_messages = []
    skipped = []
    for line in csv.DictReader(csv_content):
        dataset_id = line['dataset_id']
        base_url = f"{CATALOG_API}"
        url = f"{base_url}{dataset_id}/exports/parquet?lang=fr&timezone=Europe%2FBerlin"
        file_name = f"{dataset_id}.parquet"

        # Check if dataset has been updated since last download
        try:
            remote_data_processed = get_data_processed(dataset_id)
            stored_data_processed = get_stored_data_processed(bucket_name, file_name)

            if remote_data_processed and remote_data_processed == stored_data_processed:
                print(f"SKIP: {dataset_id} unchanged (data_processed={remote_data_processed})")
                skipped.append({"dataset_id": dataset_id, "data_processed": remote_data_processed})
                continue
            else:
                print(f"DOWNLOAD: {dataset_id} changed (remote={remote_data_processed}, stored={stored_data_processed})")
        except Exception as e:
            print(f"WARNING: Could not check data_processed for {dataset_id}: {e}. Downloading anyway.")
            remote_data_processed = None

        message_body = {
            "url": url,
            "file_name": file_name,
            "step": "process_file",
            "data_processed": remote_data_processed
        }
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageAttributes={
                'file_name': {
                    'StringValue': file_name,
                    'DataType': 'String'
                }
            }
        )
        sent_messages.append({"url": url, "file_name": file_name})

    return {
        'statusCode': 200,
        'body': f"Sent {len(sent_messages)} messages to SQS, skipped {len(skipped)}.",
        'files': sent_messages,
        'skipped': skipped
    }
