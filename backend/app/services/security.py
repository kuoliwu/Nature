import hashlib
import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


def hash_id_number(id_number: str) -> str:
    """身分證字號不落地明文，只存 SHA-256(鹽 + 正規化字號)"""
    normalized = id_number.strip().upper()
    return hashlib.sha256(f"{settings.id_hash_salt}:{normalized}".encode()).hexdigest()


def require_admin_key(x_admin_key: str = Header(..., description="與 .env 的 ADMIN_INIT_KEY 相同")):
    """系統層級操作（建立資料庫、建立第一位管理者）用的金鑰；一般管理功能改用登入（services/auth.py）"""
    if not secrets.compare_digest(x_admin_key, settings.admin_init_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "X-Admin-Key 錯誤")
