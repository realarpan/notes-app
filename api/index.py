from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import requests

# ================= APP CONFIG =================

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

# ================= LOGIN MANAGER =================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ================= ROUTES =================

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)

            if user.role == "admin":
                return redirect(url_for("admin"))
            return redirect(url_for("dashboard"))

        flash("Invalid credentials")

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/class/<int:class_number>")
@login_required
def class_notes(class_number):
    notes = Note.query.filter_by(class_number=class_number).all()
    return render_template("class_notes.html", notes=notes, class_number=class_number)

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        class_number = request.form["class_number"]
        file = request.files.get("file")

        if not file:
            flash("No file selected")
            return redirect(url_for("admin"))

        # Limit file size (10MB safety)
        if request.content_length > 10 * 1024 * 1024:
            return "File too large (Max 10MB)"

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

    return render_template("admin.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ================= INIT DATABASE =================

with app.app_context():
    db.create_all()

    # Create Admin
    admin_exists = User.query.filter_by(username="admin").first()
    if not admin_exists:
        admin_user = User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(admin_user)

    # Create Student User
    user_exists = User.query.filter_by(username="student").first()
    if not user_exists:
        student_user = User(
            username="student",
            password=generate_password_hash("student123"),
            role="user"
        )
        db.session.add(student_user)

    db.session.commit()
db.session.commit()
