import os
from config import UPLOAD_DIR
from pathlib import Path
import uuid

def make_user_dir(user_id: int):
    user_dir = Path(UPLOAD_DIR) / f"user_{user_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    return str(user_dir)

def save_chunk_to_temp(user_id: int, filename: str, chunk: bytes, upload_id: str = None):
    user_dir = make_user_dir(user_id)
    if not upload_id:
        upload_id = str(uuid.uuid4())
    tmp_path = Path(user_dir) / f"{upload_id}.upload"
    with open(tmp_path, "ab") as f:
        f.write(chunk)
    return str(tmp_path), upload_id

def finalize_upload(tmp_path: str, user_id: int, filename: str):
    user_dir = make_user_dir(user_id)
    final_name = Path(user_dir) / filename
    os.replace(tmp_path, final_name)
    return str(final_name)

def read_file_in_chunks(path: str, chunk_size: int = 64 * 1024):
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            yield data
