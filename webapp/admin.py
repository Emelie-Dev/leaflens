import csv
import io
import re
import secrets
from datetime import date, timedelta
from functools import wraps

import pymysql
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
import diagnosis_store

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLE_CHOICES = ("farmer", "extension_worker")


def _decimal_to_number(value, default=0):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    if hasattr(value, "__float__"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _ensure_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@admin_bp.app_context_processor
def csrf_token():
    return {"csrf_token": _ensure_csrf_token}


@admin_bp.before_request
def enforce_admin_csrf():
    if request.method != "POST":
        return None
    token = request.form.get("csrf_token", "")
    expected = session.get("csrf_token")
    if not expected or token != expected:
        return "Invalid request.", 400
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            if "user_id" in session:
                return redirect(url_for("dashboard"))
            return redirect(url_for("admin.login"))

        conn = None
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute("SELECT admin_id FROM tbl_administrators WHERE admin_id = %s", (session["admin_id"],))
                if not cur.fetchone():
                    session.clear()
                    return redirect(url_for("admin.login"))
        except pymysql.MySQLError:
            current_app.logger.exception("Unable to verify admin session")
            flash("Could not verify access.", "error")
            return redirect(url_for("admin.login"))
        finally:
            if conn:
                conn.close()
        return view(*args, **kwargs)

    return wrapped


def _format_date(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return value.strftime("%b %d, %Y")
    except (AttributeError, TypeError):
        return str(value)


def _paginate(page, total, per_page=10):
    page = max(1, int(page or 1))
    pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > pages:
        page = pages
    return page, pages


def _safe_form_value(form_data, field, default=""):
    if not form_data:
        return default
    return str(form_data.get(field, default) or default)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if "admin_id" in session:
        return redirect(url_for("admin.dashboard"))
    if request.method == "GET":
        return render_template("admin/login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    conn = None
    admin = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT admin_id, first_name, last_name, email, password_hash FROM tbl_administrators WHERE email = %s",
                (email,),
            )
            admin = cur.fetchone()
    except pymysql.MySQLError:
        current_app.logger.exception("Admin login query failed")
        flash("Invalid email or password.", "error")
        return render_template("admin/login.html", form_data=request.form.to_dict()), 401
    finally:
        if conn:
            conn.close()

    if not admin or not check_password_hash(admin["password_hash"], password):
        flash("Invalid email or password.", "error")
        return render_template("admin/login.html", form_data=request.form.to_dict()), 401

    session.clear()
    session["admin_id"] = admin["admin_id"]
    session["admin_name"] = f"{admin['first_name']} {admin['last_name']}".strip()
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("admin.dashboard"))


@admin_bp.get("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.get("")
@admin_required
def dashboard():
    today = date.today()
    start = today - timedelta(days=29)
    stats = {
        "total_users": 0,
        "new_users": 0,
        "total_diagnoses": 0,
        "diagnoses_30d": 0,
        "healthy": 0,
        "diseased": 0,
        "avg_confidence": 0.0,
        "low_confidence": 0,
        "disease_count": 0,
        "daily": [],
        "top_diseases": [],
        "crop_distribution": [],
        "latest_diagnoses": [],
        "new_users_list": [],
    }
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM tbl_users")
            stats["total_users"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT COUNT(*) AS total FROM tbl_users WHERE date_registered >= %s",
                (start.strftime("%Y-%m-%d"),),
            )
            stats["new_users"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute("SELECT COUNT(*) AS total FROM tbl_diagnosis_request")
            stats["total_diagnoses"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT COUNT(*) AS total FROM tbl_diagnosis_request WHERE upload_date >= %s",
                (start.strftime("%Y-%m-%d"),),
            )
            stats["diagnoses_30d"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT COALESCE(SUM(CASE WHEN d.is_healthy = 1 THEN 1 ELSE 0 END), 0) AS healthy, COALESCE(SUM(CASE WHEN d.is_healthy = 0 THEN 1 ELSE 0 END), 0) AS diseased FROM tbl_diagnosis_request r LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE r.status = 'completed'"
            )
            summary = cur.fetchone() or {}
            stats["healthy"] = _decimal_to_number(summary.get("healthy"), 0)
            stats["diseased"] = _decimal_to_number(summary.get("diseased"), 0)

            cur.execute(
                "SELECT AVG(p.confidence_score) AS avg_confidence, SUM(CASE WHEN p.confidence_score < 60 THEN 1 ELSE 0 END) AS low_confidence FROM tbl_prediction_result p JOIN tbl_diagnosis_request r ON r.request_id = p.request_id WHERE r.status = 'completed'"
            )
            summary = cur.fetchone() or {}
            stats["avg_confidence"] = _decimal_to_number(summary.get("avg_confidence"), 0)
            stats["low_confidence"] = _decimal_to_number(summary.get("low_confidence"), 0)

            cur.execute("SELECT COUNT(*) AS total FROM tbl_disease")
            stats["disease_count"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT DATE(upload_date) AS day, COUNT(*) AS total FROM tbl_diagnosis_request WHERE upload_date >= %s AND upload_date < %s GROUP BY DATE(upload_date)",
                (start.strftime("%Y-%m-%d"), (today + timedelta(days=1)).strftime("%Y-%m-%d")),
            )
            day_counts = {row["day"].isoformat() if hasattr(row["day"], "isoformat") else str(row["day"]): _decimal_to_number(row["total"], 0) for row in cur.fetchall()}
            for offset in range(30):
                current_day = start + timedelta(days=offset)
                stats["daily"].append({"day": current_day.strftime("%Y-%m-%d"), "count": day_counts.get(current_day.strftime("%Y-%m-%d"), 0)})

            cur.execute(
                "SELECT d.disease_name AS disease_name, d.crop_name AS crop_name, COUNT(*) AS total FROM tbl_prediction_result p JOIN tbl_disease d ON d.disease_id = p.disease_id JOIN tbl_diagnosis_request r ON r.request_id = p.request_id WHERE d.is_healthy = 0 AND r.status = 'completed' GROUP BY d.disease_id, d.disease_name, d.crop_name ORDER BY total DESC LIMIT 5"
            )
            stats["top_diseases"] = [
                {"disease_name": row["disease_name"], "crop_name": row["crop_name"], "total": _decimal_to_number(row["total"], 0)}
                for row in cur.fetchall()
            ]

            cur.execute(
                "SELECT d.crop_name AS crop_name, COUNT(*) AS total FROM tbl_prediction_result p JOIN tbl_disease d ON d.disease_id = p.disease_id JOIN tbl_diagnosis_request r ON r.request_id = p.request_id WHERE r.status = 'completed' GROUP BY d.crop_name ORDER BY total DESC LIMIT 5"
            )
            stats["crop_distribution"] = [
                {"crop_name": row["crop_name"], "total": _decimal_to_number(row["total"], 0)}
                for row in cur.fetchall()
            ]

            cur.execute(
                "SELECT r.request_id, u.first_name, u.last_name, d.crop_name, d.disease_name, d.is_healthy, p.confidence_score, r.upload_date FROM tbl_diagnosis_request r JOIN tbl_users u ON u.user_id = r.user_id LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id ORDER BY r.upload_date DESC LIMIT 5"
            )
            stats["latest_diagnoses"] = [
                {
                    "request_id": row["request_id"],
                    "user_name": f"{row['first_name']} {row['last_name']}".strip(),
                    "crop_name": row["crop_name"] or "Unknown",
                    "disease_name": row["disease_name"] or "Analysis failed",
                    "is_healthy": bool(row.get("is_healthy")),
                    "confidence_score": _decimal_to_number(row.get("confidence_score"), 0),
                    "upload_date": _format_date(row["upload_date"]),
                }
                for row in cur.fetchall()
            ]

            cur.execute(
                "SELECT first_name, last_name, email, date_registered FROM tbl_users ORDER BY date_registered DESC LIMIT 5"
            )
            stats["new_users_list"] = [
                {
                    "name": f"{row['first_name']} {row['last_name']}".strip(),
                    "email": row["email"],
                    "date_registered": _format_date(row["date_registered"]),
                }
                for row in cur.fetchall()
            ]
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load admin dashboard")
        flash("Dashboard data is temporarily unavailable.", "error")
    finally:
        if conn:
            conn.close()

    return render_template("admin/dashboard.html", stats=stats, active_page="dashboard")


@admin_bp.get("/users")
@admin_required
def users():
    search = request.args.get("q", "").strip()[:100]
    role = request.args.get("role", "all")
    if role not in {"all", *ROLE_CHOICES}:
        role = "all"
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 10
    params = []
    where = []

    if search:
        where.append("(u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s)")
        term = f"%{search}%"
        params.extend([term, term, term])
    if role != "all":
        where.append("u.role = %s")
        params.append(role)

    where_clause = " AND ".join(where) if where else "1 = 1"
    conn = None
    rows = []
    total = 0
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM tbl_users u WHERE " + where_clause,
                tuple(params),
            )
            total = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT u.user_id, u.first_name, u.last_name, u.email, u.role, u.date_registered, COALESCE(r.scan_count, 0) AS scan_count, r.last_scan FROM tbl_users u LEFT JOIN (SELECT user_id, COUNT(*) AS scan_count, MAX(upload_date) AS last_scan FROM tbl_diagnosis_request GROUP BY user_id) r ON r.user_id = u.user_id WHERE " + where_clause + " ORDER BY u.date_registered DESC LIMIT %s OFFSET %s",
                (*params, per_page, (page - 1) * per_page),
            )
            rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load users list")
        flash("Users could not be loaded.", "error")
    finally:
        if conn:
            conn.close()

    page, pages = _paginate(page, total, per_page)
    return render_template(
        "admin/users.html",
        rows=rows,
        total=total,
        page=page,
        pages=pages,
        search=search,
        role=role,
        active_page="users",
    )


@admin_bp.get("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    conn = None
    user = None
    stats = {"total": 0, "healthy": 0, "diseased": 0, "average_confidence": 0.0}
    history = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, first_name, last_name, email, phone_number, role, date_registered FROM tbl_users WHERE user_id = %s",
                (user_id,),
            )
            user = cur.fetchone()
            if not user:
                return redirect(url_for("admin.users"))

            cur.execute(
                "SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN d.is_healthy = 1 THEN 1 ELSE 0 END),0) AS healthy, COALESCE(SUM(CASE WHEN d.is_healthy = 0 THEN 1 ELSE 0 END),0) AS diseased, AVG(p.confidence_score) AS avg_confidence FROM tbl_diagnosis_request r LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE r.user_id = %s AND r.status = 'completed'",
                (user_id,),
            )
            summary = cur.fetchone() or {}
            stats["total"] = _decimal_to_number(summary.get("total"), 0)
            stats["healthy"] = _decimal_to_number(summary.get("healthy"), 0)
            stats["diseased"] = _decimal_to_number(summary.get("diseased"), 0)
            stats["average_confidence"] = _decimal_to_number(summary.get("avg_confidence"), 0)

            cur.execute(
                "SELECT r.request_id, r.upload_date, r.crop_type, d.crop_name, d.disease_name, d.is_healthy, p.confidence_score FROM tbl_diagnosis_request r LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE r.user_id = %s ORDER BY r.upload_date DESC LIMIT 10",
                (user_id,),
            )
            history = [
                {
                    "request_id": row["request_id"],
                    "date": _format_date(row["upload_date"]),
                    "crop_type": row["crop_type"] or row["crop_name"] or "Unknown",
                    "disease": row["disease_name"] or "Analysis failed",
                    "healthy": bool(row.get("is_healthy")),
                    "confidence": _decimal_to_number(row.get("confidence_score"), 0),
                }
                for row in cur.fetchall()
            ]
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load user details")
        flash("User details could not be loaded.", "error")
        return redirect(url_for("admin.users"))
    finally:
        if conn:
            conn.close()

    return render_template("admin/user_detail.html", user=user, stats=stats, history=history, active_page="users")


@admin_bp.post("/users/<int:user_id>/role")
@admin_required
def update_user_role(user_id):
    role = request.form.get("role", "")
    if role not in ROLE_CHOICES:
        flash("Choose a valid role.", "error")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("UPDATE tbl_users SET role = %s WHERE user_id = %s", (role, user_id))
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to update user role")
        flash("Could not update the user role.", "error")
    else:
        flash("User role updated.", "success")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.post("/users/<int:user_id>/delete")
@admin_required
def delete_user(user_id):
    conn = None
    urls = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT image_path FROM tbl_diagnosis_request WHERE user_id = %s", (user_id,))
            urls = [row["image_path"] for row in cur.fetchall() if row.get("image_path")]
            cur.execute("DELETE FROM tbl_users WHERE user_id = %s", (user_id,))
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to delete user")
        flash("The user could not be deleted.", "error")
        return redirect(url_for("admin.users"))
    finally:
        if conn:
            conn.close()

    for url in urls:
        if str(url).startswith("http") and hasattr(diagnosis_store, "delete_image"):
            try:
                diagnosis_store.delete_image(url)
            except Exception:
                current_app.logger.exception("Cloudinary cleanup failed for user %s", user_id)
    flash("User deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.get("/diagnoses")
@admin_required
def diagnoses():
    q = request.args.get("q", "").strip()[:100]
    crop = request.args.get("crop", "").strip()[:100]
    result = request.args.get("result", "all")
    if result not in {"all", "healthy", "diseased"}:
        result = "all"
    confidence = request.args.get("confidence", "all")
    if confidence not in {"all", "high", "medium", "low"}:
        confidence = "all"
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    sort = request.args.get("sort", "newest")
    if sort not in {"newest", "oldest"}:
        sort = "newest"
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 10

    where = ["1 = 1"]
    params = []
    if q:
        where.append("(u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s)")
        term = f"%{q}%"
        params.extend([term, term, term])
    if crop:
        where.append("(r.crop_type = %s OR d.crop_name = %s)")
        params.extend([crop, crop])
    if result == "healthy":
        where.append("d.is_healthy = 1")
    elif result == "diseased":
        where.append("d.is_healthy = 0")
    if confidence == "high":
        where.append("p.confidence_score >= 80")
    elif confidence == "medium":
        where.append("p.confidence_score >= 60 AND p.confidence_score < 80")
    elif confidence == "low":
        where.append("p.confidence_score < 60")
    if date_from:
        where.append("r.upload_date >= %s")
        params.append(date_from)
    if date_to:
        where.append("r.upload_date <= %s")
        params.append(date_to)

    order = "ORDER BY r.upload_date DESC" if sort == "newest" else "ORDER BY r.upload_date ASC"
    conn = None
    total = 0
    rows = []
    crop_options = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT crop_type AS crop FROM tbl_diagnosis_request WHERE crop_type IS NOT NULL AND crop_type <> '' UNION SELECT DISTINCT crop_name AS crop FROM tbl_disease WHERE crop_name IS NOT NULL AND crop_name <> '' ORDER BY crop")
            crop_options = [row["crop"] for row in cur.fetchall()]

            cur.execute(
                "SELECT COUNT(*) AS total FROM tbl_diagnosis_request r JOIN tbl_users u ON u.user_id = r.user_id LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE " + " AND ".join(where),
                tuple(params),
            )
            total = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT r.request_id, u.first_name, u.last_name, r.image_path, r.crop_type, d.crop_name, d.disease_name, d.is_healthy, p.confidence_score, r.upload_date, r.status FROM tbl_diagnosis_request r JOIN tbl_users u ON u.user_id = r.user_id LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE " + " AND ".join(where) + " " + order + " LIMIT %s OFFSET %s",
                (*params, per_page, (page - 1) * per_page),
            )
            rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to list diagnoses")
        flash("Diagnoses could not be loaded.", "error")
    finally:
        if conn:
            conn.close()

    page, pages = _paginate(page, total, per_page)
    return render_template(
        "admin/diagnoses.html",
        rows=rows,
        page=page,
        pages=pages,
        total=total,
        q=q,
        crop=crop,
        result=result,
        confidence=confidence,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        crop_options=crop_options,
        active_page="diagnoses",
    )


@admin_bp.get("/diagnoses/<int:request_id>")
@admin_required
def diagnosis_detail(request_id):
    conn = None
    item = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.request_id, r.image_path, r.crop_type, r.upload_date, r.status, u.first_name, u.last_name, u.email, d.crop_name, d.disease_name, d.description, d.recommended_treatment, d.is_healthy, p.confidence_score, m.model_version FROM tbl_diagnosis_request r JOIN tbl_users u ON u.user_id = r.user_id LEFT JOIN tbl_prediction_result p ON p.request_id = r.request_id LEFT JOIN tbl_disease d ON d.disease_id = p.disease_id LEFT JOIN tbl_model_version m ON m.model_id = p.model_id WHERE r.request_id = %s",
                (request_id,),
            )
            item = cur.fetchone()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load diagnosis")
        flash("Diagnosis details could not be loaded.", "error")
        return redirect(url_for("admin.diagnoses"))
    finally:
        if conn:
            conn.close()

    if not item:
        abort(404)

    return render_template("admin/diagnosis_detail.html", item=item, active_page="diagnoses")


