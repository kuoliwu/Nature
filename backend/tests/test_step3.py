import base64
import io
import re
from datetime import date, datetime, time, timedelta
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pypdf import PdfReader
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import AccessLink, Authorization, Booking, BookingBatch, Project, ServiceType, Unit
from app.services.security import hash_id_number
from app.services.slots import generate_slots
from tests.conftest import ADMIN


def signature_data_url(blank: bool = False, variant: int = 0) -> str:
    img = Image.new("RGB", (400, 150), "white")
    if not blank:
        ImageDraw.Draw(img).line([(20, 100), (120, 30 + variant * 20), (220, 110), (380, 40)], fill="black", width=5)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def make_booking(id_number: str | None = None) -> int:
    with SessionLocal() as db:
        project = Project(name="授權測試建案")
        db.add(project)
        db.flush()
        unit = Unit(
            project_id=project.id, unit_no=f"B-{datetime.now():%H%M%S%f}", address="新北市板橋區測試路 8 號",
            owner_id_hash=hash_id_number(id_number) if id_number else None,
        )
        batch = BookingBatch(project_id=project.id, name="驗屋", service_type=ServiceType.INSPECTION)
        db.add_all([unit, batch])
        db.flush()
        slot = generate_slots(db, batch, date(2026, 12, 1), time(14, 0), time(14, 30))[0]
        booking = Booking(batch_id=batch.id, slot_id=slot.id, unit_id=unit.id, contact_name="屋主", contact_phone="0900")
        db.add(booking)
        db.commit()
        return booking.id


def outbox_files() -> set:
    return set((settings.storage_dir / "outbox").glob("*.eml"))


def new_emails(before: set) -> list:
    return [message_from_bytes(p.read_bytes(), policy=policy.default) for p in sorted(outbox_files() - before)]


def owner_payload(**overrides) -> dict:
    return {
        "owner_name": "王小明",
        "owner_email": "owner@example.com",
        "trustee_name": "陳大文",
        "trustee_email": "trustee@example.com",
        "owner_signature": signature_data_url(),
        **overrides,
    }


@pytest.fixture(autouse=True)
def _db(client, admin_token):
    pass


