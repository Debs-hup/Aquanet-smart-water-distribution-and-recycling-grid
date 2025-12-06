from concurrent import futures
import grpc
import time
import os
import secrets
import datetime
import threading

import protos.cloud_storage_pb2 as pb2
import protos.cloud_storage_pb2_grpc as pb2_grpc


from models import SessionLocal, init_db, User, File, OTPToken, Node, Admin
from storage import save_chunk_to_temp, finalize_upload, read_file_in_chunks
from config import DEFAULT_QUOTA_BYTES, OTP_EXPIRY_SECONDS, UPLOAD_DIR, SMTP_ENABLED, USER_QUOTA_ON_LOGIN

from passlib.hash import bcrypt
from flask import Flask
from Admin.adminpanel import create_admin_app


init_db()

_ONE_DAY_IN_SECONDS = 60 * 60 * 24

# --- AuthServicer ---
class AuthServicer(pb2_grpc.AuthServiceServicer):
    def Signup(self, request, context):
        db = SessionLocal()
        try:
            if db.query(User).filter(User.email == request.email).first():
                return pb2.SignupResponse(user_id=0, message="email already registered")
            pw_hash = bcrypt.hash(request.password)
            user = User(email=request.email, password_hash=pw_hash, full_name=request.full_name)
            db.add(user)
            db.commit()
            db.refresh(user)
            return pb2.SignupResponse(user_id=user.id, message="ok")
        finally:
            db.close()

    def Login(self, request, context):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == request.email).first()
            if not user or not bcrypt.verify(request.password, user.password_hash):
                return pb2.LoginResponse(user_id=0, otp_sent=False, message="invalid credentials")
            token = f"{secrets.randbelow(10**6):06d}"
            expires_at = datetime.datetime.datetime.utcnow() if False else (datetime.datetime.utcnow() + datetime.timedelta(seconds=OTP_EXPIRY_SECONDS))
            otp = OTPToken(user_id=user.id, token=token, expires_at=expires_at)
            db.add(otp)
            db.commit()
            if SMTP_ENABLED:
                # TODO: integrate SMTP sending
                pass
            else:
                print(f"[OTP for user {user.email}] token={token} (expires {expires_at.isoformat()} UTC)")
            return pb2.LoginResponse(user_id=user.id, otp_sent=True, message="otp sent")
        finally:
            db.close()

    def VerifyOTP(self, request, context):
        db = SessionLocal()
        try:
            otp = db.query(OTPToken).filter(OTPToken.user_id == request.user_id,
                                           OTPToken.token == request.otp,
                                           OTPToken.used == False).first()
            if not otp:
                return pb2.VerifyOTPResponse(ok=False, session_token="")
            if otp.expires_at < datetime.datetime.utcnow():
                return pb2.VerifyOTPResponse(ok=False, session_token="")
            otp.used = True
            user = db.query(User).get(request.user_id)
            if not user:
                return pb2.VerifyOTPResponse(ok=False, session_token="")
            token = secrets.token_urlsafe(32)
            user.session_token = token
            try:
                if (user.quota_bytes or 0) < USER_QUOTA_ON_LOGIN:
                    user.quota_bytes = USER_QUOTA_ON_LOGIN
            except Exception:
                pass
            db.add(otp)
            db.add(user)
            db.commit()
            return pb2.VerifyOTPResponse(ok=True, session_token=token)
        finally:
            db.close()

