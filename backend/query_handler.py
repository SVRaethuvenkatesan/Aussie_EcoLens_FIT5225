import json
import boto3
import tempfile
import os
import urllib.request
import base64
import decimal
import time
import hmac
import hashlib
from boto3.dynamodb.conditions import Attr, Key

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# CONFIGURATION
S3_BUCKET_NAME = os.environ.get('BUCKET_NAME', 'aussie-ecolens-bucket-sri')
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'wildlife_files')
AWS_REGION = os.environ.get('REGION', 'us-east-1')
UPLOADS_FOLDER = "uploads/"
THUMBNAILS_FOLDER = "thumbnails/"
GCP_ML_FUNCTION_URL = os.environ.get('GCP_FUNCTION_URL', 'https://ml-detector-562419717393.us-central1.run.app')
GCP_SECRET_KEY = os.environ.get('GCP_SECRET_KEY', 'aussie-ecolens-2026')


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
        "body": json.dumps({"success": True, "data": data}, cls=DecimalEncoder)
    }

def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"success": False, "error": message})
    }

def _get_claims(event):
    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        return claims.get("sub"), claims.get("email")
    except (KeyError, TypeError, AttributeError):
        return None, None


def get_presigned_url(s3_key, bucket):
    if not s3_key:
        return ""
    if s3_key.startswith('s3://'):
        key = s3_key.replace(f's3://{bucket}/', '')
    else:
        key = s3_key
    
    return s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket,
            'Key': key
        },
        ExpiresIn=3600
    )

def format_result(item):
    file_type = item.get("file_type", "").lower()
    is_video = file_type == "video"
    
    file_url_signed = get_presigned_url(item.get("file_url"), S3_BUCKET_NAME)
    thumb_url_signed = get_presigned_url(item.get("thumbnail_url"), S3_BUCKET_NAME)
    
    video_frames_presigned = []
    if is_video and "video_frames" in item:
        for vf in item["video_frames"]:
            video_frames_presigned.append(get_presigned_url(vf, S3_BUCKET_NAME))
    
    return {
        "url": file_url_signed if is_video else thumb_url_signed,
        "file_url": file_url_signed,
        "thumbnail_url": thumb_url_signed,
        "video_frames": video_frames_presigned,
        "file_type": file_type,
        "tags": item.get("tags", {}),
        "is_video": is_video,
        "original_name": item.get("original_name", ""),
        "uploaded_at": item.get("uploaded_at", "")
    }

def scan_all():
    items = []
    response = table.scan()
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    return items

# ================================================
# QUERY TYPE 1: Find by tags with minimum counts
# POST /query/tags
# {"koala": 3, "wombat": 2}
# ================================================
def query_by_tags(tag_counts):
    try:
        items = scan_all()

        matching = []
        for item in items:
            item_tags = item.get("tags", {})
            # AND logic: ALL tags must meet minimum count
            match = all(
                int(item_tags.get(tag, 0)) >= int(count)
                for tag, count in tag_counts.items()
            )
            if match:
                matching.append(format_result(item))

        return success_response({"results": matching, "count": len(matching)})

    except Exception as e:
        return error_response(str(e), 500)

# QUERY TYPE 2: Find by species
# POST /query/species
# {"species": "dingo"}
def query_by_species(species):
    try:
        items = scan_all()

        matching = []
        for item in items:
            item_tags = item.get("tags", {})
            if species.lower() in {k.lower() for k in item_tags.keys()}:
                matching.append(format_result(item))

        return success_response({"results": matching, "count": len(matching)})

    except Exception as e:
        return error_response(str(e), 500)

# QUERY TYPE 3: Find full image by thumbnail URL
# GET /query/thumbnail?thumbnail_url=https://...
def query_by_thumbnail_url(thumbnail_url):
    try:
        # Normalize https:// presigned URLs to s3:// format
        s3_url = thumbnail_url
        if s3_url.startswith("https://"):
            s3_url = s3_url.split("?")[0]
            if f"{S3_BUCKET_NAME}.s3.amazonaws.com" in s3_url:
                key = s3_url.split(f"{S3_BUCKET_NAME}.s3.amazonaws.com/")[-1]
                s3_url = f"s3://{S3_BUCKET_NAME}/{key}"
            elif f"s3.amazonaws.com/{S3_BUCKET_NAME}" in s3_url or f"s3-{AWS_REGION}.amazonaws.com/{S3_BUCKET_NAME}" in s3_url:
                key = s3_url.split(f"/{S3_BUCKET_NAME}/")[-1]
                s3_url = f"s3://{S3_BUCKET_NAME}/{key}"
                
        # Use thumbnail-index for efficient lookup
        response = table.query(
            IndexName="thumbnail-index",
            KeyConditionExpression=Key("thumbnail_url").eq(s3_url)
        )
        items = response.get("Items", [])

        if not items:
            return error_response("No file found for this thumbnail URL", 404)

        item = items[0]
        return success_response({
            "file_url": get_presigned_url(item.get("file_url"), S3_BUCKET_NAME),
            "thumbnail_url": get_presigned_url(item.get("thumbnail_url"), S3_BUCKET_NAME),
            "file_type": item.get("file_type"),
            "tags": item.get("tags", {}),
            "original_name": item.get("original_name", "")
        })

    except Exception as e:
        return error_response(str(e), 500)

