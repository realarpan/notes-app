from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text
from datetime import datetime, timedelta
import time
import os
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "../templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

app.config["SECRET_KEY"] = "supersecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# 🔥 APP START TIME
APP_START_TIME = time.time()


# ================= MODELS =================

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20))


class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    class_number = db.Column(db.Integer)
    pdf_url = db.Column(db.String(500))


# ================= LOGIN =================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)

            if user.role == "admin":
                return redirect(url_for("admin"))
            return redirect(url_for("dashboard"))

        flash("Invalid credentials")

    return render_template("login.html")


# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ================= CLASS NOTES =================

@app.route("/class/<int:class_number>")
@login_required
def class_notes(class_number):
    notes = Note.query.filter_by(class_number=class_number).all()
    return render_template("class_notes.html", notes=notes, class_number=class_number)


# ================= ADMIN PANEL =================

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if current_user.role != "admin":
        return "Access Denied"

    # ================= UPLOAD =================
    if request.method == "POST":
        class_number = request.form["class_number"]
        file = request.files.get("file")

        if not file:
            flash("No file selected")
            return redirect(url_for("admin"))

        if request.content_length and request.content_length > 10 * 1024 * 1024:
            flash("File too large (Max 10MB)")
            return redirect(url_for("admin"))

        filename = secure_filename(file.filename)
        temp_path = f"/tmp/{filename}"
        file.save(temp_path)

        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        upload_url = f"{SUPABASE_URL}/storage/v1/object/notes/{filename}"

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/pdf"
        }

        with open(temp_path, "rb") as f:
            response = requests.post(upload_url, headers=headers, data=f)

        if response.status_code not in [200, 201]:
            return f"Upload failed: {response.text}"

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/notes/{filename}"

        note = Note(class_number=class_number, pdf_url=public_url)
        db.session.add(note)
        db.session.commit()

        flash("PDF uploaded successfully")

    # ================= FETCH =================

    notes = Note.query.order_by(Note.id.desc()).all()
    users = User.query.all()

    classes_with_notes = db.session.query(Note.class_number).distinct().count()
    total_users = len(users)

    # 🔥 Uploads in last 24h (approx using last IDs)
    recent_uploads = len(notes[:10])  # simple fallback

    # 🔥 DATABASE STATUS
    db_status = "offline"
    db_ping = None
    try:
        start = time.time()
        db.session.execute(text("SELECT 1"))
        db.session.commit()
        db_ping = round((time.time() - start) * 1000)
        db_status = "online"
    except Exception as e:
        print("DB ERROR:", e)

    # 🔥 STORAGE STATUS
    storage_status = "offline"
    try:
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        r = requests.get(f"{SUPABASE_URL}/storage/v1/bucket", timeout=3)
        if r.status_code in [200, 401]:
            storage_status = "online"
    except:
        pass

    # 🔥 API PING
    api_ping = None
    try:
        start = time.time()
        requests.get(request.host_url, timeout=2)
        api_ping = round((time.time() - start) * 1000)
    except:
        pass

    # 🔥 UPTIME
    uptime_seconds = int(time.time() - APP_START_TIME)
    uptime = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600)//60}m"

    # 🔥 HOST
    host = request.host

    # 🔥 RECENT NOTES
    recent_notes = notes[:5]

    return render_template(
        "admin.html",
        notes=notes,
        users=users,  # ✅ THIS FIXES EMPTY USERS PANEL
        classes_with_notes=classes_with_notes,
        total_users=total_users,
        recent_uploads=recent_uploads,
        db_status=db_status,
        db_ping=db_ping,
        storage_status=storage_status,
        api_ping=api_ping,
        uptime=uptime,
        host=host,
        recent_notes=recent_notes
    )


# ================= DELETE NOTE =================

@app.route("/delete-note/<int:id>", methods=["POST"])
@login_required
def delete_note(id):
    if current_user.role != "admin":
        return "Access Denied"

    note = Note.query.get(id)

    if note:
        db.session.delete(note)
        db.session.commit()
        flash("Note deleted")

    return redirect(url_for("admin"))


# ================= LOGOUT =================

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
