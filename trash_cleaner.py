import datetime
import os
from models import SessionLocal, File, User
from config import TRASH_RETENTION_DAYS

def purge_old_trashed():
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=TRASH_RETENTION_DAYS)
    db = SessionLocal()
    try:
        trashed = db.query(File).filter(File.deleted_at != None, File.deleted_at < cutoff).all()
        print(f"Found {len(trashed)} trashed files older than {TRASH_RETENTION_DAYS} days")
        for f in trashed:
            size = f.size_bytes or 0
            uid = f.user_id
            storage_path = f.storage_path
            try:
                user = db.query(User).get(uid)
                if user:
                    user.used_bytes = max(0, (user.used_bytes or 0) - size)
                    db.add(user)
                db.delete(f)
                db.commit()
            except Exception as e:
                db.rollback()
                print("DB error while purging", f.id, e)
                continue
            try:
                if storage_path and os.path.exists(storage_path):
                    os.remove(storage_path)
                    print("Deleted file from disk:", storage_path)
            except Exception as e:
                print("Error deleting file from disk:", storage_path, e)
    finally:
        db.close()

if __name__ == "__main__":
    purge_old_trashed()
