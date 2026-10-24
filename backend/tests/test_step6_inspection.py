"""M4 第三階段：驗屋（填寫結果、拍照、屋主簽名）"""

import io
from datetime import date, timedelta

import pytest
from PIL import Image

from tests.conftest import ADMIN

TOMORROW = date.today() + timedelta(days=1)
STROKES = [[[10, 50], [60, 20], [120, 80], [200, 30]], [[40, 100], [180, 100]]]


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


@pytest.fixture
def booking(client) -> dict:
    """建案（帶入範本 19 個檢查點）+ 一戶 + 明天一個預約"""
    pid = client.post("/projects", headers=ADMIN, json={"name": "驗屋測試建案", "address": "台中市驗屋路 9 號"}).json()["id"]
    uid = client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "C-3F-1", "owner_email": "c@example.com"}).json()["id"]
    batch = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "驗屋", "start_date": str(TOMORROW), "end_date": str(TOMORROW), "day_start": "10:00", "day_end": "11:00",
    }).json()
    client.post(f"/batches/{batch['id']}/invites/send", headers=ADMIN, json={})
    token = client.get(f"/batches/{batch['id']}/invites", headers=ADMIN).json()[0]["link"].rsplit("/", 1)[1]
    client.post(f"/api/public/book/{token}", json={
        "slot_id": batch["days"][0]["slots"][0]["id"], "contact_name": "陳屋主", "contact_phone": "0933000111", "contact_email": "c@example.com",
    })
    bid = client.get(f"/batches/{batch['id']}/invites", headers=ADMIN).json()[0]["booking"]["id"]
    return {"pid": pid, "booking_id": bid, "token": token, "slot_id": batch["days"][0]["slots"][1]["id"]}


def points(inspection: dict) -> list[dict]:
    return [p for c in inspection["categories"] for i in c["items"] for p in i["points"]]


