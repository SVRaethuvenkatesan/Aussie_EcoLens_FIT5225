import json
import boto3
import tempfile
import os
import requests
from boto3.dynamodb.conditions import Attr, Key

# CONFIGURATION
S3_BUCKET_NAME = "aussie-ecolens-bucket-sri"
DYNAMODB_TABLE_NAME = "wildlife_files"
AWS_REGION = "us-east-1"
UPLOADS_FOLDER = "uploads/"
THUMBNAILS_FOLDER = "thumbnails/"
GCP_ML_FUNCTION_URL = "https://your-gcp-function-url"  # Update GCP 


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

def format_result(item):
    """
    Images → return thumbnail URL
    Videos → return full file URL
    """
    file_type = item.get("file_type", "").lower()
    is_video = file_type in ["mp4", "avi", "mov", "mkv", "video"]

    return {
        "url": item.get("file_url") if is_video else item.get("thumbnail_url"),
        "file_url": item.get("file_url"),
        "thumbnail_url": item.get("thumbnail_url"),
        "file_type": file_type,
        "tags": item.get("tags", {}),
        "is_video": is_video,
        "original_name": item.get("original_name", ""),
        "uploaded_at": item.get("uploaded_at", "")
    }

# ================================================
# QUERY TYPE 1: Find by tags with minimum counts
# POST /query/tags
# {"koala": 3, "wombat": 2}
# ================================================
def query_by_tags(tag_counts):
    try:
        response = table.scan()
        items = response.get("Items", [])

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
        response = table.scan()
        items = response.get("Items", [])

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
        # Use thumbnail-index for efficient lookup
        response = table.query(
            IndexName="thumbnail-index",
            KeyConditionExpression=Key("thumbnail_url").eq(thumbnail_url)
        )
        items = response.get("Items", [])

        if not items:
            return error_response("No file found for this thumbnail URL", 404)

        item = items[0]
        return success_response({
            "file_url": item.get("file_url"),
            "thumbnail_url": item.get("thumbnail_url"),
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

    if is_video:
        frames = extract_video_frames(file_content, file_name)
        for i, frame in enumerate(frames):
            files = {"file": (f"frame_{i}.jpg", frame, "image/jpeg")}
            gcp_response = requests.post(GCP_ML_FUNCTION_URL, files=files, timeout=30)
            if gcp_response.status_code == 200:
                frame_tags = gcp_response.json().get("tags", {})
                for tag, count in frame_tags.items():
                    all_tags[tag] = max(all_tags.get(tag, 0), int(count))
    else:
        files = {"file": (file_name, file_content)}
        gcp_response = requests.post(GCP_ML_FUNCTION_URL, files=files, timeout=30)
        if gcp_response.status_code == 200:
            all_tags = gcp_response.json().get("tags", {})

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
        response = table.scan()
        items = response.get("Items", [])

        matching = []
        for item in items:
            item_tags = item.get("tags", {})
            match = all(tag in item_tags for tag in detected_tags.keys())
            if match:
                matching.append(format_result(item))

        return success_response({
            "detected_tags": detected_tags,
            "results": matching,
            "count": len(matching)
        })

    except Exception as e:
        return error_response(str(e), 500)

# QUERY TYPE 5: Bulk tag add/remove
# POST /tags/manage
# {
#   "urls": ["url1", "url2"],
#   "tags": ["koala", "wombat"],
#   "operation": 1  (1=add, 0=remove)
# }
def bulk_tag_edit(urls, tags, operation):
    try:
        results = []

        for file_url in urls:
            # Use file-url-index for efficient lookup
            response = table.query(
                IndexName="file-url-index",
                KeyConditionExpression=Key("file_url").eq(file_url)
            )
            items = response.get("Items", [])

            if not items:
                results.append({"url": file_url, "status": "not_found"})
                continue

            item = items[0]
            file_id = item["file_id"]
            current_tags = item.get("tags", {})

            if operation == 1:
                # ADD tags
                for tag in tags:
                    if tag not in current_tags:
                        current_tags[tag] = 1
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

# MAIN LAMBDA HANDLER
def lambda_handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return success_response({})

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
        if path == "/tags/manage":
            # Query Type 5: Bulk tag edit
            urls = body.get("urls", [])
            tags = body.get("tags", [])
            operation = body.get("operation", 1)
            result = bulk_tag_edit(urls, tags, operation)

        elif path == "/query/tags":
            # Query Type 1: Tags with minimum counts
            result = query_by_tags(body)

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
            file_content = event.get("body", b"")
            if isinstance(file_content, str):
                file_content = file_content.encode()
            file_name = event.get("headers", {}).get("file-name", "query_file.jpg")
            result = query_by_uploaded_file(file_content, file_name)

        else:
            result = error_response("Invalid query path")

        return result

    except Exception as e:
        return error_response(f"Internal server error: {str(e)}", 500)