@admin_bp.post("/diagnoses/<int:request_id>/delete")
@admin_required
def delete_diagnosis(request_id):
    conn = None
    urls = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT image_path FROM tbl_diagnosis_request WHERE request_id = %s", (request_id,))
            row = cur.fetchone()
            if row:
                urls = [row["image_path"]] if row.get("image_path") else []
            cur.execute("DELETE FROM tbl_diagnosis_request WHERE request_id = %s", (request_id,))
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to delete diagnosis")
        flash("The diagnosis could not be deleted.", "error")
        return redirect(url_for("admin.diagnoses"))
    finally:
        if conn:
            conn.close()

    for url in urls:
        if str(url).startswith("http") and hasattr(diagnosis_store, "delete_image"):
            try:
                diagnosis_store.delete_image(url)
            except Exception:
                current_app.logger.exception("Cloudinary cleanup failed for request %s", request_id)
    flash("Diagnosis deleted.", "success")
    return redirect(url_for("admin.diagnoses"))


@admin_bp.get("/diseases")
@admin_required
def diseases():
    q = request.args.get("q", "").strip()[:100]
    crop = request.args.get("crop", "").strip()[:100]
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 10
    params = []
    where = []
    if q:
        where.append("(disease_name LIKE %s OR crop_name LIKE %s OR class_label LIKE %s)")
        term = f"%{q}%"
        params.extend([term, term, term])
    if crop:
        where.append("crop_name = %s")
        params.append(crop)
    where_sql = " AND ".join(where) if where else "1 = 1"
    conn = None
    rows = []
    total = 0
    crop_options = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT crop_name AS crop FROM tbl_disease WHERE crop_name IS NOT NULL AND crop_name <> '' ORDER BY crop")
            crop_options = [row["crop"] for row in cur.fetchall()]

            cur.execute("SELECT COUNT(*) AS total FROM tbl_disease d WHERE " + where_sql, tuple(params))
            total = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT disease_id, disease_name, crop_name, class_label, is_healthy, description, recommended_treatment FROM tbl_disease d WHERE " + where_sql + " ORDER BY crop_name, disease_name LIMIT %s OFFSET %s",
                (*params, per_page, (page - 1) * per_page),
            )
            rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load disease list")
        flash("Disease records could not be loaded.", "error")
    finally:
        if conn:
            conn.close()

    page, pages = _paginate(page, total, per_page)
    return render_template("admin/diseases.html", rows=rows, total=total, page=page, pages=pages, q=q, crop=crop, crop_options=crop_options, active_page="diseases")


