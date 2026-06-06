import json
import boto3
from urllib.parse import urlparse
import os

# CONFIGURATION
BUCKET = os.environ.get('BUCKET_NAME', 'aussie-ecolens-bucket-sri')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'wildlife_files')
AWS_REGION = os.environ.get('REGION', 'us-east-1')

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS"
}

def success_response(data, status_code=200):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"success": True, "data": data})
    }

def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"success": False, "error": message})
    }

def extract_s3_key(url):
    """Extract S3 key from full S3 URL"""
    if url.startswith('s3://'):
        parts = url.replace('s3://', '').split('/', 1)
        return parts[1] if len(parts) > 1 else ''
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    if path.startswith(BUCKET + "/"):
        return path.replace(BUCKET + "/", "", 1)
    return path

def delete_from_s3(key):
    try:
        s3.delete_object(Bucket=BUCKET, Key=key)
        print(f"Deleted from S3: {key}")
        return True
    except Exception as e:
        print(f"Error deleting from S3: {key} → {str(e)}")
        return False

def lambda_handler(event, context):
    """
    DELETE /files
    {
        "urls": ["https://aussie-ecolens-bucket-sri.s3.amazonaws.com/uploads/image1.jpg"]
    }
    """
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return success_response({})

    # Get user from token
    claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
    user_id = claims.get('sub', '')
    
    if not user_id:
        return error_response("Unauthorized: No valid user_id found in token.", 401)

    try:
        body = json.loads(event.get("body", "{}"))
        urls = body.get("urls", [])

        if not urls:
            return error_response("No URLs provided")

        results = []

        for raw_url in urls:
            file_url = raw_url
            if file_url.startswith("https://"):
                file_url = file_url.split("?")[0]
                if f"{BUCKET}.s3.amazonaws.com" in file_url:
                    key = file_url.split(f"{BUCKET}.s3.amazonaws.com/")[-1]
                    file_url = f"s3://{BUCKET}/{key}"
                elif f"s3.amazonaws.com/{BUCKET}" in file_url or f"s3-{AWS_REGION}.amazonaws.com/{BUCKET}" in file_url:
                    key = file_url.split(f"/{BUCKET}/")[-1]
                    file_url = f"s3://{BUCKET}/{key}"

            result = {"url": file_url, "status": "success", "errors": []}

            # Extract S3 key
            s3_key = extract_s3_key(file_url)

            # Check DB first for ownership and thumbnail url
            response = table.query(
                IndexName="file-url-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("file_url").eq(file_url)
            )
            items = response.get("Items", [])

            if not items:
                result["errors"].append("Not found")
                result["status"] = "failed"
                results.append(result)
                continue

            item = items[0]
            if item.get("user_id") != user_id:
                result["errors"].append("Not authorized")
                result["status"] = "unauthorized"
                results.append(result)
                continue

            thumbnail_url = item.get("thumbnail_url", "")

            # Delete original from S3
            if not delete_from_s3(s3_key):
                result["errors"].append(f"Failed to delete original: {s3_key}")

            # Delete thumbnail from S3
            if thumbnail_url:
                thumbnail_key = extract_s3_key(thumbnail_url)
                if not delete_from_s3(thumbnail_key):
                    result["errors"].append(f"Failed to delete thumbnail: {thumbnail_key}")

            # Delete video frames from S3
            video_frames = item.get("video_frames", [])
            for frame_url in video_frames:
                frame_key = extract_s3_key(frame_url)
                if not delete_from_s3(frame_key):
                    result["errors"].append(f"Failed to delete video frame: {frame_key}")

            # ONLY delete from DynamoDB if all S3 deletes succeeded
            if not result["errors"]:
                try:
                    table.delete_item(Key={"file_id": item["file_id"]})
                except Exception as e:
                    result["errors"].append(f"Failed to delete from DB: {str(e)}")
                    result["status"] = "partial_failure"
            else:
                result["status"] = "partial_failure"
                result["errors"].append("DB record kept because S3 objects failed to delete.")

            results.append(result)

        return success_response({
            "message": "Delete operation completed",
            "results": results
        })

    except Exception as e:
        return error_response(f"Internal server error: {str(e)}", 500)
