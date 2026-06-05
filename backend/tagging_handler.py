import os, boto3, json, base64, urllib.request
REGION = os.environ.get("REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "wildlife_files")
GCP_URL = os.environ.get("GCP_FUNCTION_URL", "")
GCP_SECRET = os.environ.get("GCP_SECRET_KEY", "aussie-ecolens-2026")
NOTIFY_FN = os.environ.get("NOTIFY_FUNCTION_NAME", "notification-handler")
s3 = boto3.client("s3", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

import hmac
import hashlib
import time

def call_gcp(image_bytes, filename):
    if not GCP_URL:
        return {}
    
    timestamp = int(time.time())
    secret = GCP_SECRET
    
    # Generate HMAC token
    token = hmac.new(
        secret.encode(),
        str(timestamp).encode(),
        hashlib.sha256
    ).hexdigest()

    try:
        body = json.dumps({
            "filename": filename,
            "image_data": base64.b64encode(image_bytes).decode(),
            "secret_key": token,
            "timestamp": timestamp
        }).encode()
        req = urllib.request.Request(GCP_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
        return data.get("tags", {})
    except Exception as e:
        print(f"GCP error: {e}")
        return {}

def lambda_handler(event, context):
    file_id = event["file_id"]
    bucket = event["bucket"]
    key = event["key"]
    filename = os.path.basename(key)
    try:
        data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        tags = call_gcp(data, filename)
        print(f"Tags: {tags}")
        table.update_item(Key={"file_id": file_id}, UpdateExpression="SET tags = :t, #s = :st", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":t": tags, ":st": "complete"})
        try:
            lam.invoke(FunctionName=NOTIFY_FN, InvocationType="Event", Payload=json.dumps({"action": "notify","tags": tags,"file_url": f"s3://{bucket}/{key}"}).encode())
        except Exception as e:
            print(f"Notify error: {e}")
        return {"statusCode": 200, "tags": tags}
    except Exception as e:
        print(f"Error: {e}")
        return {"statusCode": 500}