@admin_bp.route("/diseases/new", methods=["GET", "POST"])
@admin_required
def disease_new():
    if request.method == "GET":
        return render_template("admin/disease_form.html", form_data={}, mode="new", active_page="diseases")

    form_data = request.form.to_dict()
    disease_name = (form_data.get("disease_name") or "").strip()[:100]
    crop_name = (form_data.get("crop_name") or "").strip()[:100]
    class_label = (form_data.get("class_label") or "").strip()[:150]
    description = (form_data.get("description") or "").strip()[:65535]
    treatment = (form_data.get("recommended_treatment") or "").strip()[:65535]
    is_healthy = 1 if form_data.get("is_healthy") == "1" else 0

    errors = []
    if not disease_name:
        errors.append("Disease name is required.")
    if not crop_name:
        errors.append("Crop name is required.")
    if not class_label:
        errors.append("Class label is required.")
    if len(disease_name) > 100 or len(crop_name) > 100 or len(class_label) > 150:
        errors.append("A field is too long.")
    if errors:
        for message in errors:
            flash(message, "error")
        return render_template("admin/disease_form.html", form_data=form_data, mode="new", active_page="diseases"), 400

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tbl_disease (class_label, disease_name, crop_name, is_healthy, description, recommended_treatment) VALUES (%s, %s, %s, %s, %s, %s)",
                (class_label, disease_name, crop_name, is_healthy, description or None, treatment or None),
            )
    except pymysql.err.IntegrityError:
        current_app.logger.warning("Duplicate disease insert attempted")
        flash("A disease with that class label already exists.", "error")
        return render_template("admin/disease_form.html", form_data=form_data, mode="new", active_page="diseases"), 409
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to create disease record")
        flash("The disease could not be saved.", "error")
        return render_template("admin/disease_form.html", form_data=form_data, mode="new", active_page="diseases"), 500
    finally:
        if conn:
            conn.close()

    flash("Disease added.", "success")
    return redirect(url_for("admin.diseases"))


