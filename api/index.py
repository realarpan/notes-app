from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__, template_folder="../templates", static_folder="../static")

app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ================= MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(10))  # admin or student

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_number = db.Column(db.Integer)
    filename = db.Column(db.String(200))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
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

@app.route("/admin", methods=["GET","POST"])
@login_required
def admin():
    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        file = request.files['file']
        class_number = request.form['class_number']

        if file.filename.endswith(".pdf"):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            note = Note(class_number=class_number, filename=file.filename)
            db.session.add(note)
            db.session.commit()

            flash("PDF Uploaded Successfully")

    return render_template("admin.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ============ INIT DB =============

with app.app_context():
    db.create_all()

    # Create admin if not exists
    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()

# Required for Vercel
def handler(request):
    return app