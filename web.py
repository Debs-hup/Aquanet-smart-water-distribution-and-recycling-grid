import os
import secrets
import datetime
import time
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from models import SessionLocal, init_db, User, File as FileModel, OTPToken
from passlib.hash import pbkdf2_sha256 as pwd_hasher
from config import DEFAULT_QUOTA_BYTES, UPLOAD_DIR, TMP_DIR, SMTP_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, OTP_EXPIRY_SECONDS
from storage import save_chunk_to_temp, finalize_upload
import smtplib
from email.message import EmailMessage
import threading

init_db()
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

app = Flask("aquaweb", template_folder=os.path.join(os.path.dirname(__file__), "templates"))
app.secret_key = secrets.token_urlsafe(16)

def send_otp_email(dest_email: str, token: str):
    def _send():
        try:
            msg = EmailMessage()
            msg["Subject"] = "Your AquaNet OTP"
            msg["From"] = SMTP_USER
            msg["To"] = dest_email
            msg.set_content(f"Your login OTP is: {token}")
            if SMTP_ENABLED:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
                    try:
                        smtp.starttls()
                    except Exception:
                        pass
                    if SMTP_USER and SMTP_PASS:
                        smtp.login(SMTP_USER, SMTP_PASS)
                    smtp.send_message(msg)
                print(f"[OTP] sent to {dest_email}")
            else:
                # Development fallback: print OTP to console
                print(f"[DEV OTP] send to {dest_email}: {token}")
        except Exception as e:
            print(f"Failed to send OTP to {dest_email}: {e}")

    # send asynchronously so web requests are not blocked by SMTP
    t = threading.Thread(target=_send, daemon=True)
    t.start()

def get_user_by_session():
    token = session.get("session_token")
    if not token:
        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.session_token == token).first()
        return user
    finally:
        db.close()


@app.route("/")
def index():
    """Root route: redirect authenticated users to dashboard, others to login."""
    user = get_user_by_session()
    if user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"][:72]  # bcrypt max 72 bytes
        db = SessionLocal()
        try:
            if db.query(User).filter(User.email == email).first():
                flash("Account already exists")
                return redirect(url_for("signup"))
            pw = pwd_hasher.hash(password)
            user = User(email=email, password_hash=pw, quota_bytes=DEFAULT_QUOTA_BYTES)
            db.add(user)
            db.commit()
            flash("Account created. Please login.")
            return redirect(url_for("login"))
        finally:
            db.close()
    return render_template("signup.html", user=get_user_by_session())

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"][:72]  # bcrypt max 72 bytes
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            if not user or not pwd_hasher.verify(password, user.password_hash):
                flash("Invalid credentials")
                return redirect(url_for("login"))
            token = f"{secrets.randbelow(10**6):06d}"
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=OTP_EXPIRY_SECONDS)
            otp = OTPToken(user_id=user.id, token=token, expires_at=expires_at, used=False)
            db.add(otp)
            db.commit()
            send_otp_email(user.email, token)
            session["tmp_user_id"] = user.id
            session["otp_sent_at"] = time.time()
            # In dev mode (no SMTP) store the OTP in session so tester can see it
            try:
                from config import SMTP_ENABLED as _SMTP_ENABLED
            except Exception:
                _SMTP_ENABLED = False
            if not _SMTP_ENABLED:
                session["last_otp"] = token
            flash("OTP sent to your email (dev prints to console if SMTP disabled)")
            return redirect(url_for("verify_otp"))
        finally:
            db.close()
    return render_template("login.html", user=get_user_by_session())

@app.route("/verify_otp", methods=["GET","POST"])
def verify_otp():
    if request.method == "POST":
        u_id = session.get("tmp_user_id")
        entered = request.form["otp"].strip()
        db = SessionLocal()
        try:
            otp = db.query(OTPToken).filter(OTPToken.user_id == u_id, OTPToken.token == entered, OTPToken.used == False).first()
            if not otp or otp.expires_at < datetime.datetime.utcnow():
                flash("Invalid or expired OTP")
                return redirect(url_for("verify_otp"))
            otp.used = True
            user = db.query(User).get(u_id)
            token = secrets.token_urlsafe(32)
            user.session_token = token
            db.add(otp); db.add(user); db.commit()
            session.pop("tmp_user_id", None)
            session["session_token"] = token
            # store email in session for UI (avatar, header)
            try:
                session["email"] = user.email
            except Exception:
                pass
            flash("Login successful")
            return redirect(url_for("dashboard"))
        finally:
            db.close()
    return render_template("verify_otp.html", user=get_user_by_session())


