"""

Responsibilities:
  - Read the uploaded file from S3.
  - Get species detections from the GCP detector:
      * image -> one GCP call.
      * video -> extract 1 frame/second, call GCP per frame, then aggregate
                 counts across frames (MAX per species - see _aggregate()).
  - Write the resulting {species: count} map to DynamoDB ('tags') and set
    status = "complete".
  - Asynchronously invoke notification-handler with the detected tags.

It updates ONLY 'tags' and 'status' - thumbnail-generator owns 'thumbnail_url',
so the two run in parallel without clobbering each other.

================================================================================
THREE THINGS TO CONFIRM WITH WHOEVER OWNS THE GCP FUNCTION  (search "ADJUST")
  1. _call_gcp_detector(): what the GCP endpoint expects in the request.
  2. _parse_gcp_response(): the exact JSON shape it returns.
  3. Label format: does GCP return common names ("wombat") or scientific
     ("Vombatus_ursinus")?  Queries use the names users type, so the tags you
     STORE must be in that vocabulary. Set NORMALISE_TO_COMMON accordingly.
================================================================================
"""

import base64
import json
import os
import urllib.request
from collections import defaultdict

import boto3
from boto3.dynamodb.conditions import Key  # noqa: F401  (handy if you extend)

REGION                 = os.environ.get("REGION", "us-east-1")
TABLE_NAME             = os.environ.get("TABLE_NAME", "wildlife_files")
# >>> ADJUST: set this env var to your deployed GCP detector URL.
GCP_DETECTOR_URL       = os.environ.get("GCP_DETECTOR_URL", "")
GCP_TIMEOUT            = int(os.environ.get("GCP_TIMEOUT", "120"))  # seconds
NOTIFY_FUNCTION_NAME   = os.environ.get("NOTIFY_FUNCTION_NAME", "notification-handler")

# Video sampling: 1 frame per second (per the brief), with a safety cap so a
# very long clip can't make thousands of GCP calls.
VIDEO_MAX_SAMPLES = int(os.environ.get("VIDEO_MAX_SAMPLES", "120"))

# If GCP returns scientific labels but queries use common names, flip this on
# and bundle labels.txt next to this file. Left off by default = store GCP's
# labels verbatim.
NORMALISE_TO_COMMON = os.environ.get("NORMALISE_TO_COMMON", "false").lower() == "true"

s3    = boto3.client("s3", region_name=REGION)
lam   = boto3.client("lambda", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


# --------------------------------------------------------------------------
# Optional label normalisation (Genus_species -> common name) via labels.txt
# labels.txt line format: uuid;class;order;family;genus;species;common_name
# --------------------------------------------------------------------------
def _load_common_name_map():
    mapping = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "labels.txt")) as f:
            for line in f:
                parts = line.strip().split(";")
                if len(parts) >= 7:
                    genus, species, common = parts[3], parts[4], parts[6]
                    if genus and species and common:
                        key = f"{genus}_{species}".lower()   # "vombatus_ursinus"
                        mapping[key] = common.lower()         # "common wombat"
    except FileNotFoundError:
        print("WARN: labels.txt not found; storing labels verbatim")
    return mapping

_COMMON = _load_common_name_map() if NORMALISE_TO_COMMON else {}


def _normalise(label):
    if NORMALISE_TO_COMMON:
        return _COMMON.get(label.lower(), label.lower())
    return label


