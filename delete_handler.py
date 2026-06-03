import json
import boto3
from urllib.parse import urlparse
from boto3.dynamodb.conditions import Attr

# CONFIGURATION
S3_BUCKET_NAME = "aussie-ecolens-bucket-sri"
DYNAMODB_TABLE_NAME = "wildlife_files"
AWS_REGION = "us-east-1"
UPLOADS_FOLDER = "uploads/"
THUMBNAILS_FOLDER = "thumbnails/"

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

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
    parsed = urlparse(url)
    return parsed.path.lstrip("/")

def delete_from_s3(key):
    try:
        s3.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
        print(f"Deleted from S3: {key}")
        return True
    except Exception as e:
        print(f"Error deleting from S3: {key} → {str(e)}")
        return False

def delete_from_dynamodb(file_url):
    try:
        response = table.query(
            IndexName="file-url-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("file_url").eq(file_url)
        )
        items = response.get("Items", [])

        if not items:
            print(f"No DynamoDB record found for: {file_url}")
            return False

        for item in items:
            table.delete_item(Key={"file_id": item["file_id"]})
            print(f"Deleted DynamoDB record: {item['file_id']}")

        return True

    except Exception as e:
        print(f"Error deleting from DynamoDB: {str(e)}")
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

    try:
        body = json.loads(event.get("body", "{}"))
        urls = body.get("urls", [])

        if not urls:
            return error_response("No URLs provided")

        results = []

        for file_url in urls:
            result = {"url": file_url, "status": "success", "errors": []}

            # Extract S3 key
            s3_key = extract_s3_key(file_url)

            # Delete original from S3
            if not delete_from_s3(s3_key):
                result["errors"].append(f"Failed to delete original: {s3_key}")

            # Delete thumbnail from S3
            thumbnail_key = s3_key.replace(UPLOADS_FOLDER, THUMBNAILS_FOLDER)
            if thumbnail_key != s3_key:
                if not delete_from_s3(thumbnail_key):
                    result["errors"].append(f"Failed to delete thumbnail: {thumbnail_key}")

            # Delete from DynamoDB
            if not delete_from_dynamodb(file_url):
                result["errors"].append(f"Failed to delete from DB: {file_url}")

            if result["errors"]:
                result["status"] = "partial_failure"

            results.append(result)

        return success_response({
            "message": "Delete operation completed",
            "results": results
        })

    except Exception as e:
        return error_response(f"Internal server error: {str(e)}", 500)
