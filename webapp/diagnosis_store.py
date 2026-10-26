import io
import logging
import os
import uuid

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

from db import get_db

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

FOLDER = "leaflens"
logger = logging.getLogger(__name__)


def _upload_image(img):
    """Re-encode as JPEG (max 1024px), upload to Cloudinary, return (url, public_id)."""
    buf = io.BytesIO()
    out = img.copy()
    out.thumbnail((1024, 1024))
    out.save(buf, "JPEG", quality=88)
    buf.seek(0)
    result = cloudinary.uploader.upload(
        buf,
        folder=FOLDER,
        public_id=uuid.uuid4().hex,
        resource_type="image",
        timeout=30,
    )
    return result["secure_url"], result["public_id"]


def delete_image(url):
    """Delete a Cloudinary image from its stored URL and report whether it was removed."""
    try:
        tail = url.split("/upload/", 1)[1]
        parts = tail.split("/")
        if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
            parts = parts[1:]
        public_id = "/".join(parts).rsplit(".", 1)[0]
        result = cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception:
        logger.exception("Could not delete a Cloudinary image")
        return False
    if result.get("result") not in {"ok", "not found"}:
        logger.warning("Cloudinary did not confirm image deletion: %s", result.get("result"))
        return False
    return True


def save_diagnosis(user_id, img, label, confidence, crop_type=None):
    """Upload the image, then insert the request and prediction in one transaction.

    Returns (request_id, image_url). Raises on any failure; the uploaded image is
    removed again if the database write fails.
    """
    crop_type = (crop_type or "").strip()[:100] or None
    url, public_id = _upload_image(img)
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT disease_id FROM tbl_disease WHERE class_label = %s", (label,))
            disease = cur.fetchone()
            cur.execute("SELECT model_id FROM tbl_model_version ORDER BY model_id DESC LIMIT 1")
            model = cur.fetchone()
            if not disease or not model:
                raise LookupError("Seed data missing: check tbl_disease and tbl_model_version.")

            conn.begin()
            cur.execute(
                "INSERT INTO tbl_diagnosis_request (user_id, image_path, crop_type, status) "
                "VALUES (%s, %s, %s, 'completed')",
                (user_id, url, crop_type),
            )
            request_id = cur.lastrowid
            cur.execute(
                "INSERT INTO tbl_prediction_result (request_id, disease_id, model_id, confidence_score) "
                "VALUES (%s, %s, %s, %s)",
                (request_id, disease["disease_id"], model["model_id"], confidence),
            )
            conn.commit()
            return request_id, url
    except Exception:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        try:
            cloudinary.uploader.destroy(public_id, resource_type="image")
        except Exception:
            pass
        raise
    finally:
        if conn:
            conn.close()