@app.route("/resend_otp", methods=["POST"])
def resend_otp():
    u_id = session.get("tmp_user_id")
    if not u_id:
        flash("No pending login to resend OTP for. Please login first.")
        return redirect(url_for("login"))
    last = session.get("otp_sent_at")
    now = time.time()
    cooldown = 30
    if last and (now - last) < cooldown:
        wait = int(cooldown - (now - last))
        flash(f"Please wait {wait} seconds before resending OTP.")
        return redirect(url_for("verify_otp"))

    db = SessionLocal()
    try:
        user = db.query(User).get(u_id)
        if not user:
            flash("User not found; please login again.")
            return redirect(url_for("login"))
        token = f"{secrets.randbelow(10**6):06d}"
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=OTP_EXPIRY_SECONDS)
        otp = OTPToken(user_id=user.id, token=token, expires_at=expires_at, used=False)
        db.add(otp)
        db.commit()
        session["otp_sent_at"] = time.time()
        send_otp_email(user.email, token)
        flash("OTP resent to your email (check console if SMTP disabled)")
        # store OTP in session for dev visibility when SMTP is disabled
        try:
            from config import SMTP_ENABLED as _SMTP_ENABLED2
        except Exception:
            _SMTP_ENABLED2 = False
        if not _SMTP_ENABLED2:
            session["last_otp"] = token
        return redirect(url_for("verify_otp"))
    finally:
        db.close()

@app.route("/logout")
def logout():
    session.pop("session_token", None)
    session.pop("email", None)
    flash("Logged out")
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    user = get_user_by_session()
    if not user:
        return redirect(url_for("login"))
    db = SessionLocal()
    try:
        files = db.query(FileModel).filter(FileModel.user_id == user.id, FileModel.deleted_at == None).all()
        used = user.used_bytes or 0
        quota = user.quota_bytes or DEFAULT_QUOTA_BYTES
        return render_template("dashboard.html", user=user, files=files, used=used, quota=quota)
    finally:
        db.close()

@app.route("/upload", methods=["POST"])
def upload():
    user = get_user_by_session()
    if not user:
        return redirect(url_for("login"))
    f = request.files.get("file")
    if not f:
        flash("No file")
        return redirect(url_for("dashboard"))
    db = SessionLocal()
    try:
        tmp_path = save_chunk_to_temp(f.stream)
        size = os.path.getsize(tmp_path)
        if (user.used_bytes or 0) + size > (user.quota_bytes or DEFAULT_QUOTA_BYTES):
            os.remove(tmp_path)
            flash("Quota exceeded")
            return redirect(url_for("dashboard"))
        dest = finalize_upload(tmp_path, user.id, f.filename)
        file_row = FileModel(user_id=user.id, filename=os.path.basename(dest), storage_path=dest, size_bytes=size)
        db.add(file_row)
        user.used_bytes = (user.used_bytes or 0) + size
        db.add(user)
        db.commit()
        flash("Upload successful")
        return redirect(url_for("dashboard"))
    finally:
        db.close()

@app.route("/download/<int:file_id>")
def download_file(file_id):
    user = get_user_by_session()
    if not user:
        return redirect(url_for("login"))
    db = SessionLocal()
    try:
        f = db.query(FileModel).get(file_id)
        if not f or f.user_id != user.id or f.deleted_at is not None:
            flash("File not found")
            return redirect(url_for("dashboard"))
        directory = os.path.dirname(f.storage_path)
        filename = os.path.basename(f.storage_path)
        return send_from_directory(directory, filename, as_attachment=True)
    finally:
        db.close()

@app.route("/delete/<int:file_id>")
def delete_file(file_id):
    user = get_user_by_session()
    if not user:
        return redirect(url_for("login"))
    db = SessionLocal()
    try:
        f = db.query(FileModel).get(file_id)
        if not f or f.user_id != user.id:
            flash("File not found")
            return redirect(url_for("dashboard"))
        f.deleted_at = datetime.datetime.utcnow()
        user.used_bytes = max(0, (user.used_bytes or 0) - (f.size_bytes or 0))
        db.add(f); db.add(user); db.commit()
        flash("File deleted (soft)")
        return redirect(url_for("dashboard"))
    finally:
        db.close()

@app.route("/upgrade", methods=["POST"])
def upgrade_quota():
    user = get_user_by_session()
    if not user:
        return redirect(url_for("login"))
    db = SessionLocal()
    try:
        user.quota_bytes = (user.quota_bytes or DEFAULT_QUOTA_BYTES) + 5 * 1024 * 1024 * 1024
        db.add(user); db.commit()
        flash("Quota increased by 5GB")
        return redirect(url_for("dashboard"))
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting AquaNet web app on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
