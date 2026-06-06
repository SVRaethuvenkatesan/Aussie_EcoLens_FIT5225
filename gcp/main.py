import os
import json
import base64
import time
import hmac
import hashlib
import functions_framework
from google.cloud import storage

# Moved heavy ML imports to the global scope for faster warm-starts
import torch
import torchvision.transforms as transforms
import numpy as np
from PIL import Image
import io

classifier = None
classes = [
    'Alectura_lathami','Antechinus_agilis',
    'Bos_taurus','Burhinus_grallarius',
    'Canis_familiaris','Chalcophaps_longirostris',
    'Colluricincla_harmonica',
    'Corcorax_melanorhamphos',
    'Dacelo_novaeguineae','Dama_dama',
    'Eopsaltria_australis','Felis_catus',
    'Geopelia_humeralis','Gymnorhina_tibicen',
    'Homo_sapiens','Isoodon_macrourus',
    'Lepus_europaeus','Macropus_giganteus',
    'Menura_novaehollandiae','Mus_musculus',
    'Oryctolagus_cuniculus','Perameles_nasuta',
    'Pitta_versicolor','Rattus',
    'Rattus_fuscipes','Rattus_rattus',
    'Strepera_graculina','Sus_scrofa',
    'Tachyglossus_aculeatus','Thylogale_stigmatica',
    'Trichosurus_caninus','Trichosurus_cunninghami',
    'Trichosurus_vulpecula','Varanus_varius',
    'Vombatus_ursinus','Vulpes_vulpes',
    'Wallabia_bicolor','Canis_dingo',
    'Capra_hircus','Casuarius_casuarius',
    'Heteromyias_cinereifrons',
    'Hypsiprymnodon_moschatus',
    'Megapodius_reinwardt',
    'Notamacropus_rufogriseus',
    'Orthonyx_spaldingii','Uromys_caudimaculatus'
]

label_map = {
    'alectura_lathami':'australian brushturkey',
    'antechinus_agilis':'agile antechinus',
    'bos_taurus':'cattle',
    'burhinus_grallarius':'bush thick-knee',
    'canis_familiaris':'dingo',
    'canis_dingo':'dingo',
    'chalcophaps_longirostris':'pacific emerald dove',
    'colluricincla_harmonica':'grey shrikethrush',
    'corcorax_melanorhamphos':'white-winged chough',
    'dacelo_novaeguineae':'laughing kookaburra',
    'dama_dama':'fallow deer',
    'eopsaltria_australis':'eastern yellow robin',
    'felis_catus':'domestic cat',
    'geopelia_humeralis':'bar-shouldered dove',
    'gymnorhina_tibicen':'australian magpie',
    'homo_sapiens':'human',
    'isoodon_macrourus':'northern brown bandicoot',
    'lepus_europaeus':'european hare',
    'macropus_giganteus':'eastern gray kangaroo',
    'menura_novaehollandiae':'superb lyrebird',
    'mus_musculus':'house mouse',
    'oryctolagus_cuniculus':'european rabbit',
    'perameles_nasuta':'long-nosed bandicoot',
    'pitta_versicolor':'noisy pitta',
    'rattus':'rat',
    'rattus_fuscipes':'australian bush rat',
    'rattus_rattus':'black rat',
    'strepera_graculina':'pied currawong',
    'sus_scrofa':'wild boar',
    'tachyglossus_aculeatus':'australian echidna',
    'thylogale_stigmatica':'red-legged pademelon',
    'trichosurus_caninus':'short-eared possum',
    'trichosurus_cunninghami':'mountain brushtail opossum',
    'trichosurus_vulpecula':'common brushtail',
    'varanus_varius':'lace monitor',
    'vombatus_ursinus':'common wombat',
    'vulpes_vulpes':'red fox',
    'wallabia_bicolor':'swamp wallaby',
    'capra_hircus':'domestic goat',
    'casuarius_casuarius':'southern cassowary',
    'heteromyias_cinereifrons':'grey-headed robin',
    'hypsiprymnodon_moschatus':'musky rat kangaroo',
    'megapodius_reinwardt':'orange-footed scrubfowl',
    'notamacropus_rufogriseus':'red-necked wallaby',
    'orthonyx_spaldingii':'northern chowchilla',
    'uromys_caudimaculatus':'giant white-tailed rat'
}

def get_common_name(label):
    return label_map.get(label.lower(), label.lower())

def validate_request(data):
    """HMAC-based cross-cloud authentication"""
    secret    = os.environ.get('SECRET_KEY', 'aussie-ecolens-2026')
    token     = data.get('secret_key', '')
    timestamp = data.get('timestamp', 0)

    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        print("Invalid timestamp format")
        return False

    # Check timestamp within 5 minutes to prevent replay attacks
    if abs(time.time() - ts_int) > 300:
        print("Token expired")
        return False

    # Verify HMAC signature
    expected = hmac.new(
        secret.encode(),
        str(ts_int).encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(token, expected)

def load_classifier():
    global classifier
    if classifier is not None:
        return classifier
        
    bucket_name = os.environ.get('MODEL_BUCKET', 'aussie-ecolensmodels')
    model_file = os.environ.get('MODEL_FILE', 'model.pt')
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob   = bucket.blob(model_file)
    tmp    = f"/tmp/{model_file}"
    
    blob.download_to_filename(tmp)
    print(f"Downloaded {model_file}")
    
    model = torch.load(tmp, map_location='cpu', weights_only=False)
    model.eval()
    classifier = model
    print("Model loaded!")
    return classifier

@functions_framework.http
def detect_species(request):
    data = request.get_json(silent=True) or {}

    # HMAC validation
    if not validate_request(data):
        return json.dumps({'success': False, 'error': 'Unauthorized'}), 401

    image_b64 = data.get('image_data', '')
    if not image_b64:
        return json.dumps({'success': False, 'error': 'No image provided'}), 400

    try:
        image_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        print(f"Image size: {img.size}")

        transform = transforms.Compose([
            transforms.Resize((480, 480)),
            transforms.ToTensor(),
        ])

        tensor = transform(img)
        tensor = tensor.unsqueeze(0)
        tensor = tensor.permute(0, 2, 3, 1)

        model = load_classifier()
        with torch.no_grad():
            logits = model(tensor)
            probs  = torch.softmax(logits, dim=1)[0].cpu().numpy()

        order      = np.argsort(probs)[::-1]
        best_idx   = int(order[0])
        best_conf  = float(probs[best_idx])
        best_label = classes[best_idx]

        print(f"Top: {best_label} ({best_conf:.3f})")

        tags = {}
        if best_conf > 0.1:
            tags[get_common_name(best_label)] = 1

        if len(order) > 1:
            second_idx  = int(order[1])
            second_conf = float(probs[second_idx])
            if second_conf > 0.15:
                second = get_common_name(classes[second_idx])
                if second != get_common_name(best_label):
                    tags[second] = 1

        print(f"Tags: {tags}")
        return json.dumps({
            'success': True,
            'tags': tags
        }), 200

    except Exception as e:
        print(f"Processing Error: {str(e)}")
        # Returns success=False so AWS knows the tagging failed
        return json.dumps({
            'success': False,
            'error': str(e)
        }), 500
