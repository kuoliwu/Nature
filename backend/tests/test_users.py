import itertools

import pytest

from tests.conftest import ADMIN, ADMIN_LOGIN


_phones = (f"0955{n:06d}" for n in itertools.count(1))


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, phone: str, password: str):
    return client.post("/auth/login", json={"phone": phone, "password": password})


@pytest.fixture
def staff(client, admin_token):
    """建立只有「檢視預約」權限的一般人員，回傳 (id, token)"""
    phone = next(_phones)
    r = client.post("/users", headers=ADMIN, json={
        "name": "王助理", "phone": phone, "password": "staff-pass-1", "permissions": ["booking.view"],
    })
    assert r.status_code == 201, r.text
    token = login(client, phone, "staff-pass-1").json()["access_token"]
    return r.json()["id"], token, phone


def test_setup_only_once(client, admin_token):
    assert client.get("/health").json()["needs_setup"] is False
    r = client.post("/auth/setup", headers={"X-Admin-Key": "test-key"},
                    json={"name": "又一個", "phone": "0911111111", "password": "whatever-123"})
    assert r.status_code == 409


def test_login_and_me(client, admin_token):
    r = login(client, "0900-000-000", ADMIN_LOGIN["password"])  # 手機號碼格式會正規化
    assert r.status_code == 200
    me = client.get("/auth/me", headers=bearer(r.json()["access_token"])).json()
    assert me["role"] == "super_admin" and "user.manage" in me["permissions"]

    assert login(client, ADMIN_LOGIN["phone"], "wrong-password").status_code == 401


def test_requires_login(client, admin_token):
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers=bearer("garbage")).status_code == 401
    assert client.get("/projects", headers={"X-Admin-Key": "test-key"}).status_code == 401  # 金鑰不能代替登入


def test_lockout_after_failures(client, admin_token):
    for _ in range(5):
        assert login(client, "0987654321", "nope-nope").status_code == 401
    assert login(client, "0987654321", "nope-nope").status_code == 429


def test_staff_permissions(client, staff):
    user_id, token, _ = staff
    h = bearer(token)
    assert client.get("/projects", headers=h).status_code == 200          # 登入即可讀
    assert client.post("/projects", headers=h, json={"name": "x"}).status_code == 403
    assert client.get("/authorizations", headers=h).status_code == 200    # 有 booking.view
    assert client.get("/users", headers=h).status_code == 403

    # 加上 project.manage 後立即生效（不用重新登入）
    r = client.patch(f"/users/{user_id}", headers=ADMIN, json={"permissions": ["booking.view", "project.manage"]})
    assert r.json()["permissions"] == ["booking.view", "project.manage"]
    assert client.post("/projects", headers=h, json={"name": "人員建立的建案"}).status_code == 201


def test_password_reset_and_deactivate_invalidate_token(client, staff):
    user_id, token, phone = staff
    client.patch(f"/users/{user_id}", headers=ADMIN, json={"password": "new-pass-456"})
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401
    assert login(client, phone, "new-pass-456").status_code == 200

    client.patch(f"/users/{user_id}", headers=ADMIN, json={"is_active": False})
    assert login(client, phone, "new-pass-456").status_code == 403


def test_user_validation(client, staff):
    _, _, phone = staff
    dup = {"name": "重複", "phone": phone, "password": "password-1"}
    assert client.post("/users", headers=ADMIN, json=dup).status_code == 409
    bad = {"name": "亂設", "phone": "0922222222", "password": "password-1", "permissions": ["root"]}
    assert client.post("/users", headers=ADMIN, json=bad).status_code == 422
    short = {"name": "短", "phone": "0933333333", "password": "123"}
    assert client.post("/users", headers=ADMIN, json=short).status_code == 422


def test_cannot_lock_out_last_super_admin(client, admin_token):
    me = client.get("/auth/me", headers=ADMIN).json()
    assert client.patch(f"/users/{me['id']}", headers=ADMIN, json={"is_active": False}).status_code == 400
    assert client.patch(f"/users/{me['id']}", headers=ADMIN, json={"role": "staff"}).status_code == 400


def test_change_own_password(client, staff):
    _, token, phone = staff
    h = bearer(token)
    assert client.post("/auth/change-password", headers=h,
                       json={"old_password": "wrong", "new_password": "another-pass-1"}).status_code == 400
    r = client.post("/auth/change-password", headers=h,
                    json={"old_password": "staff-pass-1", "new_password": "another-pass-1"})
    assert r.status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401                      # 舊憑證失效
    assert client.get("/auth/me", headers=bearer(r.json()["access_token"])).status_code == 200
