import json
import os
import io
import urllib.parse
import boto3
from boto3.dynamodb.conditions import Key
from PIL import Image
import cv2

REGION = os.environ.get("REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "wildlife_files")
FILE_URL_INDEX = "file-url-index"
MAX_DIM = 300
JPEG_QUALITY = 70
UPLOADS_PREFIX = "uploads/"
THUMBNAILS_PREFIX = "thumbnails/"
IMAGE_EXTS = {"jpg","jpeg","png","gif","bmp","webp"}
VIDEO_EXTS = {"mp4","mov","avi","mkv","webm"}

s3 = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

def _image_thumbnail(data):
    img = Image.open(io.BytesIO(data))
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=JPEG_QUALITY)
    return output.getvalue()

def _thumb_key(src_key):
    rest = src_key[len(UPLOADS_PREFIX):] if src_key.startswith(UPLOADS_PREFIX) else src_key
    root, _ = os.path.splitext(rest)
    return f"{THUMBNAILS_PREFIX}{root}.jpg"

def _set_thumbnail_urls(file_url, thumb_url=None, video_frames=None):
    resp = table.query(IndexName=FILE_URL_INDEX, KeyConditionExpression=Key("file_url").eq(file_url))
    items = resp.get("Items", [])
    if not items:
        print(f"WARN: no record for {file_url}")
        return
    
    update_expr = []
    expr_vals = {}
    if thumb_url:
        update_expr.append("thumbnail_url = :t")
        expr_vals[":t"] = thumb_url
    if video_frames is not None:
        update_expr.append("video_frames = :vf")
        expr_vals[":vf"] = video_frames
    
    if update_expr:
        table.update_item(
            Key={"file_id": items[0]["file_id"]}, 
            UpdateExpression="SET " + ", ".join(update_expr), 
            ExpressionAttributeValues=expr_vals
        )

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
                data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                thumb_bytes = _image_thumbnail(data)
                thumb_key = _thumb_key(key)
                s3.put_object(Bucket=bucket, Key=thumb_key, Body=thumb_bytes, ContentType="image/jpeg")
                thumb_url = f"s3://{bucket}/{thumb_key}"
                _set_thumbnail_urls(file_url, thumb_url=thumb_url)
                print(f"OK: image {key} -> {thumb_key}")
                
            elif ext in VIDEO_EXTS:
                # Download video to /tmp
                tmp_video = f"/tmp/{os.path.basename(key)}"
                s3.download_file(bucket, key, tmp_video)
                
                cap = cv2.VideoCapture(tmp_video)
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps <= 0: fps = 30 # fallback
                
                frame_interval = int(fps)
                current_frame = 0
                frame_count = 1
                video_frame_urls = []
                
                rest = key[len(UPLOADS_PREFIX):] if key.startswith(UPLOADS_PREFIX) else key
                root, _ = os.path.splitext(rest)
                
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    if current_frame % frame_interval == 0:
                        # Convert cv2 BGR to RGB and use PIL to resize
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
                if os.path.exists(tmp_video):
                    os.remove(tmp_video)
                
                _set_thumbnail_urls(file_url, video_frames=video_frame_urls)
                print(f"OK: video {key} -> {len(video_frame_urls)} frames extracted")
                
            else:
                print(f"Skipping unsupported file: {ext}")
                
        except Exception as e:
            print(f"Error processing {key}: {str(e)}")
            
    return {"statusCode": 200}
