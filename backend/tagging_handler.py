import os
import boto3
import json
import base64
import urllib.request
import hmac
import hashlib
import time

REGION = os.environ.get("REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "wildlife_files")
GCP_URL = os.environ.get("GCP_FUNCTION_URL", "")
GCP_SECRET = os.environ.get("GCP_SECRET_KEY", "aussie-ecolens-2026")
NOTIFY_FN = os.environ.get("NOTIFY_FUNCTION_NAME", "notification-handler")

s3 = boto3.client("s3", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)

def call_gcp(image_bytes, filename):
    if not GCP_URL:
        return {}
    
    timestamp = int(time.time())
    
    try:
        token = hmac.new(
            GCP_SECRET.encode(),
            str(timestamp).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        body = json.dumps({
            "filename": filename,
            "image_data": base64.b64encode(image_bytes).decode("utf-8"),
            "secret_key": token,
            "timestamp": timestamp
        }).encode("utf-8")
        req = urllib.request.Request(GCP_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
        return data.get("tags", {})
    except Exception as e:
        print(f"GCP error: {e}")
        return {}

def extract_video_frames_from_s3(bucket, key):
    try:
        import cv2
        import tempfile
        
        ext = os.path.splitext(key)[1]
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
        
        s3.download_file(bucket, key, tmp_path)
        
        frames = []
        cap = cv2.VideoCapture(tmp_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = max(int(fps), 1)
        
        frame_count = 0
        while cap.isOpened() and len(frames) < 5:  # Limit to 5 frames to prevent timeouts
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_interval == 0:
                _, buffer = cv2.imencode('.jpg', frame)
                frames.append(buffer.tobytes())
            frame_count += 1
            
        cap.release()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return frames
    except Exception as e:
        print(f"Error extracting frames: {e}")
        return []

def get_presigned_url(bucket, key):
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=3600*24*7 # 7 days
    )

def lambda_handler(event, context):
    try:
        file_id = event["file_id"]
        bucket = event["bucket"]
        key = event["key"]
        file_type = event.get("file_type", "image")
        filename = os.path.basename(key)
        
        tags = {}
        if file_type == "video":
            frames = extract_video_frames_from_s3(bucket, key)
            for i, frame in enumerate(frames):
                frame_tags = call_gcp(frame, f"{filename}_frame_{i}.jpg")
                for tag, count in frame_tags.items():
                    tags[tag] = max(tags.get(tag, 0), int(count))
        else:
            data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            tags = call_gcp(data, filename)
            
        print(f"Tags: {tags}")
        
        # Mark as complete and save tags
        table.update_item(
            Key={"file_id": file_id}, 
            UpdateExpression="SET tags = :t, #s = :st", 
            ExpressionAttributeNames={"#s": "status"}, 
            ExpressionAttributeValues={":t": tags, ":st": "complete"}
        )
        
        # Notify subscribers
        try:
            public_url = get_presigned_url(bucket, key)
            lam.invoke(
                FunctionName=NOTIFY_FN, 
                InvocationType="Event", 
                Payload=json.dumps({
                    "action": "notify",
                    "tags": tags,
                    "file_url": public_url
                }).encode("utf-8")
            )
        except Exception as e:
            print(f"Notify error: {e}")
            
        return {"statusCode": 200, "tags": tags}
        
    except KeyError as e:
        print(f"Missing required key in event: {e}")
        return {"statusCode": 400, "error": f"Missing key {e}"}
    except Exception as e:
        print(f"Error processing file: {e}")
        if 'file_id' in locals():
            try:
                table.update_item(
                    Key={"file_id": file_id}, 
                    UpdateExpression="SET #s = :st", 
                    ExpressionAttributeNames={"#s": "status"}, 
                    ExpressionAttributeValues={":st": "failed"}
                )
            except Exception as inner_e:
                print(f"Failed to update status to failed: {inner_e}")
        return {"statusCode": 500, "error": str(e)}
