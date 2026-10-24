import os
import tempfile
from pathlib import Path

import pytest

# 必須在 import app 之前設定，讓測試使用獨立的暫存資料庫
_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(_tmp / "storage")
os.environ["ADMIN_INIT_KEY"] = "test-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = {"X-Admin-Key": "test-key"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