@admin_bp.route("/diseases/<int:disease_id>/edit", methods=["GET", "POST"])
@admin_required
def disease_edit(disease_id):
    conn = None
    current_record = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT disease_id, disease_name, crop_name, class_label, is_healthy, description, recommended_treatment FROM tbl_disease WHERE disease_id = %s",
                (disease_id,),
            )
            current_record = cur.fetchone()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load disease row")
        flash("The disease record could not be loaded.", "error")
        return redirect(url_for("admin.diseases"))
    finally:
        if conn:
            conn.close()

    if not current_record:
        abort(404)

    if request.method == "GET":
        return render_template("admin/disease_form.html", form_data=current_record, mode="edit", disease_id=disease_id, active_page="diseases")

    form_data = request.form.to_dict()
    disease_name = (form_data.get("disease_name") or "").strip()[:100]
    crop_name = (form_data.get("crop_name") or "").strip()[:100]
    class_label = (form_data.get("class_label") or "").strip()[:150]
    description = (form_data.get("description") or "").strip()[:65535]
    treatment = (form_data.get("recommended_treatment") or "").strip()[:65535]
    is_healthy = 1 if form_data.get("is_healthy") == "1" else 0

    if not disease_name or not crop_name or not class_label:
        flash("All required fields must be completed.", "error")
        return render_template("admin/disease_form.html", form_data=form_data, mode="edit", disease_id=disease_id, active_page="diseases"), 400

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_disease SET class_label = %s, disease_name = %s, crop_name = %s, is_healthy = %s, description = %s, recommended_treatment = %s WHERE disease_id = %s",
                (class_label, disease_name, crop_name, is_healthy, description or None, treatment or None, disease_id),
            )
    except pymysql.err.IntegrityError:
        current_app.logger.warning("Disease edit caused a duplicate label")
        flash("A disease with that class label already exists.", "error")
        return render_template("admin/disease_form.html", form_data=form_data, mode="edit", disease_id=disease_id, active_page="diseases"), 409
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to update disease record")
        flash("The disease could not be updated.", "error")
        return render_template("admin/disease_form.html", form_data=form_data, mode="edit", disease_id=disease_id, active_page="diseases"), 500
    finally:
        if conn:
            conn.close()

    flash("Disease updated.", "success")
    return redirect(url_for("admin.diseases"))


