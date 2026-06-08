import json
import os
import io
import urllib.parse
import boto3
import uuid
from boto3.dynamodb.conditions import Key
from PIL import Image

REGION = os.environ.get("REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "wildlife_files")
CHECKSUM_INDEX = os.environ.get("CHECKSUM_INDEX", "checksum-index")
FILE_URL_INDEX = "file-url-index"
TAGGING_FUNCTION_NAME = os.environ.get("TAGGING_FUNCTION_NAME", "tagging-handler")
MAX_DIM = 300
JPEG_QUALITY = 70
UPLOADS_PREFIX = "uploads/"
THUMBNAILS_PREFIX = "thumbnails/"
IMAGE_EXTS = {"jpg","jpeg","png","gif","bmp","webp","tiff","heic"}
VIDEO_EXTS = {"mp4","mov","avi","mkv","webm"}
MAX_FRAMES = 30

s3 = boto3.client("s3", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

def _image_thumbnail(data):
    img = Image.open(io.BytesIO(data))
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=JPEG_QUALITY)
    return output.getvalue()

def _thumb_key(src_key):
    rest = src_key[len(UPLOADS_PREFIX):] if src_key.startswith(UPLOADS_PREFIX) else src_key
    root, _ = os.path.splitext(rest)
    return f"{THUMBNAILS_PREFIX}{root}.jpg"

def _update_db_record(file_url, updates):
    resp = table.query(IndexName=FILE_URL_INDEX, KeyConditionExpression=Key("file_url").eq(file_url))
    items = resp.get("Items", [])
    if not items:
        print(f"WARN: no record for {file_url}")
        return None
    
    file_id = items[0]["file_id"]
    update_expr = []
    expr_vals = {}
    expr_names = {}
    
    for k, v in updates.items():
        if k == "status":
            update_expr.append("#s = :s")
            expr_names["#s"] = "status"
            expr_vals[":s"] = v
        else:
            update_expr.append(f"{k} = :{k}")
            expr_vals[f":{k}"] = v
            
    if update_expr:
        kwargs = {
            "Key": {"file_id": file_id},
            "UpdateExpression": "SET " + ", ".join(update_expr),
            "ExpressionAttributeValues": expr_vals
        }
        if expr_names:
            kwargs["ExpressionAttributeNames"] = expr_names
        table.update_item(**kwargs)
    return items[0]

def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith(UPLOADS_PREFIX):
            continue
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        
        try:
            file_url = f"s3://{bucket}/{key}"
            
            if ext in IMAGE_EXTS:
                try:
                    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                    
                    # Thumbnail Generation
                    thumb_bytes = _image_thumbnail(data)
                    thumb_key = _thumb_key(key)
                    s3.put_object(Bucket=bucket, Key=thumb_key, Body=thumb_bytes, ContentType="image/jpeg")
                    thumb_url = f"s3://{bucket}/{thumb_key}"
                    
                    # Update DB (Do NOT overwrite checksum)
                    db_item = _update_db_record(file_url, {
                        "thumbnail_url": thumb_url, 
                        "status": "processing"
                    })
                    
                    # 4. Trigger Tagging
                    if db_item:
                        try:
                            lam.invoke(
                                FunctionName=TAGGING_FUNCTION_NAME,
                                InvocationType="Event",
                                Payload=json.dumps({
                                    "file_id": db_item["file_id"],
                                    "bucket": bucket,
                                    "key": key,
                                    "file_type": "image",
                                }).encode("utf-8"),
                            )
                        except Exception as exc:
                            print(f"WARN: could not invoke {TAGGING_FUNCTION_NAME}: {exc}")
                            
                    print(f"OK: image {key} -> {thumb_key}")
                except Exception as img_err:
                    print(f"WARN: Corrupt or unsupported format for {key}: {img_err}")
                    s3.delete_object(Bucket=bucket, Key=key)
                    _update_db_record(file_url, {"status": "corrupt"})
                
            elif ext in VIDEO_EXTS:
                # OMITTED FOR BREVITY: Video processing (similar structure, no dHash deduplication required for now)
                # If needed, we just process frames like before.
                import cv2
                tmp_video = f"/tmp/{uuid.uuid4()}_{os.path.basename(key)}"
                
                try:
                    s3.download_file(bucket, key, tmp_video)
                    cap = cv2.VideoCapture(tmp_video)
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps <= 0: fps = 30
                    frame_interval = int(fps)
                    current_frame = 0
                    frame_count = 1
                    video_frame_urls = []
                    rest = key[len(UPLOADS_PREFIX):] if key.startswith(UPLOADS_PREFIX) else key
                    root, _ = os.path.splitext(rest)
                    
                    while cap.isOpened() and frame_count <= MAX_FRAMES:
                        ret, frame = cap.read()
                        if not ret: break
                        if current_frame % frame_interval == 0:
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            img = Image.fromarray(frame_rgb)
                            img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
                            output = io.BytesIO()
                            img.save(output, format='JPEG', quality=JPEG_QUALITY)
                            thumb_bytes = output.getvalue()
                            thumb_key = f"{THUMBNAILS_PREFIX}{root}_frame_{frame_count}.jpg"
                            s3.put_object(Bucket=bucket, Key=thumb_key, Body=thumb_bytes, ContentType="image/jpeg")
                            video_frame_urls.append(f"s3://{bucket}/{thumb_key}")
                            frame_count += 1
                        current_frame += 1
                    cap.release()
                    thumb_url = video_frame_urls[0] if video_frame_urls else None
                    db_item = _update_db_record(file_url, {"thumbnail_url": thumb_url, "video_frames": video_frame_urls, "status": "processing"})
                    if db_item:
                        lam.invoke(
                            FunctionName=TAGGING_FUNCTION_NAME,
                            InvocationType="Event",
                            Payload=json.dumps({"file_id": db_item["file_id"], "bucket": bucket, "key": key, "file_type": "video"}).encode("utf-8")
                        )
                    print(f"OK: video {key} -> {len(video_frame_urls)} frames extracted")
                except Exception as vid_err:
                    print(f"WARN: Corrupt video for {key}: {vid_err}")
                    s3.delete_object(Bucket=bucket, Key=key)
                    _update_db_record(file_url, {"status": "corrupt"})
                finally:
                    if os.path.exists(tmp_video):
                        os.remove(tmp_video)
            else:
                print(f"Skipping unsupported file: {ext}")
        except Exception as e:
            print(f"Error processing {key}: {str(e)}")
            
    return {"statusCode": 200}
