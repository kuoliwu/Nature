"""M3 第二階段：寄送預約邀請、屋主線上預約"""

import re
import threading
from datetime import date, datetime, timedelta
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.models import TimeSlot, UnitInvite
from app.services.booking import book
from tests.conftest import ADMIN

TOMORROW = date.today() + timedelta(days=1)


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def outbox() -> set:
    return set((settings.storage_dir / "outbox").glob("*.eml"))


def mails_since(before: set) -> list:
    return [message_from_bytes(p.read_bytes(), policy=policy.default) for p in sorted(outbox() - before)]


@pytest.fixture
def setup(client):
    """建案 + 4 戶（其中一戶沒 Email）+ 明後兩天 09:00–10:00 的時段（每格 3 組）"""
    pid = client.post("/projects", headers=ADMIN, json={"name": "預約測試建案", "address": "台北市測試路 1 號"}).json()["id"]
    units = {}
    for n, email in [("A-1", "a1@example.com"), ("A-2", "a2@example.com"), ("A-3", "a3@example.com"), ("A-4", "a4@example.com"), ("B-1", None)]:
        units[n] = client.post(f"/projects/{pid}/units", headers=ADMIN, json={
            "unit_no": n, "owner_name": f"屋主{n}", "owner_phone": "0912000000", "owner_email": email,
        }).json()["id"]
    batch = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "交屋健檢", "start_date": str(TOMORROW), "end_date": str(TOMORROW + timedelta(days=1)),
        "day_start": "09:00", "day_end": "10:00",
    }).json()
    slots = [s["id"] for d in batch["days"] for s in d["slots"]]
    return {"pid": pid, "units": units, "batch": batch["id"], "slots": slots}


def send(client, batch_id, **body):
    return client.post(f"/batches/{batch_id}/invites/send", headers=ADMIN, json=body).json()


def token_of(client, batch_id, unit_no) -> str:
    row = next(r for r in client.get(f"/batches/{batch_id}/invites", headers=ADMIN).json() if r["unit_no"] == unit_no)
    return row["link"].rsplit("/", 1)[1]


def owner_book(client, token, slot_id, email="owner@example.com"):
    return client.post(f"/api/public/book/{token}", json={
        "slot_id": slot_id, "contact_name": "王小明", "contact_phone": "0912345678", "contact_email": email,
    })


def test_send_invites(client, setup):
    b = setup["batch"]
    before = outbox()
    r = send(client, b)
    assert r["sent"] == ["A-1", "A-2", "A-3", "A-4"] and r["no_email"] == ["B-1"]
    mails = mails_since(before)
    assert len(mails) == 4
    mail = next(m for m in mails if m["To"] == "a1@example.com")
    assert "預約邀請" in mail["Subject"] and "/book/" in mail.get_content()

    assert send(client, b)["already_sent"] == ["A-1", "A-2", "A-3", "A-4"]  # 不重複寄
    again = send(client, b, unit_ids=[setup["units"]["A-1"]], resend=True)
    assert again["sent"] == ["A-1"]
    row = next(x for x in client.get(f"/batches/{b}/invites", headers=ADMIN).json() if x["unit_no"] == "A-1")
    assert row["send_count"] == 2 and row["booking"] is None

    # 沒有 Email 的戶：只產生連結，用 LINE 傳
    link = client.post(f"/batches/{b}/units/{setup['units']['B-1']}/invite-link", headers=ADMIN).json()
    assert link["link"].endswith(token_of(client, b, "B-1")) and link["sent_at"] is None