@admin_bp.post("/diseases/<int:disease_id>/delete")
@admin_required
def disease_delete(disease_id):
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tbl_disease WHERE disease_id = %s", (disease_id,))
    except pymysql.err.IntegrityError:
        current_app.logger.warning("Attempt to delete disease with predictions")
        flash("That disease is still in use by prediction results.", "error")
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to delete disease")
        flash("The disease could not be deleted.", "error")
    else:
        flash("Disease deleted.", "success")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("admin.diseases"))


@admin_bp.get("/models")
@admin_required
def models():
    conn = None
    rows = []
    form_data = request.args.to_dict() if request.method == "GET" else {}
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.model_id, m.model_version, m.accuracy, m.date_deployed, COALESCE(COUNT(p.result_id), 0) AS prediction_count FROM tbl_model_version m LEFT JOIN tbl_prediction_result p ON p.model_id = m.model_id GROUP BY m.model_id, m.model_version, m.accuracy, m.date_deployed ORDER BY m.date_deployed DESC"
            )
            rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load model list")
        flash("Model versions could not be loaded.", "error")
    finally:
        if conn:
            conn.close()

    return render_template("admin/models.html", rows=rows, form_data=form_data, active_page="models")


@admin_bp.post("/models/new")
@admin_required
def model_new():
    model_version = (request.form.get("model_version") or "").strip()[:50]
    accuracy_input = request.form.get("accuracy", "")
    errors = []
    if not model_version:
        errors.append("Model version is required.")
    if len(model_version) > 50:
        errors.append("Model version is too long.")
    try:
        accuracy = float(accuracy_input)
    except (TypeError, ValueError):
        accuracy = None
    if accuracy is None or accuracy < 0 or accuracy > 100:
        errors.append("Accuracy must be a value between 0 and 100.")

    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("admin.models"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tbl_model_version (model_version, accuracy) VALUES (%s, %s)",
                (model_version, accuracy / 100.0),
            )
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to add model version")
        flash("The model version could not be added.", "error")
    else:
        flash("Model version added.", "success")
    finally:
        if conn:
            conn.close()

    return redirect(url_for("admin.models"))


