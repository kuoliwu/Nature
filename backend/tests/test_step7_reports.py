"""M5：外部報告上傳、7 / 14 天未完成提醒、備份"""

from datetime import date, datetime, timedelta
from email import message_from_bytes, policy

import pytest

from app.config import settings
from app.database import SessionLocal
from app.models import Booking, BookingBatch, Project, ServiceType, Unit
from app.services.backup import run_backup
from app.services.reports import run_reminders
from app.services.slots import generate_slots
from tests.conftest import ADMIN

PDF = b"%PDF-1.4\n% test report\n%%EOF\n"


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def make_booking(days_ago: int, unit_no: str) -> int:
    with SessionLocal() as db:
        project = db.query(Project).filter_by(name="報告追蹤建案").first()
        if project is None:
            project = Project(name="報告追蹤建案")
            db.add(project)
            db.flush()
        unit = Unit(project_id=project.id, unit_no=unit_no)
        batch = BookingBatch(project_id=project.id, name=f"批次{unit_no}", service_type=ServiceType.HEALTH_CHECK)
        db.add_all([unit, batch])
        db.flush()
        slot = generate_slots(db, batch, date.today() - timedelta(days=days_ago), datetime(2000, 1, 1, 9).time(), datetime(2000, 1, 1, 9, 30).time())[0]
        b = Booking(batch_id=batch.id, slot_id=slot.id, unit_id=unit.id, contact_name="屋主", contact_phone="0900", contact_email="o@example.com")
        db.add(b)
        db.commit()
        return b.id


def upload(client, bid, data=PDF, name="外部報告.pdf"):
    return client.post(f"/bookings/{bid}/report", headers=ADMIN, files={"file": (name, data, "application/pdf")})


def outbox() -> set:
    return set((settings.storage_dir / "outbox").glob("*.eml"))


def test_external_report_upload_and_switch(client):
    bid = make_booking(1, "U-1")
    assert upload(client, bid, b"not a pdf").status_code == 422
    assert upload(client, bid, b"%PDF" + b"0" * (30 * 1024 * 1024)).status_code == 413

    r = upload(client, bid)
    assert r.status_code == 201 and r.json()["filename"] == "外部報告.pdf" and r.json()["size"] == len(PDF)
    pdf = client.get("/" + r.json()["url"].split("://", 1)[1].split("/", 1)[1])
    assert pdf.content == PDF

    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    assert ins["external_report"]["filename"] == "外部報告.pdf" and ins["upload_enabled"] is False
    second = upload(client, bid)
    assert second.status_code == 409 and "上傳開關" in second.json()["detail"]  # 自動關閉，避免重複上傳

    with SessionLocal() as db:
        unit_id = db.get(Booking, bid).unit_id
    assert client.patch(f"/units/{unit_id}/report-upload", headers=ADMIN, json={"enabled": True}).status_code == 204
    assert upload(client, bid, PDF + b"v2", "第二版.pdf").json()["filename"] == "第二版.pdf"  # 取代舊檔

    assert client.delete(f"/bookings/{bid}/report", headers=ADMIN).status_code == 204
    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    assert ins["external_report"] is None and ins["upload_enabled"] is True


def test_reminders_7_and_14_days(client):
    late7 = make_booking(8, "R-7")
    late14 = make_booking(15, "R-14")
    make_booking(3, "R-3")  # 還沒到 7 天
    done = make_booking(9, "R-done")
    upload(client, done)  # 已上傳外部報告 → 不提醒

    overdue = {r["unit_no"]: r for r in client.get("/reports/overdue", headers=ADMIN).json()}
    assert {"R-7", "R-14"} <= set(overdue) and "R-3" not in overdue and "R-done" not in overdue
    assert overdue["R-14"]["days"] == 15 and overdue["R-14"]["reminded"] == []

    before = outbox()
    r = client.post("/reminders/run", headers=ADMIN).json()
    assert "報告追蹤建案 R-7" in r["day7"] and "報告追蹤建案 R-14" in r["day14"]
    [mail] = [message_from_bytes(p.read_bytes(), policy=policy.default) for p in outbox() - before]
    body = mail.get_content()
    assert "報告提醒" in mail["Subject"] and "R-7" in body and "R-14" in body and "超過 14 天" in body

    # 同一階段不重複寄
    assert client.post("/reminders/run", headers=ADMIN).json()["sent"] == 0
    assert client.get("/reports/overdue", headers=ADMIN).json()
    reminded = {r["unit_no"]: r["reminded"] for r in client.get("/reports/overdue", headers=ADMIN).json()}
    assert reminded["R-7"] == [7] and reminded["R-14"] == [7, 14]

    # 7 天後：R-7 到第 15 天 → 寄 14 天提醒
    with SessionLocal() as db:
        result = run_reminders(db, date.today() + timedelta(days=7))
    assert "報告追蹤建案 R-7" in result["day14"]
    assert late7 and late14


def test_send_report_attaches_external_pdf(client):
    from tests.test_step6_inspection import STROKES

    bid = make_booking(0, "S-1")
    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    for p in [p for c in ins["categories"] for i in c["items"] for p in i["points"]]:
        client.put(f"/inspections/{bid}/results/{p['id']}", headers=ADMIN, json={"result": "pass"})
    client.post(f"/inspections/{bid}/sign", headers=ADMIN, json={"signer_name": "x", "strokes": STROKES, "width": 300, "height": 150})
    client.post(f"/inspections/{bid}/approve", headers=ADMIN)
    upload(client, bid)
    before = outbox()
    client.post(f"/inspections/{bid}/send", headers=ADMIN, json={})
    [mail] = [message_from_bytes(p.read_bytes(), policy=policy.default) for p in outbox() - before]
    names = [a.get_filename() for a in mail.iter_attachments()]
    assert len(names) == 2 and "外部報告.pdf" in names


def test_backup(client):
    result = run_backup()
    assert result["database"] and result["database"].endswith(".db")
    import sqlite3

    with sqlite3.connect(result["database"]) as conn:
        assert conn.execute("select count(*) from projects").fetchone()[0] > 0  # 備份內容完整
    assert result["files_copied"] > 0
    assert run_backup()["files_copied"] == 0  # 第二次只複製變更的檔案
    assert client.post("/backup/run", headers=ADMIN).status_code == 200