def test_owner_books_and_gets_confirmation(client, setup):
    b = setup["batch"]
    send(client, b)
    token = token_of(client, b, "A-1")
    assert client.get(f"/book/{token}").status_code == 200

    info = client.get(f"/api/public/book/{token}").json()
    assert info["project_name"] == "預約測試建案" and info["unit_no"] == "A-1" and info["place"] == "台北市測試路 1 號"
    assert info["defaults"]["contact_email"] == "a1@example.com" and info["current"] is None
    assert [len(d["slots"]) for d in info["days"]] == [2, 2] and info["days"][0]["slots"][0]["remaining"] == 3

    before = outbox()
    r = owner_book(client, token, setup["slots"][0])
    assert r.status_code == 200, r.text
    assert r.json()["current"]["slot_id"] == setup["slots"][0]
    [mail] = mails_since(before)
    assert "預約確認" in mail["Subject"] and "09:00–09:30" in mail.get_content()

    row = next(x for x in client.get(f"/batches/{b}/invites", headers=ADMIN).json() if x["unit_no"] == "A-1")
    assert row["booking"]["start_time"] == "09:00:00" and row["last_opened_at"] is not None
    slot = client.get(f"/batches/{b}", headers=ADMIN).json()["days"][0]["slots"][0]
    assert (slot["booked"], slot["units"]) == (1, ["A-1"])
    assert send(client, b, resend=True)["already_booked"] == ["A-1"]  # 已預約的不再寄邀請


def test_capacity_reschedule_and_cancel(client, setup):
    b, s = setup["batch"], setup["slots"]
    send(client, b)
    tokens = {n: token_of(client, b, n) for n in ["A-1", "A-2", "A-3", "A-4"]}
    for n in ["A-1", "A-2", "A-3"]:
        assert owner_book(client, tokens[n], s[0]).status_code == 200
    full = owner_book(client, tokens["A-4"], s[0])
    assert full.status_code == 409 and "額滿" in full.json()["detail"]
    assert client.get(f"/api/public/book/{tokens['A-4']}").json()["days"][0]["slots"][0]["remaining"] == 0

    # A-1 改期 → 空出一個名額給 A-4
    before = outbox()
    assert owner_book(client, tokens["A-1"], s[1]).status_code == 200
    assert "改期" in mails_since(before)[0]["Subject"]
    assert owner_book(client, tokens["A-4"], s[0]).status_code == 200

    # A-2 自己取消 → 可再預約
    before = outbox()
    assert client.post(f"/api/public/book/{tokens['A-2']}/cancel").status_code == 204
    assert "取消" in mails_since(before)[0]["Subject"]
    assert client.get(f"/api/public/book/{tokens['A-2']}").json()["current"] is None
    assert owner_book(client, tokens["A-2"], s[2]).status_code == 200

    # 管理端取消
    booking_id = next(x for x in client.get(f"/batches/{b}/invites", headers=ADMIN).json() if x["unit_no"] == "A-3")["booking"]["id"]
    assert client.post(f"/bookings/{booking_id}/cancel", headers=ADMIN).status_code == 204
    assert client.get(f"/api/public/book/{tokens['A-3']}").json()["current"] is None


def test_staff_copy_of_owner_actions(client, setup, monkeypatch):
    """屋主預約／改期／取消時另寄副本給內部人員；屋主那封信看不到內部收件人；管理端取消不寄副本"""
    monkeypatch.setattr(settings, "booking_notify_to", "staff@example.com")
    b, s = setup["batch"], setup["slots"]
    send(client, b)
    token = token_of(client, b, "A-1")

    for action, keyword in [
        (lambda: owner_book(client, token, s[0]), "預約確認"),
        (lambda: owner_book(client, token, s[1]), "改期"),
        (lambda: client.post(f"/api/public/book/{token}/cancel"), "取消"),
    ]:
        before = outbox()
        assert action().status_code in (200, 204)
        owner_mail, staff_mail = sorted(mails_since(before), key=lambda m: m["To"] != "owner@example.com")
        assert owner_mail["To"] == "owner@example.com" and "staff@example.com" not in str(owner_mail)
        assert staff_mail["To"] == "staff@example.com" and staff_mail["Subject"].startswith("【副本】")
        assert keyword in staff_mail["Subject"] and "owner@example.com" in staff_mail.get_content()

    assert owner_book(client, token, s[0]).status_code == 200
    booking_id = next(x for x in client.get(f"/batches/{b}/invites", headers=ADMIN).json() if x["unit_no"] == "A-1")["booking"]["id"]
    before = outbox()
    assert client.post(f"/bookings/{booking_id}/cancel", headers=ADMIN).status_code == 204
    assert [m["To"] for m in mails_since(before)] == ["owner@example.com"]

    monkeypatch.setattr(settings, "booking_notify_to", "none")
    before = outbox()
    assert owner_book(client, token, s[2]).status_code == 200
    assert [m["To"] for m in mails_since(before)] == ["owner@example.com"]