@admin_bp.get("/reports")
@admin_required
def reports():
    today = date.today()
    default_to = today
    default_from = today - timedelta(days=29)
    date_from = request.args.get("date_from") or default_from.isoformat()
    date_to = request.args.get("date_to") or default_to.isoformat()
    quick = request.args.get("quick", "30")
    if quick not in {"7", "30", "90", "all"}:
        quick = "30"
    if quick != "all":
        window_days = int(quick)
        default_from = today - timedelta(days=window_days - 1)
        default_to = today
        date_from = request.args.get("date_from") or default_from.isoformat()
        date_to = request.args.get("date_to") or default_to.isoformat()

    conn = None
    summary = {
        "diagnoses": 0,
        "active_users": 0,
        "average_confidence": 0.0,
        "low_confidence": 0,
    }
    daily = []
    disease_rows = []
    crop_rows = []
    model_rows = []
    user_rows = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM tbl_diagnosis_request WHERE upload_date >= %s AND upload_date <= %s",
                (date_from, date_to + " 23:59:59"),
            )
            summary["diagnoses"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT COUNT(DISTINCT user_id) AS total FROM tbl_diagnosis_request WHERE upload_date >= %s AND upload_date <= %s",
                (date_from, date_to + " 23:59:59"),
            )
            summary["active_users"] = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)

            cur.execute(
                "SELECT AVG(p.confidence_score) AS avg_confidence, SUM(CASE WHEN p.confidence_score < 60 THEN 1 ELSE 0 END) AS low_confidence FROM tbl_prediction_result p JOIN tbl_diagnosis_request r ON r.request_id = p.request_id WHERE r.upload_date >= %s AND r.upload_date <= %s",
                (date_from, date_to + " 23:59:59"),
            )
            row = cur.fetchone() or {}
            summary["average_confidence"] = _decimal_to_number(row.get("avg_confidence"), 0)
            summary["low_confidence"] = _decimal_to_number(row.get("low_confidence"), 0)

            day_start = date.fromisoformat(date_from)
            day_end = date.fromisoformat(date_to)
            for offset in range((day_end - day_start).days + 1):
                current_day = day_start + timedelta(days=offset)
                daily.append({"day": current_day.isoformat(), "count": 0})

            cur.execute(
                "SELECT DATE(upload_date) AS day, COUNT(*) AS total FROM tbl_diagnosis_request WHERE upload_date >= %s AND upload_date <= %s GROUP BY DATE(upload_date)",
                (date_from, date_to + " 23:59:59"),
            )
            entries = cur.fetchall()
            mapping = {str(row["day"]): _decimal_to_number(row["total"], 0) for row in entries}
            for item in daily:
                item["count"] = mapping.get(item["day"], 0)

            cur.execute(
                "SELECT d.disease_name, d.crop_name, COUNT(*) AS total, ROUND((COUNT(*) * 100.0) / (SELECT COUNT(*) FROM tbl_prediction_result p2 JOIN tbl_diagnosis_request r2 ON r2.request_id = p2.request_id WHERE r2.upload_date >= %s AND r2.upload_date <= %s), 2) AS share, AVG(p.confidence_score) AS avg_confidence FROM tbl_prediction_result p JOIN tbl_diagnosis_request r ON r.request_id = p.request_id JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE r.upload_date >= %s AND r.upload_date <= %s GROUP BY d.disease_id, d.disease_name, d.crop_name ORDER BY total DESC LIMIT 20",
                (date_from, date_to + " 23:59:59", date_from, date_to + " 23:59:59"),
            )
            disease_rows = cur.fetchall()

            cur.execute(
                "SELECT d.crop_name AS crop_name, COUNT(*) AS total FROM tbl_prediction_result p JOIN tbl_diagnosis_request r ON r.request_id = p.request_id JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE r.upload_date >= %s AND r.upload_date <= %s GROUP BY d.crop_name ORDER BY total DESC",
                (date_from, date_to + " 23:59:59"),
            )
            crop_rows = cur.fetchall()

            cur.execute(
                "SELECT m.model_version, COUNT(*) AS total FROM tbl_prediction_result p JOIN tbl_model_version m ON m.model_id = p.model_id JOIN tbl_diagnosis_request r ON r.request_id = p.request_id WHERE r.upload_date >= %s AND r.upload_date <= %s GROUP BY m.model_id, m.model_version ORDER BY total DESC",
                (date_from, date_to + " 23:59:59"),
            )
            model_rows = cur.fetchall()

            cur.execute(
                "SELECT u.user_id, u.first_name, u.last_name, COUNT(*) AS total FROM tbl_diagnosis_request r JOIN tbl_users u ON u.user_id = r.user_id WHERE r.upload_date >= %s AND r.upload_date <= %s GROUP BY u.user_id, u.first_name, u.last_name ORDER BY total DESC LIMIT 5",
                (date_from, date_to + " 23:59:59"),
            )
            user_rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load reports")
        flash("Reports could not be loaded.", "error")
    finally:
        if conn:
            conn.close()

    return render_template(
        "admin/reports.html",
        date_from=date_from,
        date_to=date_to,
        quick=quick,
        summary=summary,
        daily=daily,
        disease_rows=disease_rows,
        crop_rows=crop_rows,
        model_rows=model_rows,
        user_rows=user_rows,
        active_page="reports",
    )


