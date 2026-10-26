"""Flask web app: plant disease detection with a ResNet18 model (ONNX Runtime)."""
from __future__ import annotations

from datetime import date, timedelta
import io
import json
import os

import numpy as np
import pymysql
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, abort, flash, jsonify, render_template, redirect, session, url_for, request
from PIL import Image, ImageOps
from werkzeug.security import check_password_hash, generate_password_hash

from disease_info import DEFAULT_INFO, DISEASE_INFO
from auth import auth_bp
from db import get_db
from utils import login_required
import diagnosis_store as store

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE, "model")
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.register_blueprint(auth_bp)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB uploads

_session = None
_classes: list[str] = []
_metrics: dict = {}


@app.context_processor
def inject_current_user_name():
    if "user_id" not in session:
        return {"current_user_first_name": ""}

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT first_name FROM tbl_users WHERE user_id = %s",
                (session["user_id"],),
            )
            user = cur.fetchone()
    except pymysql.MySQLError:
        app.logger.exception(
            "Could not refresh first name for user %s", session["user_id"]
        )
        first_name = session.get("first_name", "")
    else:
        first_name = user["first_name"] if user else ""
        if first_name:
            session["first_name"] = first_name
    finally:
        if conn:
            conn.close()

    return {"current_user_first_name": first_name}


def load_model():
    """Load the ONNX model once (lazily, so the page works while the model uploads)."""
    global _session, _classes, _metrics
    if _session is None:
        import onnxruntime as ort

        path = os.path.join(MODEL_DIR, "plant_resnet18.onnx")
        if not os.path.exists(path):
            raise FileNotFoundError("Model not uploaded yet. Run the Colab notebook to add model/plant_resnet18.onnx.")
        _session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        with open(os.path.join(MODEL_DIR, "class_names.json")) as f:
            _classes = json.load(f)
        mpath = os.path.join(MODEL_DIR, "metrics.json")
        if os.path.exists(mpath):
            with open(mpath) as f:
                _metrics = json.load(f)
    return _session


def preprocess(img: Image.Image) -> np.ndarray:
    """Same transform as training: resize 224x224, scale to [0,1], ImageNet normalize, NCHW."""
    x = np.asarray(img.resize((224, 224), Image.BILINEAR), dtype=np.float32) / 255.0
    x = (x - MEAN) / STD
    return x.transpose(2, 0, 1)[None].astype(np.float32)


def estimate_severity(img: Image.Image) -> float:
    """Percent of the leaf area that is discoloured (not green).

    Leaf pixels = saturated, non-background pixels in HSV space; diseased pixels =
    leaf pixels whose hue falls outside the healthy-green band (yellow/brown spots, lesions).
    """
    hsv = np.asarray(img.resize((256, 256)).convert("HSV"), dtype=np.float32)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    background = h > 185                         # blue/purple/magenta backdrops and shadows are never leaf tissue
    leaf = (s > 0.20) & (v > 0.18) & ~background
    if leaf.sum() < 500:
        return 0.0
    green = (h >= 65) & (h <= 170)
    diseased = leaf & ~green
    return round(float(diseased.sum() / leaf.sum() * 100), 1)


DISPLAY = {
    "Apple___Apple_scab": ("Apple", "Apple scab"),
    "Apple___Black_rot": ("Apple", "Black rot"),
    "Apple___Cedar_apple_rust": ("Apple", "Cedar apple rust"),
    "Apple___healthy": ("Apple", "Healthy"),
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": ("Corn (maize)", "Cercospora / gray leaf spot"),
    "Corn_(maize)___Common_rust_": ("Corn (maize)", "Common rust"),
    "Corn_(maize)___Northern_Leaf_Blight": ("Corn (maize)", "Northern leaf blight"),
    "Corn_(maize)___healthy": ("Corn (maize)", "Healthy"),
    "Pepper__bell___Bacterial_spot": ("Bell pepper", "Bacterial spot"),
    "Pepper__bell___healthy": ("Bell pepper", "Healthy"),
    "Potato___Early_blight": ("Potato", "Early blight"),
    "Potato___Late_blight": ("Potato", "Late blight"),
    "Potato___healthy": ("Potato", "Healthy"),
    "Tomato_Bacterial_spot": ("Tomato", "Bacterial spot"),
    "Tomato_Early_blight": ("Tomato", "Early blight"),
    "Tomato_Late_blight": ("Tomato", "Late blight"),
    "Tomato_Leaf_Mold": ("Tomato", "Leaf mold"),
    "Tomato_Septoria_leaf_spot": ("Tomato", "Septoria leaf spot"),
    "Tomato_Spider_mites_Two_spotted_spider_mite": ("Tomato", "Two-spotted spider mites"),
    "Tomato__Target_Spot": ("Tomato", "Target spot"),
    "Tomato__Tomato_YellowLeaf__Curl_Virus": ("Tomato", "Yellow leaf curl virus"),
    "Tomato__Tomato_mosaic_virus": ("Tomato", "Mosaic virus"),
    "Tomato_healthy": ("Tomato", "Healthy"),
}


