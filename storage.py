import os
import uuid
import shutil
from typing import Iterator
from config import UPLOAD_DIR, TMP_DIR

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

def save_chunk_to_temp(stream, upload_id=None) -> str:
    """
    Accept the whole file stream and write to a temp file,
    returning the temp path.
    """
    if upload_id is None:
        upload_id = str(uuid.uuid4())
    tmp_path = os.path.join(TMP_DIR, f"{upload_id}.tmp")
    # stream is expected to be a file-like binary stream (e.g. werkzeug FileStorage.stream)
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(stream, f)
    return tmp_path

def finalize_upload(tmp_path: str, user_id: int, filename: str) -> str:
    user_dir = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    dest = os.path.join(user_dir, filename)
    # if file exists, create unique name
    base, ext = os.path.splitext(filename)
    i = 1
    while os.path.exists(dest):
        dest = os.path.join(user_dir, f"{base}({i}){ext}")
        i += 1
    shutil.move(tmp_path, dest)
    return dest

def read_file_in_chunks(path: str, chunk_size: int = 8192) -> Iterator[bytes]:
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            yield data
import os
import uuid
import shutil
from typing import Iterator
from config import UPLOAD_DIR, TMP_DIR

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

def save_chunk_to_temp(stream, upload_id=None) -> str:
    """
    For simplicity we accept the whole file stream and write to a temp file,
    returning the temp path.
    """
    if upload_id is None:
        upload_id = str(uuid.uuid4())
    tmp_path = os.path.join(TMP_DIR, f"{upload_id}.tmp")
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(stream, f)
    return tmp_path

def finalize_upload(tmp_path: str, user_id: int, filename: str) -> str:
    user_dir = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    dest = os.path.join(user_dir, filename)
    # if file exists, create unique name
    base, ext = os.path.splitext(filename)
    i = 1
    while os.path.exists(dest):
        dest = os.path.join(user_dir, f"{base}({i}){ext}")
        i += 1
    shutil.move(tmp_path, dest)
    return dest

def read_file_in_chunks(path: str, chunk_size: int = 8192) -> Iterator[bytes]:
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            yield data