@admin_bp.get("/reports/export.csv")
@admin_required
def export_reports_csv():
    today = date.today()
    date_from = request.args.get("date_from") or (today - timedelta(days=29)).isoformat()
    date_to = request.args.get("date_to") or today.isoformat()
    conn = None
    rows = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.disease_name AS disease_name, d.crop_name AS crop_name, COUNT(*) AS total, ROUND((COUNT(*) * 100.0) / (SELECT COUNT(*) FROM tbl_prediction_result p2 JOIN tbl_diagnosis_request r2 ON r2.request_id = p2.request_id WHERE r2.upload_date >= %s AND r2.upload_date <= %s), 2) AS share, AVG(p.confidence_score) AS avg_confidence FROM tbl_prediction_result p JOIN tbl_diagnosis_request r ON r.request_id = p.request_id JOIN tbl_disease d ON d.disease_id = p.disease_id WHERE r.upload_date >= %s AND r.upload_date <= %s GROUP BY d.disease_id, d.disease_name, d.crop_name ORDER BY total DESC",
                (date_from, date_to + " 23:59:59", date_from, date_to + " 23:59:59"),
            )
            rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to export report CSV")
        flash("The CSV could not be generated.", "error")
        return redirect(url_for("admin.reports"))
    finally:
        if conn:
            conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["disease", "crop", "count", "share_percent", "avg_confidence"])
    for row in rows:
        writer.writerow([
            row["disease_name"],
            row["crop_name"],
            _decimal_to_number(row["total"], 0),
            _decimal_to_number(row["share"], 0),
            _decimal_to_number(row["avg_confidence"], 0),
        ])

    data = output.getvalue()
    escaped = []
    for line in data.splitlines(True):
        if line and line[0] in "=+-@":
            escaped.append("'" + line)
        else:
            escaped.append(line)
    response = "".join(escaped)
    return response, 200, {"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": "attachment; filename=leaflens-report.csv"}