def pretty(label: str) -> tuple[str, str]:
    return DISPLAY.get(label, (label.split("_")[0], label.replace("_", " ")))


@app.get("/")
def home():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("auth.login"))


@app.post("/api/predict")
@login_required
def predict():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="Please choose an image."), 400
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(file.read()))).convert("RGB")
    except Exception:
        return jsonify(error="That file isn't a readable image."), 400
    try:
        ort_session = load_model()
    except FileNotFoundError as exc:
        return jsonify(error=str(exc)), 503

    try:
        probs = ort_session.run(None, {"input": preprocess(img)})[0][0]
    except Exception:
        app.logger.exception("Prediction failed")
        return jsonify(error="The model could not analyse this image."), 500

    top = np.argsort(probs)[::-1][:3]
    label = _classes[int(top[0])]
    crop, disease = pretty(label)
    healthy = "healthy" in label.lower()
    info = DISEASE_INFO.get(label, DEFAULT_INFO)
    confidence = round(float(probs[top[0]]) * 100, 1)

    # Save to Cloudinary + MySQL. If saving fails, the diagnosis is still returned.
    saved = None
    try:
        saved = store.save_diagnosis(
            session["user_id"], img, label, confidence, request.form.get("crop_type")
        )
    except Exception:
        app.logger.exception("Could not save the diagnosis")

    return jsonify(
        saved=saved is not None,
        request_id=saved[0] if saved else None,
        image_url=saved[1] if saved else None,
        label=label,
        crop=crop,
        disease=disease,
        healthy=healthy,
        confidence=confidence,
        severity=0.0 if healthy else estimate_severity(img),
        yield_rate=info["yield_rate"],
        solution=info["solution"],
        top3=[{"crop": pretty(_classes[int(i)])[0], "disease": pretty(_classes[int(i)])[1],
               "p": round(float(probs[int(i)]) * 100, 1)} for i in top],
    )


@app.get("/api/model")
def model_info():
    try:
        load_model()
    except FileNotFoundError as exc:
        return jsonify(ready=False, error=str(exc))
    return jsonify(ready=True, classes=len(_classes), val_accuracy=_metrics.get("val_accuracy"),
                   val_images=_metrics.get("val_images"))


@app.get("/health")
def health():
    return "ok"


