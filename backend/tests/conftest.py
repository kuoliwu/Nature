import os
import tempfile
from pathlib import Path

import pytest

# 必須在 import app 之前設定，讓測試使用獨立的暫存資料庫
_tmp = Path(tempfile.mkdtemp())
os.environ["APP_ENV_FILE"] = str(_tmp / "no.env")  # 不讀 backend/.env，避免真的寄信或用到正式網址
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(_tmp / "storage")
os.environ["ADMIN_INIT_KEY"] = "test-key"
os.environ["PUBLIC_URL_FILE"] = str(_tmp / "public_url.txt")
for key in ("PUBLIC_BASE_URL", "SMTP_HOST", "CLOUDFLARE_TUNNEL_TOKEN", "PDF_FONT_PATH"):
    os.environ.pop(key, None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# 系統金鑰；admin_token fixture 執行後會再加上管理者的 Authorization header
ADMIN = {"X-Admin-Key": "test-key"}
ADMIN_LOGIN = {"phone": "0900000000", "password": "admin-pass-123"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client) -> str:
    """建立資料庫與第一位最高管理者，並讓 ADMIN header 帶上登入憑證"""
    client.post("/init-db", headers=ADMIN)
    r = client.post("/auth/setup", headers=ADMIN, json={"name": "測試管理者", **ADMIN_LOGIN})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    ADMIN["Authorization"] = f"Bearer {token}"
    return token