def test_closed_slot_and_booking_window(client, setup):
    b, s = setup["batch"], setup["slots"]
    send(client, b)
    token = token_of(client, b, "A-1")

    client.patch(f"/slots/{s[0]}", headers=ADMIN, json={"is_open": False})
    assert all(x["id"] != s[0] for d in client.get(f"/api/public/book/{token}").json()["days"] for x in d["slots"])
    assert owner_book(client, token, s[0]).status_code == 409

    past = datetime.now() - timedelta(hours=1)
    r = client.patch(f"/batches/{b}/settings", headers=ADMIN, json={"booking_close_at": past.isoformat(), "description": "請攜帶交屋文件"})
    assert r.status_code == 200 and r.json()["description"] == "請攜帶交屋文件"
    info = client.get(f"/api/public/book/{token}").json()
    assert "截止" in info["closed_reason"] and info["description"] == "請攜帶交屋文件"
    assert owner_book(client, token, s[1]).status_code == 409

    future = datetime.now() + timedelta(days=3)
    client.patch(f"/batches/{b}/settings", headers=ADMIN, json={"booking_open_at": future.isoformat(), "booking_close_at": None})
    assert "開放" in client.get(f"/api/public/book/{token}").json()["closed_reason"]
    bad = client.patch(f"/batches/{b}/settings", headers=ADMIN, json={"booking_open_at": future.isoformat(), "booking_close_at": past.isoformat()})
    assert bad.status_code == 422


def test_past_slots_hidden(client, setup):
    with SessionLocal() as db:  # 把第一個時段改到昨天
        slot = db.get(TimeSlot, setup["slots"][0])
        slot.slot_date = date.today() - timedelta(days=1)
        db.commit()
    send(client, setup["batch"])
    token = token_of(client, setup["batch"], "A-1")
    ids = [x["id"] for d in client.get(f"/api/public/book/{token}").json()["days"] for x in d["slots"]]
    assert setup["slots"][0] not in ids
    r = owner_book(client, token, setup["slots"][0])
    assert r.status_code == 409 and "已經開始" in r.json()["detail"]


def test_last_spot_race_never_overbooks(client, setup):
    """多人同時搶同一時段：名額 3，6 個執行緒同時預約，只能成功 3 個"""
    pid, b, slot_id = setup["pid"], setup["batch"], setup["slots"][3]
    unit_ids = [
        client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": f"R-{i}", "owner_email": f"r{i}@example.com"}).json()["id"]
        for i in range(6)
    ]
    send(client, b)
    with SessionLocal() as db:
        invite_ids = [db.query(UnitInvite).filter_by(batch_id=b, unit_id=u).one().id for u in unit_ids]

    results: list[str] = []
    barrier = threading.Barrier(len(invite_ids))

    def attempt(invite_id: int):
        with SessionLocal() as db:
            invite = db.get(UnitInvite, invite_id)
            barrier.wait()
            try:
                book(db, invite, slot_id, {"contact_name": "x", "contact_phone": "0912000000", "contact_email": "x@example.com"})
                db.commit()
                results.append("ok")
            except Exception as e:  # noqa: BLE001
                db.rollback()
                results.append(type(e).__name__)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in invite_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 3, results
    assert client.get(f"/batches/{b}", headers=ADMIN).json()["days"][1]["slots"][1]["booked"] == 3


def test_public_server_exposes_only_booking(client, setup):
    from app.public_main import app as public_app

    send(client, setup["batch"])
    token = token_of(client, setup["batch"], "A-1")
    with TestClient(public_app) as pc:
        assert pc.get(f"/book/{token}").status_code == 200
        assert pc.get(f"/api/public/book/{token}").status_code == 200
        assert pc.get(f"/batches/{setup['batch']}/invites", headers=ADMIN).status_code == 404
        assert pc.post(f"/batches/{setup['batch']}/invites/send", headers=ADMIN, json={}).status_code == 404
    assert client.get("/api/public/book/not-a-token").status_code == 404
