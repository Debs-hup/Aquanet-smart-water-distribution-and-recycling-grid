import os

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///cloud_storage.db")
DEFAULT_QUOTA_BYTES = int(os.environ.get("DEFAULT_QUOTA_BYTES", 50 * 1024 * 1024))  # 50 MB default
OTP_EXPIRY_SECONDS = 300  # 5 minutes
SMTP_ENABLED = False
SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# Trash retention in days (files older than this in trash will be purged permanently)
TRASH_RETENTION_DAYS = int(os.environ.get("TRASH_RETENTION_DAYS", 30))

# Assign 5 GiB to each user on successful OTP verify (5 * 1024^3)
USER_QUOTA_ON_LOGIN = int(os.environ.get("USER_QUOTA_ON_LOGIN", 5368709120))