# QUERY TYPE 4: Find files by uploaded file tags
# POST /query/file
# multipart/form-data with file
# Does NOT store the query file!
def extract_video_frames(file_content, file_name):
    """Extract 1 frame per second from video"""
    try:
        import cv2

        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        frames = []
        cap = cv2.VideoCapture(tmp_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = max(int(fps), 1)

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_interval == 0:
                _, buffer = cv2.imencode('.jpg', frame)
                frames.append(buffer.tobytes())
            frame_count += 1

        cap.release()
        os.unlink(tmp_path)
        return frames

    except Exception as e:
        print(f"Error extracting frames: {str(e)}")
        return []

def detect_tags_from_file(file_content, file_name):
    """Send file to GCP ML and get detected tags"""
    file_ext = os.path.splitext(file_name)[1].lower()
    is_video = file_ext in [".mp4", ".avi", ".mov", ".mkv"]
    all_tags = {}

    def call_gcp(img_bytes, fname):
        if not GCP_ML_FUNCTION_URL:
            return {}
            
        timestamp = int(time.time())
        token = hmac.new(
            GCP_SECRET_KEY.encode(),
            str(timestamp).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        try:
            body = json.dumps({
                "filename": fname,
                "image_data": base64.b64encode(img_bytes).decode("utf-8"),
                "secret_key": token,
                "timestamp": timestamp
            }).encode("utf-8")
            req = urllib.request.Request(GCP_ML_FUNCTION_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode())
            return data.get("tags", {})
        except Exception as e:
            print(f"GCP error: {e}")
            return {}

    if is_video:
        frames = extract_video_frames(file_content, file_name)
        for i, frame in enumerate(frames):
            frame_tags = call_gcp(frame, f"frame_{i}.jpg")
            for tag, count in frame_tags.items():
                all_tags[tag] = max(all_tags.get(tag, 0), int(count))
    else:
        all_tags = call_gcp(file_content, file_name)

    return all_tags

def query_by_uploaded_file(file_content, file_name):
    try:
        # Detect tags (file is NOT stored)
        detected_tags = detect_tags_from_file(file_content, file_name)

        if not detected_tags:
            return success_response({
                "results": [],
                "detected_tags": {},
                "message": "No species detected in file"
            })

        # Find matching files in DB
        items = scan_all()

        matching = []
        for item in items:
            item_tags = item.get("tags", {})
            match = all(
                int(item_tags.get(tag, 0)) >= int(count)
                for tag, count in detected_tags.items()
            )
            if match:
                matching.append(format_result(item))

        return success_response({
            "detected_tags": detected_tags,
            "results": matching,
            "count": len(matching)
        })

    except Exception as e:
        return error_response(str(e), 500)

def query_my_uploads(user_id):
    try:
        items = scan_all()
        
        matching = []
        for item in items:
            if item.get("user_id") == user_id:
                matching.append(format_result(item))

        # Sort by uploaded_at descending
        matching.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)

        return success_response({"results": matching, "count": len(matching)})

    except Exception as e:
        return error_response(str(e), 500)

# QUERY TYPE 5: Bulk tag add/remove
# POST /tags/manage
# {
#   "urls": ["url1", "url2"],
#   "tags": ["koala", "wombat"],
#   "operation": 1  (1=add, 0=remove)
# }
def bulk_tag_edit(urls, tags, operation, user_id):
    try:
        results = []

        for raw_url in urls:
            # Normalize https:// presigned URLs to s3:// format
            file_url = raw_url
            if file_url.startswith("https://"):
                # Remove query params
                file_url = file_url.split("?")[0]
                bucket = S3_BUCKET_NAME
                if f"{bucket}.s3.amazonaws.com" in file_url:
                    key = file_url.split(f"{bucket}.s3.amazonaws.com/")[-1]
                    file_url = f"s3://{bucket}/{key}"

            # Use file-url-index for efficient lookup
            response = table.query(
                IndexName="file-url-index",
                KeyConditionExpression=Key("file_url").eq(file_url)
            )
            items = response.get("Items", [])

            if not items:
                results.append({"url": file_url, "status": "not_found"})
                continue

            if not user_id:
                results.append({"url": file_url, "status": "unauthorized"})
                continue
                
            item = items[0]
            file_id = item["file_id"]
            current_tags = item.get("tags", {})
            owner_id = item.get("user_id")
            allow_editing = item.get("allow_tag_editing", False)

            if owner_id != user_id and not allow_editing:
                results.append({"url": file_url, "status": "unauthorized"})
                continue

            if operation == 1:
                # ADD tags
                for tag in tags:
                    current_tags[tag] = current_tags.get(tag, 0) + 1
            elif operation == 0:
                # REMOVE tags - ignore if not present (as per spec)
                for tag in tags:
                    if tag in current_tags:
                        del current_tags[tag]

            # Update DynamoDB
            table.update_item(
                Key={"file_id": file_id},
                UpdateExpression="SET tags = :tags",
                ExpressionAttributeValues={":tags": current_tags}
            )

            results.append({
                "url": file_url,
                "status": "success",
                "updated_tags": current_tags
            })

        return success_response({"results": results})

    except Exception as e:
        return error_response(str(e), 500)

def set_tag_sharing(urls, allow, user_id):
    try:
        results = []
        for raw_url in urls:
            file_url = raw_url
            if file_url.startswith("https://"):
                file_url = file_url.split("?")[0]
                bucket = S3_BUCKET_NAME
                if f"{bucket}.s3.amazonaws.com" in file_url:
                    key = file_url.split(f"{bucket}.s3.amazonaws.com/")[-1]
                    file_url = f"s3://{bucket}/{key}"

            response = table.query(
                IndexName="file-url-index",
                KeyConditionExpression=Key("file_url").eq(file_url)
            )
            items = response.get("Items", [])
            if not items:
                results.append({"url": file_url, "status": "not_found"})
                continue
            item = items[0]
            if item.get("user_id") != user_id:
                results.append({"url": file_url, "status": "unauthorized"})
                continue

            table.update_item(
                Key={"file_id": item["file_id"]},
                UpdateExpression="SET allow_tag_editing = :a",
                ExpressionAttributeValues={":a": allow}
            )
            results.append({"url": file_url, "status": "success"})
        return success_response({"results": results})
    except Exception as e:
        return error_response(str(e), 500)

# MAIN LAMBDA HANDLER
def lambda_handler(event, context):
    print(f"EVENT: {json.dumps(event)}")
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return success_response({})

    user_id, _ = _get_claims(event)

    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "POST")
        body = {}

        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except Exception:
                body = {}

        # Route to correct query type
        if path == "/query/my_uploads":
            if not user_id:
                result = error_response("Unauthorized", 401)
            else:
                result = query_my_uploads(user_id)

        elif path == "/tags/manage":
            # Query Type 5: Bulk tag edit
            urls = body.get("urls", [])
            tags = body.get("tags", [])
            operation = body.get("operation", 1)
            result = bulk_tag_edit(urls, tags, operation, user_id)

        elif path == "/tags/sharing":
            urls = body.get("urls", [])
            allow = body.get("allow", False)
            result = set_tag_sharing(urls, allow, user_id)


        elif path == "/query/tags":
            if body.get("action") == "my_uploads":
                if not user_id:
                    result = error_response("Unauthorized", 401)
                else:
                    result = query_my_uploads(user_id)
            else:
                # Query Type 1: Tags with minimum counts
                valid_body = {k: v for k, v in body.items() if isinstance(v, (int, float, str)) and str(v).isdigit()}
                result = query_by_tags(valid_body)

        elif path == "/query/species":
            # Query Type 2: Species
            species = body.get("species", "")
            if not species:
                result = error_response("Species is required")
            else:
                result = query_by_species(species)

        elif path == "/query/thumbnail":
            # Query Type 3: Thumbnail URL
            params = event.get("queryStringParameters") or {}
            thumbnail_url = params.get("thumbnail_url") or body.get("thumbnail_url", "")
            if not thumbnail_url:
                result = error_response("thumbnail_url is required")
            else:
                result = query_by_thumbnail_url(thumbnail_url)

        elif path == "/query/file":
            # Query Type 4: Uploaded file
            file_b64 = body.get("file_content", "")
            if not file_b64:
                result = error_response("No file provided")
            else:
                file_content = base64.b64decode(file_b64)
                file_name = body.get("file_name", "query.jpg")
                result = query_by_uploaded_file(file_content, file_name)

        else:
            result = error_response("Invalid query path")

        return result

    except Exception as e:
        return error_response(f"Internal server error: {str(e)}", 500)