@app.get("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    stats = {
        "total": 0,
        "healthy": 0,
        "diseased": 0,
        "avg_confidence": 0,
        "low_confidence": 0,
        "top_disease": None,
        "crops": [],
        "daily": [],
        "recent": [],
    }
    dashboard_error = False
    today = date.today()
    first_day = today - timedelta(days=29)
    conn = None

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) AS total,
                          COALESCE(SUM(d.is_healthy = 1), 0) AS healthy,
                          COALESCE(SUM(d.is_healthy = 0), 0) AS diseased,
                          COALESCE(AVG(p.confidence_score), 0) AS avg_confidence,
                          COALESCE(SUM(p.confidence_score < 60), 0) AS low_confidence
                   FROM tbl_diagnosis_request r
                   JOIN tbl_prediction_result p ON p.request_id = r.request_id
                   JOIN tbl_disease d ON d.disease_id = p.disease_id
                   WHERE r.user_id = %s AND r.status = 'completed'""",
                (user_id,),
            )
            summary = cur.fetchone() or {}

            cur.execute(
                """SELECT d.crop_name AS crop, COUNT(*) AS count
                   FROM tbl_diagnosis_request r
                   JOIN tbl_prediction_result p ON p.request_id = r.request_id
                   JOIN tbl_disease d ON d.disease_id = p.disease_id
                   WHERE r.user_id = %s AND r.status = 'completed'
                   GROUP BY d.crop_name
                   ORDER BY count DESC, d.crop_name""",
                (user_id,),
            )
            crop_rows = cur.fetchall()

            cur.execute(
                """SELECT d.crop_name AS crop, d.disease_name AS name, COUNT(*) AS count
                   FROM tbl_diagnosis_request r
                   JOIN tbl_prediction_result p ON p.request_id = r.request_id
                   JOIN tbl_disease d ON d.disease_id = p.disease_id
                   WHERE r.user_id = %s AND r.status = 'completed'
                     AND d.is_healthy = 0
                   GROUP BY d.crop_name, d.disease_name
                   ORDER BY count DESC, d.crop_name, d.disease_name
                   LIMIT 1""",
                (user_id,),
            )
            top_disease = cur.fetchone()

            cur.execute(
                """SELECT DATE(r.upload_date) AS day, COUNT(*) AS count
                   FROM tbl_diagnosis_request r
                   JOIN tbl_prediction_result p ON p.request_id = r.request_id
                   WHERE r.user_id = %s AND r.status = 'completed'
                     AND r.upload_date >= %s AND r.upload_date < %s
                   GROUP BY DATE(r.upload_date)""",
                (user_id, first_day, today + timedelta(days=1)),
            )
            daily_rows = cur.fetchall()

            cur.execute(
                """SELECT r.image_path AS image_url, d.crop_name AS crop,
                          r.crop_type AS selected_crop,
                          d.disease_name AS disease, d.is_healthy,
                          p.confidence_score AS confidence, r.upload_date
                   FROM tbl_diagnosis_request r
                   JOIN tbl_prediction_result p ON p.request_id = r.request_id
                   JOIN tbl_disease d ON d.disease_id = p.disease_id
                   WHERE r.user_id = %s AND r.status = 'completed'
                   ORDER BY r.upload_date DESC, r.request_id DESC
                   LIMIT 5""",
                (user_id,),
            )
            recent_rows = cur.fetchall()

        stats.update(
            total=int(summary.get("total") or 0),
            healthy=int(summary.get("healthy") or 0),
            diseased=int(summary.get("diseased") or 0),
            avg_confidence=float(summary.get("avg_confidence") or 0),
            low_confidence=int(summary.get("low_confidence") or 0),
            crops=[
                {"crop": row["crop"], "count": int(row["count"])}
                for row in crop_rows
            ],
            daily=[
                {
                    "day": (first_day + timedelta(days=offset)).isoformat(),
                    "count": 0,
                }
                for offset in range(30)
            ],
            recent=[
                {
                    "image_url": row["image_url"],
                    "crop": row["crop"],
                    "selected_crop": row["selected_crop"] or "Not selected",
                    "disease": "Healthy" if row["is_healthy"] else row["disease"],
                    "confidence": round(float(row["confidence"] or 0)),
                    "date": row["upload_date"].strftime("%b %d, %Y"),
                }
                for row in recent_rows
            ],
        )
        if top_disease:
            stats["top_disease"] = {
                "crop": top_disease["crop"],
                "name": top_disease["name"],
                "count": int(top_disease["count"]),
            }

        daily_counts = {row["day"].isoformat(): int(row["count"]) for row in daily_rows}
        for item in stats["daily"]:
            item["count"] = daily_counts.get(item["day"], 0)
    except Exception:
        app.logger.exception("Could not load dashboard data for user %s", user_id)
        dashboard_error = True
    finally:
        if conn:
            conn.close()

    return render_template(
        "dashboard.html", stats=stats, dashboard_error=dashboard_error
    )


@app.get("/upload")
@login_required
def upload():
    examples = sorted(os.listdir(os.path.join(BASE, "static", "examples")))
    return render_template("upload.html", examples=examples)


@app.get("/history")
@login_required
def history():
    user_id = session["user_id"]
    query = request.args.get("q", "").strip()[:100]
    crop = request.args.get("crop", "").strip()[:100]
    result = request.args.get("result", "all")
    if result not in {"all", "healthy", "diseased"}:
        result = "all"
    sort = request.args.get("sort", "newest")
    if sort not in {"newest", "oldest"}:
        sort = "newest"

    filters = {"q": query, "crop": crop, "result": result, "sort": sort}
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 10
    where = ["r.user_id = %s"]
    params = [user_id]

    if query:
        where.append(
            "(d.crop_name LIKE %s OR r.crop_type LIKE %s OR d.disease_name LIKE %s)"
        )
        search_term = f"%{query}%"
        params.extend([search_term, search_term, search_term])
    if crop:
        where.append("(d.crop_name = %s OR r.crop_type = %s)")
        params.extend([crop, crop])
    if result == "healthy":
        where.append("r.status = 'completed' AND d.is_healthy = 1")
    elif result == "diseased":
        where.append("r.status = 'completed' AND d.is_healthy = 0")

    from_clause = """FROM tbl_diagnosis_request r
        LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id
        LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id"""
    where_clause = " AND ".join(where)
    items = []
    crop_options = []
    total = 0
    pages = 1
    history_error = False
    conn = None

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT crop_name AS crop FROM tbl_disease
                   UNION
                   SELECT crop_type AS crop FROM tbl_diagnosis_request
                   WHERE user_id = %s AND crop_type IS NOT NULL AND crop_type <> ''
                   ORDER BY crop""",
                (user_id,),
            )
            crop_options = [row["crop"] for row in cur.fetchall()]

            cur.execute(
                f"SELECT COUNT(*) AS total {from_clause} WHERE {where_clause}",
                tuple(params),
            )
            total = int((cur.fetchone() or {}).get("total") or 0)
            pages = max(1, (total + per_page - 1) // per_page)
            page = min(page, pages)
            direction = "ASC" if sort == "oldest" else "DESC"
            cur.execute(
                f"""SELECT r.request_id, r.image_path AS image_url,
                           COALESCE(d.crop_name, r.crop_type, 'Unknown') AS crop,
                           r.crop_type AS selected_crop, d.disease_name AS disease,
                           d.is_healthy, p.confidence_score AS confidence,
                           r.status, r.upload_date
                    {from_clause}
                    WHERE {where_clause}
                    ORDER BY r.upload_date {direction}, r.request_id {direction}
                    LIMIT %s OFFSET %s""",
                tuple(params + [per_page, (page - 1) * per_page]),
            )
            rows = cur.fetchall()

        items = [
            {
                "request_id": row["request_id"],
                "image_url": row["image_url"],
                "crop": row["crop"],
                "selected_crop": row["selected_crop"] or "Not selected",
                "disease": row["disease"] or "",
                "is_healthy": bool(row["is_healthy"]),
                "confidence": float(row["confidence"] or 0),
                "status": row["status"],
                "date": row["upload_date"].strftime("%b %d, %Y"),
            }
            for row in rows
        ]
    except Exception:
        app.logger.exception("Could not load history for user %s", user_id)
        history_error = True
    finally:
        if conn:
            conn.close()

    return render_template(
        "history.html",
        items=items,
        page=page,
        pages=pages,
        total=total,
        filters=filters,
        crop_options=crop_options,
        history_error=history_error,
    )


@app.get("/history/<int:request_id>")
@login_required
def history_detail(request_id):
    conn = None
    diagnosis = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT r.request_id, r.image_path AS image_url,
                          r.crop_type AS crop_type_entered,
                          COALESCE(d.crop_name, r.crop_type, 'Unknown') AS crop,
                          d.disease_name AS disease, d.is_healthy,
                          p.confidence_score AS confidence, d.description,
                          d.recommended_treatment AS treatment,
                          m.model_version, r.upload_date, r.status
                   FROM tbl_diagnosis_request r
                   LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id
                   LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id
                   LEFT JOIN tbl_model_version m ON m.model_id = p.model_id
                   WHERE r.request_id = %s AND r.user_id = %s""",
                (request_id, session["user_id"]),
            )
            diagnosis = cur.fetchone()
    except Exception:
        app.logger.exception(
            "Could not load diagnosis %s for user %s",
            request_id,
            session["user_id"],
        )
        abort(503)
    finally:
        if conn:
            conn.close()

    if not diagnosis:
        abort(404)

    diagnosis["is_healthy"] = bool(diagnosis["is_healthy"])
    diagnosis["confidence"] = float(diagnosis["confidence"] or 0)
    diagnosis["disease"] = diagnosis["disease"] or (
        "Analysis in progress" if diagnosis["status"] == "pending" else "Analysis failed"
    )
    diagnosis["description"] = diagnosis["description"] or ""
    diagnosis["treatment"] = diagnosis["treatment"] or ""
    diagnosis["model_version"] = diagnosis["model_version"] or "Not available"
    diagnosis["date"] = diagnosis["upload_date"].strftime("%b %d, %Y")
    return render_template("history_detail.html", d=diagnosis)


@app.post("/history/<int:request_id>/delete")
@login_required
def history_delete(request_id):
    conn = None
    diagnosis = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM tbl_diagnosis_request WHERE request_id = %s AND user_id = %s",
                (request_id, session["user_id"]),
            )
            diagnosis = cur.fetchone()
            if diagnosis:
                cur.execute(
                    "DELETE FROM tbl_diagnosis_request WHERE request_id = %s AND user_id = %s",
                    (request_id, session["user_id"]),
                )
        if diagnosis:
            conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        app.logger.exception(
            "Could not delete diagnosis %s for user %s",
            request_id,
            session["user_id"],
        )
        flash("Could not delete this diagnosis. Please try again.", "error")
        return redirect(url_for("history"))
    finally:
        if conn:
            conn.close()

    if not diagnosis:
        abort(404)

    if not store.delete_image(diagnosis["image_path"]):
        flash("Diagnosis deleted, but its stored image could not be removed.", "error")
        return redirect(url_for("history"))
    flash("Diagnosis deleted.", "success")
    return redirect(url_for("history"))


@app.get("/profile")
@login_required
def profile():
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            profile_data = _fetch_profile(cur, session["user_id"])
    except pymysql.MySQLError:
        app.logger.exception("Could not load profile for user %s", session["user_id"])
        abort(503)
    finally:
        if conn:
            conn.close()

    if not profile_data:
        session.clear()
        flash("Your account could not be found. Please log in again.", "error")
        return redirect(url_for("auth.login"))

    profile_data["date_registered"] = _profile_date(profile_data["date_registered"])
    profile_data["last_scan"] = _profile_date(profile_data["last_scan"], abbreviated=True)
    return render_template("profile.html", profile=profile_data)


def _fetch_profile(cur, user_id):
    cur.execute(
        """SELECT u.first_name, u.last_name, u.email, u.phone_number, u.role,
                  u.date_registered, COUNT(r.request_id) AS total_scans,
                  MAX(r.upload_date) AS last_scan
           FROM tbl_users u
           LEFT JOIN tbl_diagnosis_request r ON r.user_id = u.user_id
           WHERE u.user_id = %s
           GROUP BY u.user_id, u.first_name, u.last_name, u.email,
                    u.phone_number, u.role, u.date_registered""",
        (user_id,),
    )
    return cur.fetchone()


def _profile_date(value, abbreviated=False):
    if value is None:
        return None
    month = value.strftime("%b" if abbreviated else "%B")
    return f"{month} {value.day}, {value.year}"


@app.post("/profile/update")
@login_required
def profile_update():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone_number = request.form.get("phone_number", "").strip() or None
    role = request.form.get("role", "")
    errors = []

    if not first_name or len(first_name) > 50:
        errors.append("First name is required (50 characters max).")
    if not last_name or len(last_name) > 50:
        errors.append("Last name is required (50 characters max).")
    if phone_number and len(phone_number) > 20:
        errors.append("Phone number is too long (20 characters max).")
    if role not in {"farmer", "extension_worker"}:
        errors.append("Choose a valid role.")

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            profile_data = _fetch_profile(cur, session["user_id"])
            if profile_data and not errors:
                cur.execute(
                    """UPDATE tbl_users
                       SET first_name = %s, last_name = %s, phone_number = %s, role = %s
                       WHERE user_id = %s""",
                    (first_name, last_name, phone_number, role, session["user_id"]),
                )
    except pymysql.MySQLError:
        app.logger.exception("Could not update profile for user %s", session["user_id"])
        flash("Could not save your profile. Please try again.", "error")
        return redirect(url_for("profile"))
    finally:
        if conn:
            conn.close()

    if not profile_data:
        session.clear()
        flash("Your account could not be found. Please log in again.", "error")
        return redirect(url_for("auth.login"))
    if errors:
        for error in errors:
            flash(error, "error")
        profile_data["date_registered"] = _profile_date(profile_data["date_registered"])
        profile_data["last_scan"] = _profile_date(profile_data["last_scan"], abbreviated=True)
        return render_template("profile.html", profile=profile_data), 400

    session["first_name"] = first_name
    session["role"] = role
    flash("Profile updated.", "success")
    return redirect(url_for("profile"))


@app.post("/profile/password")
@login_required
def profile_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if len(new_password) < 8 or len(new_password) > 128:
        flash("Password must be 8 to 128 characters.", "error")
        return redirect(url_for("profile"))
    if new_password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("profile"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM tbl_users WHERE user_id = %s",
                (session["user_id"],),
            )
            user = cur.fetchone()
            if not user:
                session.clear()
                flash("Your account could not be found. Please log in again.", "error")
                return redirect(url_for("auth.login"))
            if not check_password_hash(user["password_hash"], current_password):
                flash("Your current password is incorrect.", "error")
                return redirect(url_for("profile"))
            cur.execute(
                "UPDATE tbl_users SET password_hash = %s WHERE user_id = %s",
                (generate_password_hash(new_password), session["user_id"]),
            )
    except pymysql.MySQLError:
        app.logger.exception("Could not update password for user %s", session["user_id"])
        flash("Could not update your password. Please try again.", "error")
        return redirect(url_for("profile"))
    finally:
        if conn:
            conn.close()

    flash("Password updated.", "success")
    return redirect(url_for("profile"))


@app.post("/profile/delete")
@login_required
def profile_delete():
    if request.form.get("confirm_delete") != "yes":
        flash("Confirm that you understand this action cannot be undone.", "error")
        return redirect(url_for("profile"))

    conn = None
    try:
        conn = get_db()
        conn.begin()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM tbl_users WHERE user_id = %s FOR UPDATE",
                (session["user_id"],),
            )
            user = cur.fetchone()
            if not user:
                session.clear()
                flash("Your account could not be found. Please log in again.", "error")
                return redirect(url_for("auth.login"))
            if not check_password_hash(user["password_hash"], request.form.get("password", "")):
                flash("Your password is incorrect.", "error")
                return redirect(url_for("profile"))

            cur.execute(
                "SELECT image_path FROM tbl_diagnosis_request WHERE user_id = %s",
                (session["user_id"],),
            )
            image_paths = [row["image_path"] for row in cur.fetchall()]
            cur.execute("DELETE FROM tbl_users WHERE user_id = %s", (session["user_id"],))
        conn.commit()
    except pymysql.MySQLError:
        if conn:
            conn.rollback()
        app.logger.exception("Could not delete account for user %s", session["user_id"])
        flash("Could not delete your account. Please try again.", "error")
        return redirect(url_for("profile"))
    finally:
        if conn:
            conn.close()

    image_cleanup_failed = False
    for image_path in image_paths:
        if not store.delete_image(image_path):
            image_cleanup_failed = True
    session.clear()
    if image_cleanup_failed:
        flash(
            "Your account and diagnosis history were deleted, but some stored images could not be removed.",
            "error",
        )
    else:
        flash("Your account and diagnosis history have been deleted.", "success")
    return redirect(url_for("auth.login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)