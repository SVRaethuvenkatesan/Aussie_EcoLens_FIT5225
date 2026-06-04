import base64
import io
import os
import uuid
import json
from collections import defaultdict
from flask import Flask, request, jsonify
from PIL import Image
import numpy as np
import torch
import torchvision.transforms as transforms

# Import the MegaDetector routine
from megadetector.detection import run_detector_batch

# Google Cloud storage bucket
from google.cloud import storage

app = Flask(__name__)

# ==============================================================================
# 1. CONFIG & INITIALISATION
# ==============================================================================
if torch.cuda.is_available():
    DEVICE = "cuda"
elif torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"
print(f"--> Hosting inference runtime on architecture device: {DEVICE}")

MD_MODEL_PATH = "./mdv5a.pt"
SPECIES_MODEL_PATH = "./model.pt"
BUCKET_NAME = "ecolens-model-weights"  # bucket containing the two .pt files

def download_weight_file(blob_name, destination_path):
    """Downloads a model weight file from GCS to the local container disk if not present."""
    if not os.path.exists(destination_path):
        print(f"--> Target {blob_name} missing locally. Downloading from GCS bucket {BUCKET_NAME}...")
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(destination_path)
        print(f"--> Successfully downloaded {blob_name} to {destination_path}.")
    else:
        print(f"--> {blob_name} already exists locally. Skipping download.")

download_weight_file("mdv5a.pt", MD_MODEL_PATH)
download_weight_file("model.pt", SPECIES_MODEL_PATH)

print("--> Initializing SpeciesNet Model...")
species_model = torch.load(SPECIES_MODEL_PATH, map_location=DEVICE, weights_only=False)
species_model.eval()

# supported classes in the model
CLASSES = [
    'Alectura_lathami', 'Antechinus_agilis', 'Bos_taurus', 'Burhinus_grallarius', 'Canis_familiaris', 
    'Chalcophaps_longirostris', 'Colluricincla_harmonica', 'Corcorax_melanorhamphos', 'Dacelo_novaeguineae', 
    'Dama_dama', 'Eopsaltria_australis', 'Felis_catus', 'Geopelia_humeralis', 'Gymnorhina_tibicen', 
    'Homo_sapiens', 'Isoodon_macrourus', 'Lepus_europaeus', 'Macropus_giganteus', 'Menura_novaehollandiae', 
    'Mus_musculus', 'Oryctolagus_cuniculus', 'Perameles_nasuta', 'Pitta_versicolor', 'Rattus', 
    'Rattus_fuscipes', 'Rattus_rattus', 'Strepera_graculina', 'Sus_scrofa', 'Tachyglossus_aculeatus', 
    'Thylogale_stigmatica', 'Trichosurus_caninus', 'Trichosurus_cunninghami', 'Trichosurus_vulpecula', 
    'Varanus_varius', 'Vombatus_ursinus', 'Vulpes_vulpes', 'Wallabia_bicolor', 'Canis_dingo', 
    'Capra_hircus', 'Casuarius_casuarius', 'Heteromyias_cinereifrons', 'Hypsiprymnodon_moschatus', 
    'Megapodius_reinwardt', 'Notamacropus_rufogriseus', 'Orthonyx_spaldingii', 'Uromys_caudimaculatus'
]

# Transform to be applied on the images before applying the model
transform_pipeline = transforms.Compose([
    transforms.Resize((480, 480)),
    transforms.ToTensor(),
])

CONF_THRESH = 0.05
SNIP_SIZE = 600


# ==============================================================================
# 2. CORE INFERENCE WORKFLOW
# ==============================================================================
def run_pipeline(image_bytes, filename):
    """Processes a single image through MegaDetector and SpeciesNet."""
    detected_counts = defaultdict(int)

    temp_filename = f"/tmp/{uuid.uuid4()}_{filename}"
    with open(temp_filename, "wb") as f:
        f.write(image_bytes)

    try:
        # Step A: Execute MegaDetector bounding box search
        md_results = run_detector_batch.load_and_run_detector_batch(
            image_file_names=[temp_filename], 
            model_file=MD_MODEL_PATH
        )

        if not md_results or len(md_results) == 0:
            return {}

        entry = md_results[0]
        detections = entry.get("detections", [])

        # open img via PIL
        img_pil = Image.open(temp_filename).convert("RGB")
        W, H = img_pil.size

        # Step B: Loop over detected entities
        for detection in detections:
            # Category "1" signifies an animal detection
            if detection.get("category") != "1":
                continue

            conf = detection.get("conf", 0.0)
            if conf < CONF_THRESH:
                continue

            # Bounding box coordinates are normalized floats (0.0 to 1.0)
            x, y, w, h = detection["bbox"]
            left = int(x * W)
            top = int(y * H)
            right = int((x + w) * W)
            bottom = int((y + h) * H)

            # Performance optimization: crop bounding area in volatile memory
            crop = img_pil.crop((left, top, right, bottom))

            # Resize rectangular crop
            resized_crop = crop.resize((SNIP_SIZE, SNIP_SIZE), Image.BILINEAR)

            # Step C: Formulate PyTorch Tensor 
            tensor_img = transform_pipeline(resized_crop)          # -> C, H, W
            tensor_img = tensor_img.unsqueeze(0)                  # -> B, C, H, W
            tensor_img = tensor_img.permute(0, 2, 3, 1)            # -> B, H, W, C (Channels-Last)
            tensor_img = tensor_img.to(DEVICE)

            # Step D: Execute SpeciesNet evaluation
            with torch.no_grad():
                logits = species_model(tensor_img)
                probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

            best_idx = np.argsort(probs)[::-1][0]
            predicted_species = CLASSES[best_idx]

            # Register detection 
            detected_counts[predicted_species] += 1

    finally:
        # clean up the storage file to avoid disk saturation
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

    return dict(detected_counts)


# ==============================================================================
# 3. WEB ROUTING LAYER (Flask API)
# ==============================================================================
@app.route("/", methods=["POST"])
def handler():
    try:
        request_json = request.get_json(silent=True)
        if not request_json or "image_base64" not in request_json:
            return jsonify({"success": False, "error": "Missing image_base64 parameter"}), 400

        # unpack incoming parameters sent by AWS' tagging handler
        filename = request_json.get("filename", "sensor_capture.jpg")
        image_b64 = request_json["image_base64"]
        image_bytes = base64.b64decode(image_b64)

        tags_output = run_pipeline(image_bytes, filename)
        return jsonify({"tags": tags_output}), 200

    except Exception as e:
        print(f"RUNTIME EXCEPTION: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)