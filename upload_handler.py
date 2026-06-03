"""


Responsibilities - and ONLY these, to stay off the critical path:
  1. Read the uploaded file from the request.
  2. Compute an MD5 checksum and reject duplicates (checksum-index).
  3. Save the original to s3://<bucket>/uploads/...
  4. Write the BASE DynamoDB record (no thumbnail_url, no tags yet).
  5. Asynchronously invoke tagging-handler (does NOT wait for the model).
  6. Return immediately.

NOTE: thumbnail-generator is triggered automatically by the S3 upload event,
so this function does NOT call it (avoids a double-trigger).

Expected request body (JSON):
  {
    "filename":     "koala1.jpg",
    "content_type": "image/jpeg",
    "file_base64":  "<base64 of the raw file bytes>"
  }
"""

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

# ---- Configuration: set these as Lambda environment variables ----
REGION                = os.environ.get("REGION", "us-east-1")
BUCKET_NAME           = os.environ.get("BUCKET_NAME", "aussie-ecolens-bucket-sri")
TABLE_NAME            = os.environ.get("TABLE_NAME", "wildlife_files")
CHECKSUM_INDEX        = os.environ.get("CHECKSUM_INDEX", "checksum-index")
# IMPORTANT: set this to the real name of your tagging-handler Lambda once it exists.
TAGGING_FUNCTION_NAME = os.environ.get("TAGGING_FUNCTION_NAME", "tagging-handler")

UPLOADS_PREFIX = "uploads/"

# Clients are created once per container and reused across warm invocations.
s3    = boto3.client("s3", region_name=REGION)
lam   = boto3.client("lambda", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}
VIDEO_EXTS = {"mp4", "mov", "avi", "mkv", "webm"}

# ---- Response helpers (match the team's shared response contract) ----
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}


def _ok(data, status=200):
    return {"statusCode": status, "headers": _CORS,
            "body": json.dumps({"success": True, "data": data})}


def _err(message, status=400):
    return {"statusCode": status, "headers": _CORS,
            "body": json.dumps({"success": False, "error": message})}


def _get_claims(event):
    """
    The trustworthy user identity comes from the Cognito authorizer, NOT the
    request body (a client could forge the body). Returns (None, None) when
    invoked outside API Gateway - e.g. the console 'Test' tab - so local
    testing doesn't crash with a KeyError.
    """
    try:
        claims = event["requestContext"]["authorizer"]["claims"]
        return claims.get("sub"), claims.get("email")
    except (KeyError, TypeError):
        return None, None


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
    # ---- 1. Parse the request body ----
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return _err("Request body must be valid JSON.")

    filename     = payload.get("filename")
    content_type = payload.get("content_type", "")
    file_b64     = payload.get("file_base64")

    if not filename or not file_b64:
        return _err("Both 'filename' and 'file_base64' are required.")

    file_type = _detect_file_type(content_type, filename)
    if file_type is None:
        return _err("Unsupported file type (must be an image or a video).")

    # ---- 2. Decode the file + compute checksum ----
    try:
        file_bytes = base64.b64decode(file_b64)
    except Exception:
        return _err("'file_base64' is not valid base64.")

    checksum = hashlib.md5(file_bytes).hexdigest()

    # ---- 3. Deduplicate via the checksum GSI ----
    dup = table.query(
        IndexName=CHECKSUM_INDEX,
        KeyConditionExpression=Key("checksum").eq(checksum),
    )
    if dup.get("Items"):
        existing = dup["Items"][0]
        return _err(
            f"Duplicate file - already uploaded as {existing.get('file_url')}",
            status=409,
        )

    # ---- 4. Save the original to S3 ----
    user_id, user_email = _get_claims(event)
    file_id  = str(uuid.uuid4())
    s3_key   = f"{UPLOADS_PREFIX}{file_id}/{filename}"
    file_url = f"s3://{BUCKET_NAME}/{s3_key}"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type or "application/octet-stream",
    )

    # ---- 5. Write the BASE record ----
    # tags starts as {} and is filled later by tagging-handler.
    # thumbnail_url is intentionally OMITTED so the item stays OUT of
    # thumbnail-index until a real thumbnail exists (a 'sparse' index).
    item = {
        "file_id":       file_id,
        "file_url":      file_url,
        "file_type":     file_type,
        "tags":          {},
        "checksum":      checksum,
        "user_id":       user_id or "unknown",
        "user_email":    user_email or "unknown",
        "uploaded_at":   datetime.now(timezone.utc).isoformat(),
        "original_name": filename,
        "file_size":     len(file_bytes),
        "status":        "processing",
    }
    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(file_id)",  # never clobber
    )

    # ---- 6. Fire tagging-handler asynchronously (do NOT wait for the model) ----
    try:
        lam.invoke(
            FunctionName=TAGGING_FUNCTION_NAME,
            InvocationType="Event",  # async: returns straight away
            Payload=json.dumps({
                "file_id":   file_id,
                "bucket":    BUCKET_NAME,
                "key":       s3_key,
                "file_type": file_type,
            }).encode("utf-8"),
        )
    except Exception as exc:
        # The file is already saved, so don't fail the upload; tagging can retry.
        print(f"WARN: could not invoke {TAGGING_FUNCTION_NAME}: {exc}")

    return _ok({"file_id": file_id, "file_url": file_url, "file_type": file_type})