# --- FileServicer ---
class FileServicer(pb2_grpc.FileServiceServicer):
    def Upload(self, request_iterator, context):
        db = SessionLocal()
        tmp_path = None
        upload_id = None
        user_id = None
        filename = None
        total_expected = None
        uploaded = 0
        try:
            for msg in request_iterator:
                if msg.HasField("init"):
                    init = msg.init
                    user_id = init.user_id
                    filename = init.filename
                    total_expected = init.total_bytes
                    user = db.query(User).get(user_id)
                    if not user:
                        return pb2.UploadResponse(ok=False, message="user not found", file_id=0)
                    continue
                else:
                    chunk = msg.chunk_data
                    if user_id is None:
                        return pb2.UploadResponse(ok=False, message="missing init", file_id=0)
                    with db.begin():
                        try:
                            user = db.query(User).with_for_update().get(user_id)
                        except Exception:
                            user = db.query(User).get(user_id)
                        if not user:
                            return pb2.UploadResponse(ok=False, message="user not found", file_id=0)
                        if (user.used_bytes or 0) + uploaded + len(chunk) > (user.quota_bytes or 0):
                            return pb2.UploadResponse(ok=False, message="quota exceeded during upload", file_id=0)
                    tmp_path, upload_id = save_chunk_to_temp(user_id, filename, chunk, upload_id)
                    uploaded += len(chunk)
            if user_id is None:
                return pb2.UploadResponse(ok=False, message="no upload data", file_id=0)
            final_path = finalize_upload(tmp_path, user_id, filename)
            with db.begin():
                try:
                    user = db.query(User).with_for_update().get(user_id)
                except Exception:
                    user = db.query(User).get(user_id)
                if (user.used_bytes or 0) + uploaded > (user.quota_bytes or 0):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                    return pb2.UploadResponse(ok=False, message="quota exceeded on finalize", file_id=0)
                file_row = File(user_id=user_id, filename=filename, storage_path=final_path, size_bytes=uploaded)
                db.add(file_row)
                user.used_bytes = (user.used_bytes or 0) + uploaded
            db.commit()
            db.refresh(file_row)
            return pb2.UploadResponse(ok=True, message="upload complete", file_id=file_row.id)
        except Exception as e:
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return pb2.UploadResponse(ok=False, message="internal error", file_id=0)
        finally:
            db.close()

    def DownloadFile(self, request, context):
        db = SessionLocal()
        try:
            row = db.query(File).filter(File.id == request.file_id, File.user_id == request.user_id, File.deleted_at == None).first()
            if not row:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("file not found")
                return
            for chunk in read_file_in_chunks(row.storage_path):
                yield pb2.DownloadChunk(chunk_data=chunk)
        finally:
            db.close()

    def DeleteFile(self, request, context):
        db = SessionLocal()
        try:
            with db.begin():
                try:
                    file_row = db.query(File).filter(File.id == request.file_id, File.user_id == request.user_id).with_for_update().first()
                except Exception:
                    file_row = db.query(File).filter(File.id == request.file_id, File.user_id == request.user_id).first()
                if not file_row:
                    return pb2.DeleteFileResponse(ok=False, message="file not found")
                if file_row.deleted_at:
                    return pb2.DeleteFileResponse(ok=False, message="already trashed")
                file_row.deleted_at = datetime.datetime.utcnow()
                db.add(file_row)
            db.commit()
            return pb2.DeleteFileResponse(ok=True, message="moved to trash")
        finally:
            db.close()

    def RestoreFile(self, request, context):
        db = SessionLocal()
        try:
            with db.begin():
                try:
                    file_row = db.query(File).filter(File.id == request.file_id, File.user_id == request.user_id).with_for_update().first()
                except Exception:
                    file_row = db.query(File).filter(File.id == request.file_id, File.user_id == request.user_id).first()
                if not file_row:
                    return pb2.RestoreFileResponse(ok=False, message="file not found")
                if not file_row.deleted_at:
                    return pb2.RestoreFileResponse(ok=False, message="file not in trash")
                file_row.deleted_at = None
                db.add(file_row)
            db.commit()
            return pb2.RestoreFileResponse(ok=True, message="restored")
        finally:
            db.close()

    def ListFiles(self, request, context):
        db = SessionLocal()
        try:
            rows = db.query(File).filter(File.user_id == request.user_id).all()
            out = []
            for r in rows:
                out.append(pb2.FileMeta(
                    id=r.id, filename=r.filename, size_bytes=r.size_bytes,
                    created_at=r.created_at.isoformat() if r.created_at else "", deleted=(r.deleted_at is not None)
                ))
            return pb2.ListFilesResponse(files=out)
        finally:
            db.close()