@admin_bp.get("/administrators")
@admin_required
def administrators():
    conn = None
    rows = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT admin_id, first_name, last_name, email, date_added FROM tbl_administrators ORDER BY date_added DESC")
            rows = cur.fetchall()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load administrators")
        flash("Administrators could not be loaded.", "error")
    finally:
        if conn:
            conn.close()
    return render_template("admin/administrators.html", rows=rows, active_page="administrators")


@admin_bp.post("/administrators/new")
@admin_required
def administrator_new():
    first_name = (request.form.get("first_name") or "").strip()[:50]
    last_name = (request.form.get("last_name") or "").strip()[:50]
    email = (request.form.get("email") or "").strip().lower()[:100]
    password = request.form.get("password", "")
    if not first_name or not last_name or not email or not password:
        flash("All administrator fields are required.", "error")
        return redirect(url_for("admin.administrators"))
    if not EMAIL_RE.fullmatch(email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("admin.administrators"))
    if len(password) < 8 or len(password) > 128:
        flash("Password must be 8 to 128 characters.", "error")
        return redirect(url_for("admin.administrators"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tbl_administrators (first_name, last_name, email, password_hash) VALUES (%s, %s, %s, %s)",
                (first_name, last_name, email, generate_password_hash(password)),
            )
    except pymysql.err.IntegrityError:
        flash("That email is already in use.", "error")
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to add admin")
        flash("The administrator could not be created.", "error")
    else:
        flash("Administrator added.", "success")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("admin.administrators"))


@admin_bp.post("/administrators/<int:admin_id>/delete")
@admin_required
def administrator_delete(admin_id):
    if admin_id == session["admin_id"]:
        flash("You cannot delete your own administrator account.", "error")
        return redirect(url_for("admin.administrators"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM tbl_administrators")
            count = _decimal_to_number((cur.fetchone() or {}).get("total"), 0)
            if count <= 1:
                flash("At least one administrator must remain.", "error")
                return redirect(url_for("admin.administrators"))
            cur.execute("DELETE FROM tbl_administrators WHERE admin_id = %s", (admin_id,))
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to delete admin")
        flash("The administrator could not be deleted.", "error")
    else:
        flash("Administrator deleted.", "success")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("admin.administrators"))


@admin_bp.get("/account")
@admin_required
def account():
    conn = None
    admin = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT admin_id, first_name, last_name, email FROM tbl_administrators WHERE admin_id = %s",
                (session["admin_id"],),
            )
            admin = cur.fetchone()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load admin account")
        flash("Account details could not be loaded.", "error")
    finally:
        if conn:
            conn.close()
    return render_template("admin/account.html", admin=admin, form_data={}, active_page="account")


@admin_bp.post("/account")
@admin_required
def account_update():
    first_name = (request.form.get("first_name") or "").strip()[:50]
    last_name = (request.form.get("last_name") or "").strip()[:50]
    if not first_name or not last_name:
        flash("First and last name are required.", "error")
        return redirect(url_for("admin.account"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tbl_administrators SET first_name = %s, last_name = %s WHERE admin_id = %s",
                (first_name, last_name, session["admin_id"]),
            )
        session["admin_name"] = f"{first_name} {last_name}".strip()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to update admin account")
        flash("Your account details could not be saved.", "error")
    else:
        flash("Account updated.", "success")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("admin.account"))


@admin_bp.post("/account/password")
@admin_required
def account_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    conn = None
    admin = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM tbl_administrators WHERE admin_id = %s", (session["admin_id"],))
            admin = cur.fetchone()
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to load admin password data")
        flash("Your password could not be changed.", "error")
        return redirect(url_for("admin.account"))
    finally:
        if conn:
            conn.close()

    if not admin or not check_password_hash(admin["password_hash"], current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("admin.account"))
    if len(new_password) < 8 or len(new_password) > 128:
        flash("Password must be 8 to 128 characters.", "error")
        return redirect(url_for("admin.account"))
    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(url_for("admin.account"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("UPDATE tbl_administrators SET password_hash = %s WHERE admin_id = %s", (generate_password_hash(new_password), session["admin_id"]))
    except pymysql.MySQLError:
        current_app.logger.exception("Unable to update admin password")
        flash("Your password could not be changed.", "error")
    else:
        flash("Password changed.", "success")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("admin.account"))
