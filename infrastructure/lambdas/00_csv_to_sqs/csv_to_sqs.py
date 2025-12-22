import boto3
import os
import csv
import json

s3 = boto3.client('s3')
sqs = boto3.client('sqs')

def lambda_handler(event, context):
    bucket_name = os.environ['BUCKET_NAME']
    queue_url = os.environ['QUEUE_URL']
    file_key = '99_params/filelist.csv'

    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    csv_content = response['Body'].read().decode('utf-8').splitlines()

    sent_messages = []
    for line in csv.DictReader(csv_content):
        dataset_id = line['dataset_id']
        base_url = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
        url = f"{base_url}{dataset_id}/exports/parquet?lang=fr&timezone=Europe%2FBerlin"
        file_name = f"{dataset_id}.parquet"
        message_body = {
            "url": url,
            "file_name": file_name,
            "step": "process_file"
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
        'body': f"Sent {len(sent_messages)} messages to SQS!",
        'files': sent_messages 
    }
