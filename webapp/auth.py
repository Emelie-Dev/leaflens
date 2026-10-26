import re

import os
import smtplib

import pymysql
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

from email.message import EmailMessage
from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer

RESET_MAX_AGE = 1800  # 30 minutes

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLES = {"farmer", "extension_worker"}


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return render_template("register.html")

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone_number", "").strip() or None
    role = request.form.get("role", "farmer")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    errors = []
    if not first_name or len(first_name) > 50:
        errors.append("First name is required (50 characters max).")
    if not last_name or len(last_name) > 50:
        errors.append("Last name is required (50 characters max).")
    if not EMAIL_RE.match(email) or len(email) > 100:
        errors.append("Enter a valid email address.")
    if phone and len(phone) > 20:
        errors.append("Phone number is too long (20 characters max).")
    if role not in ROLES:
        errors.append("Choose a valid role.")
    if len(password) < 8 or len(password) > 128:
        errors.append("Password must be 8 to 128 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("register.html"), 400

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM tbl_users WHERE email = %s", (email,))
            if cur.fetchone():
                flash("An account with that email already exists.", "error")
                return render_template("register.html"), 409
            cur.execute(
                "INSERT INTO tbl_users (first_name, last_name, email, password_hash, phone_number, role) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (first_name, last_name, email, generate_password_hash(password), phone, role),
            )
    except pymysql.err.IntegrityError:
        flash("An account with that email already exists.", "error")
        return render_template("register.html"), 409
    except pymysql.MySQLError:
        flash("Could not reach the database. Please try again.", "error")
        return render_template("register.html"), 503
    finally:
        if conn:
            conn.close()

    flash("Account created. Please log in.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    conn = None
    user = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, first_name, role, password_hash FROM tbl_users WHERE email = %s",
                (email,),
            )
            user = cur.fetchone()
    except pymysql.MySQLError:
        flash("Could not reach the database. Please try again.", "error")
        return render_template("login.html"), 503
    finally:
        if conn:
            conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return render_template("login.html"), 401

    session.clear()
    session["user_id"] = user["user_id"]
    session["first_name"] = user["first_name"]
    session["role"] = user["role"]
    return redirect(url_for("dashboard"))


@auth_bp.get("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))

def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def _send_reset_email(to_email, link):
    if not os.getenv("MAIL_HOST") or not os.getenv("MAIL_USER"):
        print("PASSWORD RESET LINK (email not configured):", link)
        return
    msg = EmailMessage()
    msg["Subject"] = "Reset your LeafLens password"
    msg["From"] = os.getenv("MAIL_FROM", os.getenv("MAIL_USER"))
    msg["To"] = to_email
    msg.set_content(
        "Open the link below to reset your password. It expires in 30 minutes.\n\n"
        f"{link}\n\nIf you did not ask for this, ignore this email."
    )
    with smtplib.SMTP(os.getenv("MAIL_HOST"), int(os.getenv("MAIL_PORT", 587))) as s:
        s.starttls()
        s.login(os.getenv("MAIL_USER"), os.getenv("MAIL_PASSWORD"))
        s.send_message(msg)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    email = request.form.get("email", "").strip().lower()
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, password_hash FROM tbl_users WHERE email = %s", (email,))
            user = cur.fetchone()
    except pymysql.MySQLError:
        flash("Could not reach the database. Please try again.", "error")
        return render_template("forgot_password.html"), 503
    finally:
        if conn:
            conn.close()

    if user:
        token = _serializer().dumps({"uid": user["user_id"], "ph": user["password_hash"][-12:]})
        link = url_for("auth.reset_password", token=token, _external=True)
        try:
            _send_reset_email(email, link)
        except Exception:
            current_app.logger.exception("Reset email failed")

    flash("If that email is registered, a reset link has been sent.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    invalid = "That reset link is invalid or has expired."
    try:
        data = _serializer().loads(token, max_age=RESET_MAX_AGE)
    except BadSignature:   # also covers expired tokens
        flash(invalid, "error")
        return redirect(url_for("auth.forgot_password"))

    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM tbl_users WHERE user_id = %s", (data["uid"],))
            row = cur.fetchone()
            if not row or row["password_hash"][-12:] != data["ph"]:
                flash(invalid, "error")
                return redirect(url_for("auth.forgot_password"))

            if request.method == "GET":
                return render_template("reset_password.html")

            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if len(password) < 8 or len(password) > 128:
                flash("Password must be 8 to 128 characters.", "error")
                return render_template("reset_password.html"), 400
            if password != confirm:
                flash("Passwords do not match.", "error")
                return render_template("reset_password.html"), 400

            cur.execute("UPDATE tbl_users SET password_hash = %s WHERE user_id = %s",
                        (generate_password_hash(password), data["uid"]))
    except pymysql.MySQLError:
        flash("Could not reach the database. Please try again.", "error")
        return redirect(url_for("auth.forgot_password"))
    finally:
        if conn:
            conn.close()

    flash("Password updated. Please log in.", "success")
    return redirect(url_for("auth.login"))