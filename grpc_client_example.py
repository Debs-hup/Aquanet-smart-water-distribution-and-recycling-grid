import grpc
from protos import cloud_storage_pb2 as pb2
from protos import cloud_storage_pb2_grpc as pb2_grpc
import os

SERVER = "localhost:50051"

def signup(stub, email, password, full_name=""):
    r = stub.Signup(pb2.SignupRequest(email=email, password=password, full_name=full_name))
    print("Signup:", r.user_id, r.message)
    return r.user_id

def login_and_verify(stub, email, password):
    r = stub.Login(pb2.LoginRequest(email=email, password=password))
    print("Login:", r.message)
    if not r.otp_sent:
        return None, None
    user_id = r.user_id
    otp = input("Enter OTP printed in server console: ").strip()
    v = stub.VerifyOTP(pb2.VerifyOTPRequest(user_id=user_id, otp=otp))
    print("Verify:", v.ok, "session_token:", v.session_token)
    return user_id, v.session_token

def upload_file(stub, user_id, filepath):
    filename = os.path.basename(filepath)
    total = os.path.getsize(filepath)
    def gen():
        yield pb2.UploadChunk(init=pb2.UploadInit(user_id=user_id, filename=filename, total_bytes=total))
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(64*1024)
                if not chunk:
                    break
                yield pb2.UploadChunk(chunk_data=chunk)
    resp = stub.Upload(gen())
    print("Upload:", resp.ok, resp.message, "file_id:", resp.file_id)
    return resp

def list_files(stub, user_id):
    r = stub.ListFiles(pb2.ListFilesRequest(user_id=user_id))
    print("Files:")
    for f in r.files:
        print(f"  {f.id} {f.filename} {f.size_bytes} deleted={f.deleted}")

def download_file(stub, user_id, file_id, outpath):
    req = pb2.DownloadFileRequest(user_id=user_id, file_id=file_id)
    with open(outpath, "wb") as f:
        for chunk in stub.DownloadFile(req):
            f.write(chunk.chunk_data)
    print("Downloaded to", outpath)

def delete_file(stub, user_id, file_id):
    r = stub.DeleteFile(pb2.DeleteFileRequest(user_id=user_id, file_id=file_id))
    print("Delete:", r.ok, r.message)

def restore_file(stub, user_id, file_id):
    r = stub.RestoreFile(pb2.RestoreFileRequest(user_id=user_id, file_id=file_id))
    print("Restore:", r.ok, r.message)

if __name__ == "__main__":
    with grpc.insecure_channel(SERVER) as channel:
        auth = pb2_grpc.AuthServiceStub(channel)
        files = pb2_grpc.FileServiceStub(channel)
        email = "alice@example.com"
        pw = "password123"
        signup(auth, email, pw, "Alice")
        uid, token = login_and_verify(auth, email, pw)
        if uid:
            tmp = "small_test.txt"
            with open(tmp, "wb") as f:
                f.write(b"A"*1024*10)
            upload_file(files, uid, tmp)
            list_files(files, uid)
