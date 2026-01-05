import os

BASE_DIR = os.path.dirname(__file__)
# File storage paths
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
TMP_DIR = os.path.join(UPLOAD_DIR, "tmp")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

# Database & quotas
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aquanet.db")
DEFAULT_QUOTA_BYTES = int(os.getenv("DEFAULT_QUOTA_BYTES", 5 * 1024 * 1024 * 1024))  # 5 GB

# SMTP / OTP settings (read from environment for safety)
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "False").lower() in ("1", "true", "yes")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.example.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "user@example.com")
SMTP_PASS = os.getenv("SMTP_PASS", "password")
OTP_EXPIRY_SECONDS = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))  # seconds

# Admin defaults (override via env)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me")
USER_QUOTA_ON_LOGIN = DEFAULT_QUOTA_BYTES
