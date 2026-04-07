import os
import json
import requests
import boto3
import io

def lambda_handler(event, context):
    # S3 bucket and prefix for storing downloaded files
    S3_BUCKET = os.environ['BUCKET_NAME']
    S3_PREFIX = '01_downloaded'

    # Check if there are records to process
    if 'Records' not in event or not event['Records']:
        return {'statusCode': 400, 'body': json.dumps("No SQS message to process.")}

    record = event['Records'][0]
    sqs = boto3.client('sqs')

    try:
        # Parse the SQS message body
        body = json.loads(record['body'])
        url = body['url']
        file_name = record['messageAttributes']['file_name']['stringValue']

        # Validate the file name to avoid path traversal
        if not file_name or '/' in file_name or '\\' in file_name:
            print(f"ERROR: Invalid file name: {file_name}")
            # Delete the message from the queue to prevent retry
            sqs.delete_message(
                QueueUrl=os.environ['QUEUE_URL'],  # SQS queue URL
                ReceiptHandle=record['receiptHandle']
            )
            return {'statusCode': 400, 'body': 'Invalid file name.'}

        print(f"INFO: Starting download of {file_name} from {url}")

        # Download the file from the URL
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Write the file content to a buffer
        buffer = io.BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            buffer.write(chunk)
        buffer.seek(0)

        # Upload the file to S3
        s3_key = f"{S3_PREFIX}/{file_name}"
        s3 = boto3.client('s3')
        s3.upload_fileobj(Fileobj=buffer, Bucket=S3_BUCKET, Key=s3_key)

        print(f"SUCCESS: File uploaded to s3://{S3_BUCKET}/{s3_key}")

    except Exception as e:
        print(f"ERROR: {e}")
        # Delete the message from the queue to prevent retry
        sqs.delete_message(
            QueueUrl=os.environ['QUEUE_URL'],  # SQS queue URL
            ReceiptHandle=record['receiptHandle']
        )
        return {'statusCode': 500, 'body': f'Error processing message: {str(e)}'}

    return {'statusCode': 200, 'body': 'Processing completed.'}