def owner_link(client, booking_id: int) -> dict:
    r = client.post(f"/bookings/{booking_id}/authorization-link", headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def owner_sign(client, token: str, **overrides):
    return client.post(f"/api/public/authorize/{token}", json=owner_payload(**overrides))


def test_full_signing_flow(client):
    booking_id = make_booking()
    link = owner_link(client, booking_id)
    assert link["public_url"] is None  # 未啟動通道
    assert link["lan_url"].endswith(f"/authorize/{link['token']}")
    assert owner_link(client, booking_id)["token"] == link["token"]  # 重複產生沿用同一個連結
    owner_token = link["token"]

    page = client.get(f"/authorize/{owner_token}")
    assert page.status_code == 200 and "__CONFIG__" not in page.text

    summary = client.get(f"/api/public/authorize/{owner_token}").json()
    assert summary["inspection_date"] == "2026-12-01 14:00-14:30"
    assert summary["require_id_verification"] is False

    # 1. 屋主簽名 → 寄出邀請
    before = outbox_files()
    r = owner_sign(client, owner_token)
    assert r.status_code == 201, r.text
    auth = r.json()
    assert auth["status"] == "pending_trustee"

    [invite] = new_emails(before)
    assert invite["To"] == "trustee@example.com"
    token = re.search(r"/sign/([\w-]+)", invite.get_content()).group(1)

    # 2. 受託人開啟連結並簽名
    info = client.get(f"/api/public/sign/{token}").json()
    assert (info["owner_name"], info["trustee_name"]) == ("王小明", "陳大文")

    before = outbox_files()
    r = client.post(f"/api/public/sign/{token}", json={"trustee_signature": signature_data_url(variant=1)})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed" and r.json()["has_pdf"] is True

    # 3. PDF 內容：文字欄位 + 兩張簽名圖
    pdf = client.get(f"/authorizations/{auth['id']}/pdf", headers=ADMIN)
    assert pdf.headers["content-type"] == "application/pdf"
    page = PdfReader(io.BytesIO(pdf.content)).pages[0]
    text = page.extract_text()
    for expected in ["驗屋代理授權書", "授權測試建案", "王小明", "陳大文", "2026-12-01 14:00-14:30", f"AUTH-{auth['id']:06d}"]:
        assert expected in text, expected
    assert len(page.images) == 2

    # 4. 完成通知附上 PDF，寄給雙方
    [done] = new_emails(before)
    assert set(done["To"].addresses[i].addr_spec for i in range(2)) == {"owner@example.com", "trustee@example.com"}
    [attachment] = list(done.iter_attachments())
    assert attachment.get_filename().endswith(".pdf")
    assert attachment.get_content() == pdf.content

    # 連結不能重複使用
    assert client.post(f"/api/public/sign/{token}", json={"trustee_signature": signature_data_url()}).status_code == 409


def test_id_verification(client):
    token = owner_link(client, make_booking(id_number="A123456789"))["token"]
    assert client.get(f"/api/public/authorize/{token}").json()["require_id_verification"] is True

    assert owner_sign(client, token, owner_id_number="B987654321").status_code == 403
    r = owner_sign(client, token, owner_id_number=" a123456789 ")
    assert r.status_code == 201


def test_expired_invite_and_resend(client):
    booking_id = make_booking()
    auth_id = owner_sign(client, owner_link(client, booking_id)["token"]).json()["id"]

    with SessionLocal() as db:
        auth = db.get(Authorization, auth_id)
        auth.invite_expires_at = datetime.now() - timedelta(minutes=1)
        old_token = auth.invite_token
        db.commit()

    assert client.get(f"/api/public/sign/{old_token}").status_code == 410
    listed = client.get("/authorizations", headers=ADMIN, params={"booking_id": booking_id}).json()
    assert listed[0]["status"] == "expired"

    before = outbox_files()
    assert client.post(f"/authorizations/{auth_id}/resend-invite", headers=ADMIN).status_code == 200
    [invite] = new_emails(before)
    new_token = re.search(r"/sign/([\w-]+)", invite.get_content()).group(1)
    assert new_token != old_token
    assert client.get(f"/api/public/sign/{new_token}").status_code == 200
    assert client.get(f"/api/public/sign/{old_token}").status_code == 404


@pytest.mark.parametrize(
    "signature, message",
    [(signature_data_url(blank=True), "空白"), ("not-base64!!", "Base64"), ("data:text/html;base64,PGh0bWw+", "PNG")],
)
def test_invalid_signature(client, signature, message):
    r = owner_sign(client, owner_link(client, make_booking())["token"], owner_signature=signature)
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_sign_page_escapes_token(client):
    html = client.get("/sign/%3C%2Fscript%3E%3Cscript%3Ealert(1)").text
    assert "</script><script>alert(1)" not in html


def test_owner_link_rules(client):
    assert client.get("/api/public/authorize/not-a-real-token").status_code == 404
    assert client.post("/bookings/999999/authorization-link", headers=ADMIN).status_code == 404

    token = owner_link(client, make_booking())["token"]
    with SessionLocal() as db:
        link = db.scalar(select(AccessLink).where(AccessLink.token == token))
        link.expires_at = datetime.now() - timedelta(seconds=1)
        db.commit()
    assert client.get(f"/api/public/authorize/{token}").status_code == 410
    assert owner_sign(client, token).status_code == 410


def test_public_link_uses_tunnel_url(client):
    settings.public_url_file.write_text("https://demo-tunnel.trycloudflare.com\n")
    try:
        booking_id = make_booking()
        link = owner_link(client, booking_id)
        assert link["public_url"] == f"https://demo-tunnel.trycloudflare.com/authorize/{link['token']}"

        before = outbox_files()
        owner_sign(client, link["token"])
        [invite] = new_emails(before)
        assert "https://demo-tunnel.trycloudflare.com/sign/" in invite.get_content()
    finally:
        settings.public_url_file.unlink()


def test_public_server_has_no_admin_api():
    from app.public_main import app as public_app

    with TestClient(public_app) as pc:
        for method, path in [
            ("post", "/init-db"), ("get", "/db/status"), ("get", "/health"), ("get", "/projects"),
            ("get", "/authorizations"), ("get", "/authorizations/1/pdf"),
            ("post", "/bookings/1/authorization-link"), ("get", "/docs"), ("get", "/openapi.json"),
        ]:
            assert getattr(pc, method)(path, headers=ADMIN).status_code in (404, 405), path
        assert pc.get("/authorize/abc").status_code == 200
        assert pc.get("/sign/abc").status_code == 200


def test_owner_resubmit_latest_wins(client):
    booking_id = make_booking()
    token = owner_link(client, booking_id)["token"]
    invite_token = lambda mail: re.search(r"/sign/([\w-]+)", mail.get_content()).group(1)

    # 第一次：受託人 A
    before = outbox_files()
    first = owner_sign(client, token, trustee_email="a@example.com").json()
    [invite_a] = new_emails(before)

    # 第二次：改成受託人 B → 以最後一次為準
    before = outbox_files()
    second = owner_sign(client, token, trustee_name="林小華", trustee_email="b@example.com")
    assert second.status_code == 201
    mails = {m["To"]: m for m in new_emails(before)}
    assert set(mails) == {"a@example.com", "b@example.com"}
    assert "作廢" in mails["a@example.com"]["Subject"]  # 通知舊受託人

    old_link = client.get(f"/api/public/sign/{invite_token(invite_a)}")
    assert old_link.status_code == 410 and "更新" in old_link.json()["detail"]
    new_info = client.get(f"/api/public/sign/{invite_token(mails['b@example.com'])}").json()
    assert new_info["trustee_name"] == "林小華"

    listed = client.get("/authorizations", headers=ADMIN, params={"booking_id": booking_id}).json()
    assert [(a["id"], a["status"]) for a in listed] == [
        (second.json()["id"], "pending_trustee"),
        (first["id"], "cancelled"),
    ]

    # 已完成的授權書也可以被最新一次取代；同一位受託人不寄作廢通知，只寄新邀請
    client.post(f"/api/public/sign/{invite_token(mails['b@example.com'])}", json={"trustee_signature": signature_data_url(variant=2)})
    before = outbox_files()
    assert owner_sign(client, token, trustee_name="林小華", trustee_email="B@example.com").status_code == 201
    [only_invite] = new_emails(before)
    assert "簽署邀請" in only_invite["Subject"]
    statuses = [a["status"] for a in client.get("/authorizations", headers=ADMIN, params={"booking_id": booking_id}).json()]
    assert statuses == ["pending_trustee", "cancelled", "cancelled"]
