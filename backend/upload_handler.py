import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

# ---- Configuration: set these as Lambda environment variables ----
REGION                = os.environ.get("REGION", "us-east-1")
BUCKET_NAME           = os.environ.get("BUCKET_NAME", "aussie-ecolens-bucket-sri")
TABLE_NAME            = os.environ.get("DYNAMODB_TABLE", "wildlife_files")
CHECKSUM_INDEX        = os.environ.get("CHECKSUM_INDEX", "checksum-index")
# TAGGING_FUNCTION_NAME is now used in thumbnail_generator.py, not here.

UPLOADS_PREFIX = "uploads/"
THUMBNAILS_PREFIX = "thumbnails/"

s3    = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "heic"}
VIDEO_EXTS = {"mp4", "mov", "avi", "mkv", "webm"}

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}

def _ok(data, status=200):
    return {"statusCode": status, "headers": _CORS, "body": json.dumps({"success": True, "data": data})}

def _err(message, status=400):
    return {"statusCode": status, "headers": _CORS, "body": json.dumps({"success": False, "error": message})}

def _get_claims(event):
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        return claims.get("sub"), claims.get("email")
    except (KeyError, TypeError):
        return None, None

def get_presigned_url(s3_key, bucket, operation='get_object'):
    if not s3_key:
        return ""
    if s3_key.startswith('s3://'):
        key = s3_key.replace(f's3://{bucket}/', '')
    else:
        key = s3_key
    
    return s3.generate_presigned_url(
        operation,
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=3600
    )

def _detect_file_type(content_type, filename):
    if content_type:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return _ok({})

    try:
        raw = event.get("body") or "{}"
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return _err("Request body must be valid JSON.")

    filename     = payload.get("filename")
    content_type = payload.get("content_type", "")
    file_size    = payload.get("file_size", 0)
    client_hash  = payload.get("client_hash", "")

    if not filename or file_size is None:
        return _err("Both 'filename' and 'file_size' are required.")

    if file_size <= 0:
        return _err("File is empty or corrupt.", status=400)

    # 5GB arbitrary massive limit
    if file_size > 5 * 1024 * 1024 * 1024:
        return _err("File is too large. Maximum size is 5GB.", status=413)

    file_type = _detect_file_type(content_type, filename)
    if file_type is None:
        return _err("Unsupported file type (must be an image or a video).")

    # Synchronous duplicate check if client provided a hash (using Hamming distance to catch different formats/compressions)
    if client_hash:
        try:
            def hamming_distance(h1, h2):
                try:
                    return bin(int(h1, 16) ^ int(h2, 16)).count('1')
                except Exception:
                    return 999

            response = table.scan(ProjectionExpression="file_id, checksum, #s", ExpressionAttributeNames={"#s": "status"})
            items = response.get("Items", [])
            while "LastEvaluatedKey" in response:
                response = table.scan(
                    ProjectionExpression="file_id, checksum, #s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items.extend(response.get("Items", []))

            duplicate_found = False
            for item in items:
                db_checksum = item.get("checksum")
                if db_checksum and db_checksum != "pending" and item.get("status") != "corrupt":
                    # Increased threshold from 5 to 10 to account for compression artifacts when formats differ (e.g. JPG vs PNG)
                    if hamming_distance(client_hash, db_checksum) <= 10:
                        duplicate_found = True
                        break

            if duplicate_found:
                return _err("Duplicate file! This exact image has already been uploaded.", status=409)
        except Exception as scan_err:
            print(f"Error during scan-based duplicate check: {str(scan_err)}")
            # Fallback to direct query
            dup = table.query(
                IndexName=CHECKSUM_INDEX,
                KeyConditionExpression=Key("checksum").eq(client_hash)
            )
            if dup.get("Items"):
                return _err("Duplicate file! This exact image has already been uploaded.", status=409)

    user_id, user_email = _get_claims(event)
    if not user_id:
        return _err("Unauthorized: You must be logged in to upload files.", status=401)

    file_id = str(uuid.uuid4())
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    s3_key = f"{UPLOADS_PREFIX}{file_id}/{safe_name}"
    file_url = f"s3://{BUCKET_NAME}/{s3_key}"

    # Generate presigned upload URL
    try:
        upload_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': s3_key,
                'ContentType': content_type or "application/octet-stream"
            },
            ExpiresIn=3600
        )
    except Exception as e:
        return _err(f"Failed to generate upload URL: {str(e)}", status=500)

    item = {
        "file_id":       file_id,
        "file_url":      file_url,
        "file_type":     file_type,
        "tags":          {},
        "checksum":      client_hash or "pending",
        "user_id":       user_id,
        "user_email":    user_email,
        "allow_tag_editing": False,
        "uploaded_at":   datetime.now(timezone.utc).isoformat(),
        "original_name": filename,
        "file_size":     file_size,
        "status":        "pending_upload",
    }
    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(file_id)",
    )

    rest = s3_key[len(UPLOADS_PREFIX):] if s3_key.startswith(UPLOADS_PREFIX) else s3_key
    root, _ = os.path.splitext(rest)
    if file_type == "video":
        thumb_key = f"{THUMBNAILS_PREFIX}{root}_frame_1.jpg"
    else:
        thumb_key = f"{THUMBNAILS_PREFIX}{root}.jpg"
        
    predicted_thumb_s3_url = f"s3://{BUCKET_NAME}/{thumb_key}"
    
    presigned_file_url = get_presigned_url(file_url, BUCKET_NAME)
    presigned_thumb_url = get_presigned_url(predicted_thumb_s3_url, BUCKET_NAME)

    return _ok({
        "file_id": file_id, 
        "upload_url": upload_url,
        "file_url": presigned_file_url, 
        "thumbnail_url": presigned_thumb_url,
        "file_type": file_type, 
        "status": "pending_upload"
    })
