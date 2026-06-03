"""""

Responsibilities:
  - Image: resize keeping aspect ratio, compress, save to thumbnails/.
  - Video: grab ONE representative frame (Ed ruling: one frame is enough),
           resize + compress it, save to thumbnails/.
  - Then UpdateItem to set ONLY thumbnail_url on the matching record,
    located via file-url-index.

It does NOT touch 'tags' - tagging-handler owns that attribute, so the two
functions can run in parallel without overwriting each other's writes.
"""

import os
import urllib.parse

import boto3
import cv2
import numpy as np
from boto3.dynamodb.conditions import Key

REGION         = os.environ.get("REGION", "us-east-1")
TABLE_NAME     = os.environ.get("TABLE_NAME", "wildlife_files")
FILE_URL_INDEX = os.environ.get("FILE_URL_INDEX", "file-url-index")
MAX_DIM        = int(os.environ.get("THUMB_MAX_DIM", "300"))   # longest side, px
JPEG_QUALITY   = int(os.environ.get("JPEG_QUALITY", "70"))     # 0-100

UPLOADS_PREFIX    = "uploads/"
THUMBNAILS_PREFIX = "thumbnails/"

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}
VIDEO_EXTS = {"mp4", "mov", "avi", "mkv", "webm"}

s3    = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


def _resize_keep_aspect(img):
    """Downscale so the longest side == MAX_DIM, preserving aspect ratio.
    Never upscales a small image."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= MAX_DIM:
        return img
    scale = MAX_DIM / float(longest)
    new_size = (int(round(w * scale)), int(round(h * scale)))
    return cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)


def _encode_jpeg(img):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return buf.tobytes()


def _image_thumbnail(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("cv2 could not decode image bytes")
    return _encode_jpeg(_resize_keep_aspect(img))


def _video_thumbnail(data, key):
    """Write to /tmp, open with OpenCV, grab the middle frame (fallback: first)."""
    tmp_path = "/tmp/" + os.path.basename(key)
    with open(tmp_path, "wb") as f:
        f.write(data)
    try:
        cap = cv2.VideoCapture(tmp_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)   # middle frame
        ok, frame = cap.read()
        if not ok:                                          # fallback: first frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise RuntimeError("could not read any frame from video")
        return _encode_jpeg(_resize_keep_aspect(frame))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _thumb_key(src_key):
    """uploads/<id>/name.mp4  ->  thumbnails/<id>/name.jpg"""
    rest = src_key[len(UPLOADS_PREFIX):] if src_key.startswith(UPLOADS_PREFIX) else src_key
    root, _ = os.path.splitext(rest)
    return f"{THUMBNAILS_PREFIX}{root}.jpg"


def _set_thumbnail_url(file_url, thumb_url):
    """Find the record by file_url (GSI) and set ONLY thumbnail_url."""
    resp = table.query(
        IndexName=FILE_URL_INDEX,
        KeyConditionExpression=Key("file_url").eq(file_url),
    )
    items = resp.get("Items", [])
    if not items:
        print(f"WARN: no record found for {file_url}; skipping update")
        return
    table.update_item(
        Key={"file_id": items[0]["file_id"]},
        UpdateExpression="SET thumbnail_url = :t",
        ExpressionAttributeValues={":t": thumb_url},
    )


def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key    = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        # Guard: only handle originals under uploads/ (never thumbnails/).
        if not key.startswith(UPLOADS_PREFIX):
            continue

        ext  = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

        if ext in IMAGE_EXTS:
            thumb_bytes = _image_thumbnail(data)
        elif ext in VIDEO_EXTS:
            thumb_bytes = _video_thumbnail(data, key)
        else:
            print(f"WARN: unsupported extension '{ext}' for {key}; skipping")
            continue

        thumb_key = _thumb_key(key)
        s3.put_object(
            Bucket=bucket,
            Key=thumb_key,
            Body=thumb_bytes,
            ContentType="image/jpeg",
        )

        file_url  = f"s3://{bucket}/{key}"
        thumb_url = f"s3://{bucket}/{thumb_key}"
        _set_thumbnail_url(file_url, thumb_url)
        print(f"OK: thumbnail for {key} -> {thumb_key}")

    return {"statusCode": 200}