# --- NodeServicer ---
class NodeServicer(pb2_grpc.NodeServiceServicer):
    def RegisterNode(self, request, context):
        db = SessionLocal()
        try:
            node = Node(name=request.name, address=request.address, capacity=request.capacity, status="online", last_heartbeat=datetime.datetime.utcnow())
            db.add(node)
            db.commit()
            db.refresh(node)
            return pb2.RegisterNodeResponse(node_id=node.id, message="registered")
        finally:
            db.close()

    def Heartbeat(self, request, context):
        db = SessionLocal()
        try:
            node = db.query(Node).get(request.node_id)
            if not node:
                return pb2.HeartbeatResponse(ok=False, message="node not found")
            node.used_bytes = request.used_bytes
            node.status = request.status or "online"
            node.last_heartbeat = datetime.datetime.utcnow()
            db.add(node)
            db.commit()
            return pb2.HeartbeatResponse(ok=True, message="ok")
        finally:
            db.close()

    def GetNodes(self, request, context):
        db = SessionLocal()
        try:
            nodes = db.query(Node).all()
            out = []
            for n in nodes:
                out.append(pb2.NodeInfo(
                    id=n.id, name=n.name, address=n.address, capacity=n.capacity,
                    used_bytes=n.used_bytes, last_heartbeat=(n.last_heartbeat.isoformat() if n.last_heartbeat else ""), status=n.status
                ))
            return pb2.GetNodesResponse(nodes=out)
        finally:
            db.close()

    def RemoveNode(self, request, context):
        db = SessionLocal()
        try:
            node = db.query(Node).get(request.node_id)
            if not node:
                return pb2.RemoveNodeResponse(ok=False, message="node not found")
            db.delete(node)
            db.commit()
            return pb2.RemoveNodeResponse(ok=True, message="removed")
        finally:
            db.close()

# --- AdminServicer ---
class AdminServicer(pb2_grpc.AdminServiceServicer):
    def ListUsers(self, request, context):
        db = SessionLocal()
        try:
            users = db.query(User).all()
            out = []
            for u in users:
                out.append(pb2.UserInfo(
                    id=u.id, email=u.email, full_name=u.full_name or "", quota_bytes=u.quota_bytes or 0,
                    used_bytes=u.used_bytes or 0, created_at=(u.created_at.isoformat() if u.created_at else "")
                ))
            return pb2.ListUsersResponse(users=out)
        finally:
            db.close()

    def DeleteUser(self, request, context):
        db = SessionLocal()
        try:
            user = db.query(User).get(request.user_id)
            if not user:
                return pb2.DeleteUserAdminResponse(ok=False, message="user not found")
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
            return pb2.DeleteUserAdminResponse(ok=True, message="deleted")
        finally:
            db.close()

    def UpdateQuota(self, request, context):
        db = SessionLocal()
        try:
            user = db.query(User).get(request.user_id)
            if not user:
                return pb2.UpdateQuotaResponse(ok=False, message="user not found")
            user.quota_bytes = request.new_quota_bytes
            db.add(user)
            db.commit()
            return pb2.UpdateQuotaResponse(ok=True, message="quota updated")
        finally:
            db.close()

    def PurgeFile(self, request, context):
        db = SessionLocal()
        try:
            file_row = db.query(File).filter(File.id == request.file_id, File.user_id == request.user_id).with_for_update().first()
            if not file_row:
                return pb2.PurgeFileResponse(ok=False, message="file not found")
            size = file_row.size_bytes or 0
            user = db.query(User).get(file_row.user_id)
            db.delete(file_row)
            if user:
                user.used_bytes = max(0, (user.used_bytes or 0) - size)
                db.add(user)
            db.commit()
            try:
                if file_row.storage_path and os.path.exists(file_row.storage_path):
                    os.remove(file_row.storage_path)
            except Exception:
                pass
            return pb2.PurgeFileResponse(ok=True, message="purged")
        finally:
            db.close()

# --- Serve both gRPC and Flask admin panel ---
def serve_grpc(host='[::]:50051'):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=12))
    pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    pb2_grpc.add_FileServiceServicer_to_server(FileServicer(), server)
    pb2_grpc.add_NodeServiceServicer_to_server(NodeServicer(), server)
    pb2_grpc.add_AdminServiceServicer_to_server(AdminServicer(), server)
    server.add_insecure_port(host)
    server.start()
    print(f"gRPC server listening on {host}")
    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)

def serve_flask_admin():
    app = create_admin_app()
    print("Starting Flask admin on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

if __name__ == "__main__":
    t = threading.Thread(target=serve_flask_admin, daemon=True)
    t.start()
    serve_grpc()
