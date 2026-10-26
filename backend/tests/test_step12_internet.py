"""管理 API 開放到外網（Tailscale Funnel）時的保護"""

import pytest

from tests.conftest import ADMIN

FUNNEL = {"X-Forwarded-For": "203.0.113.9", "Tailscale-Funnel-Request": "?1"}


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def test_local_only_paths_hidden_from_internet(client):
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert client.get(path).status_code == 200
        assert client.get(path, headers=FUNNEL).status_code == 404
    assert client.post("/init-db", headers={**ADMIN, **FUNNEL}).status_code == 404
    assert client.get("/db/status", headers={"X-Admin-Key": "test-key", **FUNNEL}).status_code == 404
    r = client.post("/auth/setup", headers={"X-Admin-Key": "test-key", **FUNNEL},
                    json={"name": "x", "phone": "0900111222", "password": "abc12345"})
    assert r.status_code == 404
    # 一般功能照常可用
    assert client.get("/health", headers=FUNNEL).status_code == 200
    assert client.get("/projects", headers={**ADMIN, **FUNNEL}).status_code == 200
    assert client.get("/health", headers=FUNNEL).headers["referrer-policy"] == "no-referrer"


def test_weak_passwords_rejected(client):
    for weak in ("abcdefgh", "12345678", "a1"):
        r = client.post("/users", headers=ADMIN, json={"name": "弱", "phone": "0955000111", "password": weak})
        assert r.status_code == 422, weak
    r = client.post("/users", headers=ADMIN, json={"name": "強", "phone": "0955000111", "password": "abcd1234"})
    assert r.status_code == 201, r.text


def test_login_limited_per_ip(client):
    ip = {"X-Forwarded-For": "198.51.100.7"}
    for i in range(20):  # 輪流猜不同帳號，單一帳號不會被鎖
        r = client.post("/auth/login", headers=ip, json={"phone": f"09770000{i:02d}", "password": "wrong-pass-1"})
        assert r.status_code == 401
    r = client.post("/auth/login", headers=ip, json={"phone": "0977999999", "password": "wrong-pass-1"})
    assert r.status_code == 429 and "15 分鐘" in r.json()["detail"]
    # 其他 IP 不受影響
    r = client.post("/auth/login", headers={"X-Forwarded-For": "198.51.100.8"}, json={"phone": "0977999999", "password": "x"})
    assert r.status_code == 401