def jpeg(w=3000, h=2000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 120, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def fill_all(client, bid, result="pass"):
    for p in points(client.get(f"/inspections/{bid}", headers=ADMIN).json()):
        client.put(f"/inspections/{bid}/results/{p['id']}", headers=ADMIN, json={"result": result})


def test_schedule_lists_bookings_of_the_day(client, booking):
    rows = client.get("/inspections/schedule", headers=ADMIN, params={"day": str(TOMORROW)}).json()
    row = next(r for r in rows if r["booking_id"] == booking["booking_id"])
    assert (row["unit_no"], row["contact_name"], row["status"], row["checked"], row["total"]) == ("C-3F-1", "陳屋主", "not_started", 0, 19)
    assert row["place"] == "台中市驗屋路 9 號" and row["start_time"] == "10:00:00"
    assert client.get("/inspections/schedule", headers=ADMIN, params={"day": str(TOMORROW + timedelta(days=5))}).json() == []


def test_fill_results_and_notes(client, booking):
    bid = booking["booking_id"]
    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    assert [c["name"] for c in ins["categories"]] == ["窗戶", "水電", "其他"] and ins["status"] == "not_started"
    first, second = points(ins)[:2]

    r = client.put(f"/inspections/{bid}/results/{first['id']}", headers=ADMIN, json={"result": "fail", "note": "膠條脫落"})
    assert (r.json()["result"], r.json()["note"]) == ("fail", "膠條脫落")
    client.put(f"/inspections/{bid}/results/{second['id']}", headers=ADMIN, json={"result": "na"})
    client.put(f"/inspections/{bid}/results/{first['id']}", headers=ADMIN, json={"note": "膠條脫落，需更換"})  # 只改備註

    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    assert (ins["status"], ins["checked"], ins["total"], ins["fail_count"]) == ("in_progress", 2, 19, 1)
    assert points(ins)[0]["result"] == "fail" and points(ins)[0]["note"] == "膠條脫落，需更換"
    assert ins["inspector_name"] == "測試管理者"

    assert client.patch(f"/inspections/{bid}", headers=ADMIN, json={"general_note": "整體良好"}).json()["general_note"] == "整體良好"
    assert client.put(f"/inspections/{bid}/results/{first['id']}", headers=ADMIN, json={"result": "maybe"}).status_code == 422

    other = client.post("/projects", headers=ADMIN, json={"name": "別的建案"}).json()["id"]
    other_point = points_of_project(client, other)
    assert client.put(f"/inspections/{bid}/results/{other_point}", headers=ADMIN, json={"result": "pass"}).status_code == 404


def points_of_project(client, pid) -> int:
    return client.get(f"/projects/{pid}/checklist", headers=ADMIN).json()[0]["items"][0]["check_points"][0]["id"]


def test_photos(client, booking):
    bid = booking["booking_id"]
    point = points(client.get(f"/inspections/{bid}", headers=ADMIN).json())[0]
    r = client.post(f"/inspections/{bid}/photos", headers=ADMIN, data={"check_point_id": str(point["id"]), "caption": "左下角"},
                    files={"file": ("p.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 201, r.text
    photo = r.json()
    img = client.get("/" + photo["url"].split("://", 1)[1].split("/", 1)[1])  # 不需登入 header
    assert img.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(img.content)).size == (1600, 1067)  # 長邊縮到 1600

    general = client.post(f"/inspections/{bid}/photos", headers=ADMIN, files={"file": ("g.jpg", jpeg(800, 600), "image/jpeg")}).json()
    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    assert [p["caption"] for p in points(ins)[0]["photos"]] == ["左下角"]
    assert [p["id"] for p in ins["general_photos"]] == [general["id"]]

    bad = client.post(f"/inspections/{bid}/photos", headers=ADMIN, files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert bad.status_code == 422
    assert client.delete(f"/inspection-photos/{general['id']}", headers=ADMIN).status_code == 204
    assert client.get(f"/inspections/{bid}", headers=ADMIN).json()["general_photos"] == []


def test_sign_locks_and_reopen(client, booking):
    bid = booking["booking_id"]
    sign_body = {"signer_name": "陳屋主", "strokes": STROKES, "width": 300, "height": 150}
    r = client.post(f"/inspections/{bid}/sign", headers=ADMIN, json=sign_body)
    assert r.status_code == 409 and "未填寫" in r.json()["detail"]

    fill_all(client, bid)
    assert client.post(f"/inspections/{bid}/sign", headers=ADMIN, json={**sign_body, "strokes": [[]]}).status_code == 422
    ins = client.post(f"/inspections/{bid}/sign", headers=ADMIN, json=sign_body).json()
    assert (ins["status"], ins["signer_name"], ins["checked"]) == ("signed", "陳屋主", 19)
    sig = client.get("/" + ins["signature_url"].split("://", 1)[1].split("/", 1)[1])
    assert sig.headers["content-type"] == "image/png" and Image.open(io.BytesIO(sig.content)).mode == "RGBA"

    # 鎖定：不能再改結果或加照片
    p = points(ins)[0]
    assert client.put(f"/inspections/{bid}/results/{p['id']}", headers=ADMIN, json={"result": "fail"}).status_code == 409
    assert client.post(f"/inspections/{bid}/photos", headers=ADMIN, files={"file": ("p.jpg", jpeg(10, 10), "image/jpeg")}).status_code == 409

    # 屋主的預約頁：已完成，不能改期或取消
    info = client.get(f"/api/public/book/{booking['token']}").json()
    assert info["current"]["can_change"] is False
    assert client.post(f"/api/public/book/{booking['token']}", json={
        "slot_id": booking["slot_id"], "contact_name": "x", "contact_phone": "0900000000", "contact_email": "x@example.com",
    }).status_code == 409
    assert client.post(f"/api/public/book/{booking['token']}/cancel").status_code == 409
    rows = client.get("/inspections/schedule", headers=ADMIN, params={"day": str(TOMORROW)}).json()
    assert next(r for r in rows if r["booking_id"] == bid)["status"] == "signed"

    # 重新開啟：清除簽名、可再修改
    ins = client.post(f"/inspections/{bid}/reopen", headers=ADMIN).json()
    assert (ins["status"], ins["signer_name"], ins["signature_url"]) == ("in_progress", None, None)
    assert client.put(f"/inspections/{bid}/results/{p['id']}", headers=ADMIN, json={"result": "fail"}).status_code == 200


def test_disabled_point_kept_only_when_it_has_result(client, booking):
    bid, pid = booking["booking_id"], booking["pid"]
    pts = points(client.get(f"/inspections/{bid}", headers=ADMIN).json())
    used, unused = pts[0], pts[1]
    client.put(f"/inspections/{bid}/results/{used['id']}", headers=ADMIN, json={"result": "fail"})
    for p in (used, unused):
        client.patch(f"/checklist/points/{p['id']}", headers=ADMIN, json={"is_active": False})
    ids = [p["id"] for p in points(client.get(f"/inspections/{bid}", headers=ADMIN).json())]
    assert used["id"] in ids and unused["id"] not in ids
    assert client.get(f"/inspections/{bid}", headers=ADMIN).json()["total"] == 18


def test_permissions(client, booking):
    bid = booking["booking_id"]
    for phone, perms in [("0977000001", ["booking.view"]), ("0977000002", [])]:
        client.post("/users", headers=ADMIN, json={"name": phone, "phone": phone, "password": "password-9", "permissions": perms})
    view = {"Authorization": "Bearer " + client.post("/auth/login", json={"phone": "0977000001", "password": "password-9"}).json()["access_token"]}
    none = {"Authorization": "Bearer " + client.post("/auth/login", json={"phone": "0977000002", "password": "password-9"}).json()["access_token"]}
    point = points(client.get(f"/inspections/{bid}", headers=ADMIN).json())[0]["id"]

    assert client.get(f"/inspections/{bid}", headers=view).status_code == 200
    assert client.put(f"/inspections/{bid}/results/{point}", headers=view, json={"result": "pass"}).status_code == 403
    assert client.get("/inspections/schedule", headers=none, params={"day": str(TOMORROW)}).status_code == 403


def test_review_and_send_report(client, booking):
    from email import message_from_bytes, policy

    from pypdf import PdfReader

    from app.config import settings

    bid = booking["booking_id"]
    assert client.post(f"/inspections/{bid}/report-link", headers=ADMIN).status_code == 409  # 簽名前不能產生
    assert client.post(f"/inspections/{bid}/approve", headers=ADMIN).status_code == 409

    fill_all(client, bid)
    first = points(client.get(f"/inspections/{bid}", headers=ADMIN).json())[0]
    client.put(f"/inspections/{bid}/results/{first['id']}", headers=ADMIN, json={"result": "fail", "note": "膠條脫落"})
    client.post(f"/inspections/{bid}/photos", headers=ADMIN, data={"check_point_id": str(first["id"])},
                files={"file": ("p.jpg", jpeg(1200, 900), "image/jpeg")})
    client.post(f"/inspections/{bid}/sign", headers=ADMIN, json={"signer_name": "陳屋主", "strokes": STROKES, "width": 300, "height": 150})

    # 預覽 PDF（不需登入 header）
    link = client.post(f"/inspections/{bid}/report-link", headers=ADMIN).json()
    assert link["filename"] == f"健檢報告_驗屋測試建案_C-3F-1_{TOMORROW:%Y%m%d}.pdf"
    pdf = client.get("/" + link["url"].split("://", 1)[1].split("/", 1)[1])
    assert pdf.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(pdf.content))
    text = "".join(page.extract_text() for page in reader.pages)
    for expected in ["健檢報告", "驗屋測試建案", "C-3F-1", "不合格項目（1）", "膠條脫落", "陳屋主", "完整檢查結果", "照片紀錄"]:
        assert expected in text, expected
    assert sum(len(p.images) for p in reader.pages) >= 2  # 現場照片 + 簽名

    # Review OK → 取消確認 → 再確認
    ins = client.post(f"/inspections/{bid}/approve", headers=ADMIN).json()
    assert ins["status"] == "approved" and ins["approver_name"] == "測試管理者"
    assert client.post(f"/inspections/{bid}/reopen", headers=ADMIN).status_code == 409  # 已確認不能重開
    assert client.post(f"/inspections/{bid}/unapprove", headers=ADMIN).json()["status"] == "signed"
    assert client.post(f"/inspections/{bid}/send", headers=ADMIN, json={}).status_code == 409  # 未確認不能寄
    client.post(f"/inspections/{bid}/approve", headers=ADMIN)

    # 寄送：附 PDF + 感謝信
    outbox = settings.storage_dir / "outbox"
    before = set(outbox.glob("*.eml"))
    ins = client.post(f"/inspections/{bid}/send", headers=ADMIN, json={}).json()
    assert (ins["status"], ins["sent_to"]) == ("sent", "c@example.com") and ins["sent_at"]
    [mail] = [message_from_bytes(p.read_bytes(), policy=policy.default) for p in set(outbox.glob("*.eml")) - before]
    assert "健檢報告" in mail["Subject"] and "感謝您撥冗協助完成" in mail.get_body(preferencelist=("plain",)).get_content()
    [att] = list(mail.iter_attachments())
    assert att.get_filename().endswith(".pdf") and att.get_content().startswith(b"%PDF")
    assert (settings.storage_dir / "reports").exists()

    # 重新寄送到指定信箱；已寄出不能取消確認
    assert client.post(f"/inspections/{bid}/send", headers=ADMIN, json={"to": "other@example.com"}).json()["sent_to"] == "other@example.com"
    assert client.post(f"/inspections/{bid}/unapprove", headers=ADMIN).status_code == 409
    rows = client.get("/inspections/schedule", headers=ADMIN, params={"day": str(TOMORROW)}).json()
    assert next(r for r in rows if r["booking_id"] == bid)["status"] == "sent"


def test_report_permission(client, booking):
    bid = booking["booking_id"]
    fill_all(client, bid)
    client.post(f"/inspections/{bid}/sign", headers=ADMIN, json={"signer_name": "x", "strokes": STROKES, "width": 300, "height": 150})
    client.post("/users", headers=ADMIN, json={"name": "驗屋員", "phone": "0977000009", "password": "password-9", "permissions": ["inspection.edit"]})
    h = {"Authorization": "Bearer " + client.post("/auth/login", json={"phone": "0977000009", "password": "password-9"}).json()["access_token"]}
    assert client.post(f"/inspections/{bid}/report-link", headers=h).status_code == 200  # 可預覽
    assert client.post(f"/inspections/{bid}/approve", headers=h).status_code == 403  # 不能確認
