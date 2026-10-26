import json
import os
from db import get_db

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "model", "class_names.json"), encoding="utf-8") as f:
    labels = json.load(f)


def healthy(crop):
    return (
        crop, "Healthy", 1,
        f"The {crop.lower()} leaf shows no visible signs of disease.",
        "No treatment needed. Keep up good practice: water at the base of the plant, "
        "keep spacing for airflow, remove dead leaves, and inspect plants regularly.",
    )


# label: (crop_name, disease_name, is_healthy, description, recommended_treatment)
DATA = {
    "Apple___Apple_scab": (
        "Apple", "Apple Scab", 0,
        "A fungal disease causing olive-green to brown velvety spots on leaves and rough, scabby patches on fruit. Worst in cool, wet spring weather.",
        "Rake and destroy fallen leaves, prune for airflow, and apply a protectant fungicide from bud break as directed on the label. Plant resistant varieties where possible.",
    ),
    "Apple___Black_rot": (
        "Apple", "Black Rot", 0,
        "A fungal disease causing 'frogeye' leaf spots with purple edges, rotting fruit and cankers on branches.",
        "Prune out cankers and dead wood, remove mummified fruit, and apply fungicide during the growing season as directed. Keep the orchard clean of debris.",
    ),
    "Apple___Cedar_apple_rust": (
        "Apple", "Cedar Apple Rust", 0,
        "A fungal disease causing bright yellow-orange spots on leaves, with small tube-like structures underneath. It needs nearby juniper or cedar trees to complete its life cycle.",
        "Remove nearby juniper or cedar if practical, apply fungicide from the pink bud stage as directed, and choose resistant apple varieties.",
    ),
    "Apple___healthy": healthy("Apple"),
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": (
        "Corn (Maize)", "Cercospora Leaf Spot / Gray Leaf Spot", 0,
        "A fungal disease causing narrow rectangular tan to gray lesions that run parallel to the leaf veins. Favoured by warm, humid weather.",
        "Rotate crops, bury or remove crop residue after harvest, and plant resistant hybrids. Apply foliar fungicide if the disease is severe before tasselling.",
    ),
    "Corn_(maize)___Common_rust_": (
        "Corn (Maize)", "Common Rust", 0,
        "A fungal disease causing small, round to elongated brick-red or brown pustules on both sides of the leaf.",
        "Plant resistant hybrids and plant early. Fungicide is only worth applying when infection is heavy on a susceptible variety.",
    ),
    "Corn_(maize)___Northern_Leaf_Blight": (
        "Corn (Maize)", "Northern Leaf Blight", 0,
        "A fungal disease causing long, cigar-shaped gray-green to tan lesions on the leaves, which can join together and kill large areas of leaf.",
        "Use resistant hybrids, rotate crops and manage crop residue. Apply fungicide if lesions appear on upper leaves before tasselling.",
    ),
    "Corn_(maize)___healthy": healthy("Corn (Maize)"),
    "Pepper__bell___Bacterial_spot": (
        "Pepper (Bell)", "Bacterial Spot", 0,
        "A bacterial disease causing small water-soaked spots that turn brown and may drop out, yellowing and leaf drop, and rough raised spots on fruit.",
        "Use disease-free seed and transplants, avoid overhead watering and working in wet fields, and rotate crops for 2 to 3 years. Copper sprays can slow spread but do not cure it. Remove infected plant debris.",
    ),
    "Pepper__bell___healthy": healthy("Pepper (Bell)"),
    "Potato___Early_blight": (
        "Potato", "Early Blight", 0,
        "A fungal disease causing dark brown spots with concentric rings, like a target, on older leaves, followed by yellowing.",
        "Rotate crops, use certified seed potatoes, keep plants well fed and watered, and remove debris. Apply a protectant fungicide at the first symptoms as directed.",
    ),
    "Potato___Late_blight": (
        "Potato", "Late Blight", 0,
        "A fast-spreading disease causing dark, water-soaked lesions on leaves and stems, often with white fuzzy growth underneath in humid weather. Tubers can rot.",
        "Act immediately. Remove and destroy infected plants and volunteer potatoes, use certified seed, avoid overhead irrigation, and apply preventive fungicide as directed.",
    ),
    "Potato___healthy": healthy("Potato"),
    "Tomato_Bacterial_spot": (
        "Tomato", "Bacterial Spot", 0,
        "A bacterial disease causing small dark water-soaked spots, often with yellow halos, on leaves and rough scabby spots on fruit.",
        "Use disease-free seed and transplants, avoid overhead watering, rotate crops, and remove infected debris. Copper sprays give only limited control.",
    ),
    "Tomato_Early_blight": (
        "Tomato", "Early Blight", 0,
        "A fungal disease causing brown spots with concentric rings on lower leaves, yellowing around the spots, and sometimes stem and fruit lesions.",
        "Remove infected lower leaves, mulch and stake plants, rotate crops, and apply fungicide at the first signs as directed.",
    ),
    "Tomato_Late_blight": (
        "Tomato", "Late Blight", 0,
        "A fast-spreading disease causing greasy gray-green lesions on leaves, white mould underneath in damp conditions, and firm brown rot on fruit.",
        "Remove and destroy infected plants (do not compost them), improve spacing and airflow, avoid wetting foliage, and apply preventive fungicide as directed.",
    ),
    "Tomato_Leaf_Mold": (
        "Tomato", "Leaf Mold", 0,
        "A fungal disease causing pale green or yellow spots on the upper leaf surface with olive-green to gray-purple mould underneath. Common in humid, poorly ventilated conditions.",
        "Improve ventilation, reduce humidity, avoid wetting leaves, use resistant varieties, and apply fungicide if needed as directed.",
    ),
    "Tomato_Septoria_leaf_spot": (
        "Tomato", "Septoria Leaf Spot", 0,
        "A fungal disease causing many small circular spots with dark borders and gray-white centres, starting on the lower leaves.",
        "Remove infected leaves, mulch to stop soil splash, rotate crops, avoid overhead watering, and apply fungicide as directed.",
    ),
    "Tomato_Spider_mites_Two_spotted_spider_mite": (
        "Tomato", "Spider Mites (Two-spotted Spider Mite)", 0,
        "A pest problem rather than a disease. Tiny mites cause yellow stippling, fine webbing and bronzing on leaves, mostly in hot, dry weather.",
        "Spray the underside of leaves with water, apply insecticidal soap or horticultural oil, avoid water stress, and protect natural predators. Use a miticide only if the infestation is severe.",
    ),
    "Tomato__Target_Spot": (
        "Tomato", "Target Spot", 0,
        "A fungal disease causing brown spots with concentric rings on leaves, and sometimes sunken spots on fruit.",
        "Rotate crops, improve airflow, remove infected debris, and apply fungicide as directed.",
    ),
    "Tomato__Tomato_YellowLeaf__Curl_Virus": (
        "Tomato", "Tomato Yellow Leaf Curl Virus", 0,
        "A virus spread by whiteflies. Leaves curl upward and turn yellow at the edges, plants are stunted, and flowers drop.",
        "There is no cure. Remove and destroy infected plants, control whiteflies with insect nets, reflective mulch or suitable sprays, control weeds, and plant tolerant varieties.",
    ),
    "Tomato__Tomato_mosaic_virus": (
        "Tomato", "Tomato Mosaic Virus", 0,
        "A virus causing mottled light and dark green patches on leaves, distorted leaf shape and reduced yield. It spreads by touch, tools and seed.",
        "There is no cure. Remove infected plants, wash hands and disinfect tools, avoid handling tobacco before touching plants, and use certified seed and resistant varieties.",
    ),
    "Tomato_healthy": healthy("Tomato"),
}

missing = [l for l in labels if l not in DATA]
extra = [l for l in DATA if l not in labels]
if missing or extra:
    print("MISSING:", missing)
    print("EXTRA:", extra)
    raise SystemExit("Fix the label mismatch before seeding.")

SQL = """
INSERT INTO tbl_disease
  (class_label, disease_name, crop_name, is_healthy, description, recommended_treatment)
VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  disease_name = VALUES(disease_name),
  crop_name = VALUES(crop_name),
  is_healthy = VALUES(is_healthy),
  description = VALUES(description),
  recommended_treatment = VALUES(recommended_treatment)
"""

conn = get_db()
with conn.cursor() as cur:
    for label in labels:
        crop, name, is_healthy, desc, treat = DATA[label]
        cur.execute(SQL, (label, name, crop, is_healthy, desc, treat))
    cur.execute("SELECT COUNT(*) AS n FROM tbl_disease")
    print(cur.fetchone()["n"], "rows in tbl_disease")
conn.close()