"""售服七步驟：時間軸、屋主預約頁封面照片"""

import io
from datetime import date, datetime, time, timedelta

import pytest
from PIL import Image

from app.database import SessionLocal
from app.models import Booking, BookingBatch, Inspection, InspectionStatus, ServiceType, Unit
from app.services.slots import generate_slots
from tests.conftest import ADMIN

TODAY = date.today()


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def make_batch(db, pid: int, service: ServiceType, day: date) -> BookingBatch:
    batch = BookingBatch(project_id=pid, name=service.value, service_type=service)
    db.add(batch)
    db.flush()
    generate_slots(db, batch, day, time(10), time(11))
    return batch


def book(db, batch: BookingBatch, unit: Unit, *, checked_in=False, inspection: InspectionStatus | None = None) -> None:
    b = Booking(batch_id=batch.id, slot_id=batch.slots[0].id, unit_id=unit.id, contact_name="屋主", contact_phone="0900",
                checked_in_at=datetime.now() if checked_in else None)
    db.add(b)
    db.flush()
    if inspection:
        db.add(Inspection(booking_id=b.id, status=inspection))


def test_timeline_steps(client):
    pid = client.post("/projects", headers=ADMIN, json={"name": "時間軸建案"}).json()["id"]
    with SessionLocal() as db:
        units = [Unit(project_id=pid, unit_no=f"T-{i}") for i in range(4)]
        db.add_all(units)
        db.flush()
        # 參觀：日期已過，只有 1 戶報到 → 仍算完成（沒來的不再等）
        visit = make_batch(db, pid, ServiceType.VISIT, TODAY - timedelta(days=10))
        book(db, visit, units[0], checked_in=True)
        # 驗屋：日期還沒過，2 戶預約、1 戶已簽名
        ins = make_batch(db, pid, ServiceType.INSPECTION, TODAY + timedelta(days=3))
        book(db, ins, units[0], inspection=InspectionStatus.SIGNED)
        book(db, ins, units[1])
        db.commit()

    t = client.get(f"/projects/{pid}/timeline", headers=ADMIN).json()
    steps = {s["key"]: s for s in t["steps"]}
    assert [s["key"] for s in t["steps"]] == [
        "created", "visit", "inspection_booking", "inspection", "handbook", "health_check_booking", "health_check"]
    assert steps["created"]["status"] == "done"
    assert steps["visit"]["status"] == "done" and steps["visit"]["done"] == 1
    assert steps["inspection_booking"]["status"] == "active" and (steps["inspection_booking"]["done"], steps["inspection_booking"]["total"]) == (2, 4)
    assert steps["inspection"]["status"] == "active" and steps["inspection"]["done"] == 1
    assert steps["inspection"]["date_from"] == str(TODAY + timedelta(days=3))
    assert steps["health_check_booking"]["status"] == "todo" and steps["health_check"]["status"] == "todo"
    assert t["current"] == 2

    # 驗屋日期過了、預約的都完成 → 預約驗屋與驗屋都算完成，目前走到第 5 步
    with SessionLocal() as db:
        batch = db.query(BookingBatch).filter_by(project_id=pid, service_type=ServiceType.INSPECTION).one()
        for slot in batch.slots:
            slot.slot_date = TODAY - timedelta(days=1)
        for b in db.query(Booking).filter_by(batch_id=batch.id):
            if db.query(Inspection).filter_by(booking_id=b.id).first() is None:
                db.add(Inspection(booking_id=b.id, status=InspectionStatus.SENT))
        db.commit()
    t = client.get(f"/projects/{pid}/timeline", headers=ADMIN).json()
    assert [s["status"] for s in t["steps"]][:4] == ["done"] * 4 and t["current"] == 4

    # 全部建案（路徑不能被 /projects/{project_id} 吃掉）
    r = client.get("/projects/timeline", headers=ADMIN)
    assert r.status_code == 200 and any(x["project"]["id"] == pid for x in r.json())


def jpeg_bytes(color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2400, 1200), color).save(buf, format="PNG")
    return buf.getvalue()


def test_cover_photos(client):
    pid = client.post("/projects", headers=ADMIN, json={"name": "封面建案"}).json()["id"]
    p = client.post(f"/projects/{pid}/covers/inspection", headers=ADMIN, files={"file": ("a.png", jpeg_bytes(), "image/png")}).json()
    assert p["covers"]["inspection"] and p["covers"]["health_check"] is None
    img = client.get(p["covers"]["inspection"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(img.content)).size) == 1600

    assert client.post(f"/projects/{pid}/covers/inspection", headers=ADMIN, files={"file": ("x.png", b"nope", "image/png")}).status_code == 422
    assert client.post(f"/projects/{pid}/covers/other", headers=ADMIN, files={"file": ("a.png", jpeg_bytes(), "image/png")}).status_code == 422

    # 屋主預約頁：驗屋批次有封面（預售屋），健檢批次沒有
    unit_id = client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "C-1"}).json()["id"]
    tokens = {}
    for service in ("inspection", "health_check"):
        batch = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
            "name": service, "service_type": service, "start_date": str(TODAY + timedelta(days=1)),
            "end_date": str(TODAY + timedelta(days=1)), "day_start": "10:00", "day_end": "11:00",
        }).json()
        link = client.post(f"/batches/{batch['id']}/units/{unit_id}/invite-link", headers=ADMIN).json()["link"]
        tokens[service] = link.rsplit("/", 1)[1]
    info = client.get(f"/api/public/book/{tokens['inspection']}").json()
    assert info["cover_url"].startswith(f"/api/public/book/{tokens['inspection']}/cover?v=")
    assert client.get(info["cover_url"]).headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/public/book/{tokens['health_check']}").json()["cover_url"] is None
    assert client.get(f"/api/public/book/{tokens['health_check']}/cover").status_code == 404

    # 換照片：舊檔刪除、網址不同
    old_url = info["cover_url"]
    client.post(f"/projects/{pid}/covers/inspection", headers=ADMIN, files={"file": ("b.png", jpeg_bytes("blue"), "image/png")})
    assert client.get(f"/api/public/book/{tokens['inspection']}").json()["cover_url"] != old_url

    p = client.delete(f"/projects/{pid}/covers/inspection", headers=ADMIN).json()
    assert p["covers"]["inspection"] is None
    assert client.get(f"/api/public/book/{tokens['inspection']}").json()["cover_url"] is None
