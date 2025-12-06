from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import SessionLocal, User, Admin, Node, File
from passlib.hash import bcrypt
import datetime
import os

def register_admin_routes(app):
    bp = Blueprint("admin", __name__, template_folder="templates", static_folder="static")

    @bp.route("/", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            db = SessionLocal()
            admin = db.query(Admin).filter(Admin.username == username).first()
            db.close()
            if admin and bcrypt.verify(password, admin.password_hash):
                session["admin_id"] = admin.id
                return redirect(url_for("admin.dashboard"))
            else:
                flash("invalid credentials", "danger")
        return render_template("login.html")

    @bp.route("/dashboard")
    def dashboard():
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        total_users = db.query(User).count()
        total_files = db.query(File).filter(File.deleted_at == None).count()
        total_storage = sum([u.used_bytes for u in db.query(User).all()]) if total_users else 0
        nodes = db.query(Node).all()
        db.close()
        return render_template("dashboard.html", total_users=total_users, total_files=total_files, total_storage=total_storage, nodes=nodes)

    @bp.route("/users")
    def users():
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        users = db.query(User).all()
        db.close()
        return render_template("users.html", users=users)

    @bp.route("/users/delete/<int:user_id>", methods=["POST"])
    def delete_user(user_id):
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        user = db.query(User).get(user_id)
        if user:
            files = db.query(File).filter(File.user_id == user.id).all()
            for f in files:
                try:
                    if f.storage_path and os.path.exists(f.storage_path):
                        os.remove(f.storage_path)
                except Exception:
                    pass
                db.delete(f)
            db.delete(user)
            db.commit()
            flash("user deleted permanently", "success")
        db.close()
        return redirect(url_for("admin.users"))

    @bp.route("/nodes")
    def nodes():
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        nodes = db.query(Node).all()
        db.close()
        return render_template("nodes.html", nodes=nodes)

    @bp.route("/nodes/add", methods=["POST"])
    def add_node():
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        name = request.form.get("name")
        address = request.form.get("address")
        capacity = int(request.form.get("capacity") or 0)
        db = SessionLocal()
        node = Node(name=name, address=address, capacity=capacity, status="online", last_heartbeat=datetime.datetime.utcnow())
        db.add(node)
        db.commit()
        db.close()
        flash("node added", "success")
        return redirect(url_for("admin.nodes"))

    @bp.route("/nodes/delete/<int:node_id>", methods=["POST"])
    def delete_node(node_id):
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        node = db.query(Node).get(node_id)
        if node:
            db.delete(node)
            db.commit()
            flash("node removed", "success")
        db.close()
        return redirect(url_for("admin.nodes"))

    @bp.route("/trash")
    def trash():
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        trashed_files = db.query(File).filter(File.deleted_at != None).all()
        db.close()
        return render_template("trash.html", files=trashed_files)

    @bp.route("/trash/restore/<int:file_id>", methods=["POST"])
    def trash_restore(file_id):
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        f = db.query(File).get(file_id)
        if f and f.deleted_at:
            f.deleted_at = None
            db.add(f)
            db.commit()
            flash("file restored", "success")
        db.close()
        return redirect(url_for("admin.trash"))

    @bp.route("/trash/purge/<int:file_id>", methods=["POST"])
    def trash_purge(file_id):
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        db = SessionLocal()
        f = db.query(File).get(file_id)
        if f:
            size = f.size_bytes or 0
            user = db.query(User).get(f.user_id)
            try:
                db.delete(f)
                if user:
                    user.used_bytes = max(0, (user.used_bytes or 0) - size)
                    db.add(user)
                db.commit()
            except Exception:
                db.rollback()
            try:
                if f.storage_path and os.path.exists(f.storage_path):
                    os.remove(f.storage_path)
            except Exception:
                pass
            flash("file purged permanently", "success")
       
        db.close()
        return redirect(url_for("admin.trash"))

    @bp.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("admin.login"))

    app.register_blueprint(bp, url_prefix="/admin")