# --------------------------------------------------------------------------
# GCP detector call  (ONE image -> {species: count})
# --------------------------------------------------------------------------
def _call_gcp_detector(image_bytes, filename):
    """POST one image to the GCP detector and return {species: count}."""
    if not GCP_DETECTOR_URL:
        raise RuntimeError("GCP_DETECTOR_URL is not set")

    # >>> ADJUST (1): match what your GCP endpoint actually expects.
    # Default assumption: JSON with a base64 image.
    body = json.dumps({
        "filename": filename,
        "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
    }).encode("utf-8")

    req = urllib.request.Request(
        GCP_DETECTOR_URL, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=GCP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return _parse_gcp_response(raw)


def _parse_gcp_response(raw):
    """Normalise the GCP reply into {species: count}.

    >>> ADJUST (2): tighten this to your endpoint's real shape. It currently
    tolerates several common formats:
      A) {"tags": {"wombat": 2}}            (already counted)
      B) {"species_counts": {"wombat": 2}}
      C) {"detections": ["Vombatus_ursinus", "Vombatus_ursinus"]}  (list -> count)
      D) ["wombat", "wombat", "magpie"]      (bare list -> count)
    """
    data = json.loads(raw)

    counts = defaultdict(int)
    if isinstance(data, dict):
        for k in ("tags", "species_counts", "counts"):
            if isinstance(data.get(k), dict):
                for sp, c in data[k].items():
                    counts[_normalise(sp)] += int(c)
                return dict(counts)
        listing = data.get("detections") or data.get("species") or []
    elif isinstance(data, list):
        listing = data
    else:
        listing = []

    for sp in listing:                      # list of labels -> tally
        counts[_normalise(str(sp))] += 1
    return dict(counts)


# --------------------------------------------------------------------------
# Video: extract ~1 frame/second, encode each as JPEG bytes
# --------------------------------------------------------------------------
def _extract_frames_1fps(video_bytes, key):
    import cv2  # imported lazily so image-only deployments don't need OpenCV

    tmp_path = "/tmp/" + os.path.basename(key)
    with open(tmp_path, "wb") as f:
        f.write(video_bytes)
    frames = []
    try:
        cap = cv2.VideoCapture(tmp_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        step = max(1, int(round(fps)))      # one sample per ~second
        idx = 0
        while len(frames) < VIDEO_MAX_SAMPLES:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                ok2, buf = cv2.imencode(".jpg", frame)
                if ok2:
                    frames.append(buf.tobytes())
            idx += 1
        cap.release()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return frames


def _aggregate(frame_counts):
    """Combine per-frame {species: count} dicts into one.

    Uses MAX per species across frames (not sum). Summing would massively
    overcount - one wombat standing still for 30s would read as 30 wombats -
    so max approximates the number of distinct individuals seen. This is a
    defensible design choice; be ready to justify it in the demo.
    """
    merged = defaultdict(int)
    for fc in frame_counts:
        for sp, c in fc.items():
            merged[sp] = max(merged[sp], int(c))
    return dict(merged)


# --------------------------------------------------------------------------
# Handler
# --------------------------------------------------------------------------
def lambda_handler(event, context):
    file_id   = event["file_id"]
    bucket    = event["bucket"]
    key       = event["key"]
    file_type = event.get("file_type", "image")
    filename  = os.path.basename(key)

    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    if file_type == "video":
        # If your GCP endpoint accepts a whole video, replace this block with a
        # single _call_gcp_detector(data, filename).
        frames = _extract_frames_1fps(data, key)
        print(f"video {key}: sampled {len(frames)} frames at ~1 fps")
        per_frame = [_call_gcp_detector(f, filename) for f in frames]
        tags = _aggregate(per_frame)
    else:
        tags = _call_gcp_detector(data, filename)

    print(f"{file_id} detected tags: {tags}")

    # ---- Write ONLY tags + status (thumbnail-generator owns thumbnail_url) ----
    table.update_item(
        Key={"file_id": file_id},
        UpdateExpression="SET tags = :t, #s = :st",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":t": tags, ":st": "complete"},
    )

    # ---- Notify only AFTER tags exist (a tag-based notification needs tags) ----
    try:
        lam.invoke(
            FunctionName=NOTIFY_FUNCTION_NAME,
            InvocationType="Event",
            # >>> ADJUST (notification payload): match notification-handler's input.
            Payload=json.dumps({"file_id": file_id, "tags": tags}).encode("utf-8"),
        )
    except Exception as exc:
        print(f"WARN: could not invoke {NOTIFY_FUNCTION_NAME}: {exc}")

    return {"statusCode": 200, "file_id": file_id, "tags": tags}
