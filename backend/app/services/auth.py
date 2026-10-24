"""管理端登入：手機號碼 + 密碼 → JWT；以及依權限代碼檢查的 FastAPI dependency"""

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import PERMISSIONS, User, UserRole

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# 手機號碼與密碼
# ---------------------------------------------------------------------------
def normalize_phone(phone: str) -> str:
    """去掉空白、橫線、括號：0912-345-678 → 0912345678"""
    return re.sub(r"[\s\-()]", "", phone.strip())


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$")
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


# ---------------------------------------------------------------------------
# 登入失敗次數限制（記憶體內；重啟後歸零即可）
# ---------------------------------------------------------------------------
MAX_FAILURES = 5
LOCK_SECONDS = 300
_failures: dict[str, list[float]] = {}


def check_login_allowed(phone: str) -> None:
    recent = [t for t in _failures.get(phone, []) if time.monotonic() - t < LOCK_SECONDS]
    _failures[phone] = recent
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "密碼錯誤次數過多，請 5 分鐘後再試")


def record_login_failure(phone: str) -> None:
    _failures.setdefault(phone, []).append(time.monotonic())


def clear_login_failures(phone: str) -> None:
    _failures.pop(phone, None)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _jwt_secret() -> str:
    """優先使用 .env 的 JWT_SECRET；沒有設定時自動產生並存在 data/ 下，重啟後登入狀態仍有效"""
    if settings.jwt_secret:
        return settings.jwt_secret
    path = settings.jwt_secret_file
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48), "utf-8")
        path.chmod(0o600)
    return path.read_text("utf-8").strip()


def create_access_token(user: User) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(days=settings.token_expire_days)
    # pwd：密碼雜湊的一小段，改密碼後舊 token 自動失效
    payload = {"sub": str(user.id), "exp": expires, "pwd": (user.password_hash or "")[-8:]}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256"), expires


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "請重新登入", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthorized
    if "sub" not in payload or payload.get("typ") == "download":  # 下載連結的 token 不能拿來登入
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or payload.get("pwd") != (user.password_hash or "")[-8:]:
        raise unauthorized
    return user


def create_download_token(data: dict, minutes: int = 5) -> tuple[str, datetime]:
    """短效下載連結：讓手機用瀏覽器直接下載檔案（瀏覽器無法帶登入 header）"""
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({**data, "typ": "download", "exp": expires}, _jwt_secret(), algorithm="HS256"), expires


def read_download_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "download" else None


# ---------------------------------------------------------------------------
# 權限
# ---------------------------------------------------------------------------
def user_permissions(user: User) -> set[str]:
    if user.role == UserRole.SUPER_ADMIN:
        return set(PERMISSIONS)
    return {p.permission for p in user.permissions}


def require_permission(code: str) -> Callable[..., User]:
    """用法：Depends(require_permission("project.manage"))"""
    if code not in PERMISSIONS:
        raise ValueError(f"未知的權限代碼 {code}")

    def dependency(user: User = Depends(get_current_user)) -> User:
        if code not in user_permissions(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"沒有「{PERMISSIONS[code]}」權限")
        return user

    return dependency


def require_any_permission(*codes: str) -> Callable[..., User]:
    """具備其中任一權限即可"""
    for code in codes:
        if code not in PERMISSIONS:
            raise ValueError(f"未知的權限代碼 {code}")

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not set(codes) & user_permissions(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "沒有檢視此資料的權限")
        return user

    return dependency
