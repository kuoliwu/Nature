"""售服七步驟：時間軸、屋主預約頁封面照片"""

import io
from datetime import date, datetime, time, timedelta

import pytest
from PIL import Image

from app.database import SessionLocal
from app.models import Booking, BookingBatch, BookingStatus, Inspection, InspectionStatus, ServiceType, Unit
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


def test_project_pins_are_per_user(client):
    """釘選只影響自己的建案列表：釘選的排最前面（最近釘選的在上）"""
    ids = [client.post("/projects", headers=ADMIN, json={"name": f"釘選測試{i}"}).json()["id"] for i in range(3)]
    first, middle, last = ids
    assert client.put(f"/projects/{first}/pin", headers=ADMIN).status_code == 204
    assert client.put(f"/projects/{middle}/pin", headers=ADMIN).status_code == 204
    assert client.put(f"/projects/{middle}/pin", headers=ADMIN).status_code == 204  # 重複釘選不會出錯
    rows = client.get("/projects", headers=ADMIN).json()
    assert [r["id"] for r in rows[:2]] == [middle, first] and rows[0]["pinned"] and rows[1]["pinned"]
    assert not next(r for r in rows if r["id"] == last)["pinned"]

    # 其他人員看不到我的釘選
    other = {"name": "釘選同事", "phone": "0955987001", "password": "pin-pass-123", "permissions": []}
    assert client.post("/users", headers=ADMIN, json=other).status_code == 201
    token = client.post("/auth/login", json={"phone": other["phone"], "password": other["password"]}).json()["access_token"]
    theirs = client.get("/projects", headers={"Authorization": f"Bearer {token}"}).json()
    assert not any(r["pinned"] for r in theirs)

    assert client.delete(f"/projects/{middle}/pin", headers=ADMIN).status_code == 204
    rows = client.get("/projects", headers=ADMIN).json()
    assert rows[0]["id"] == first and not next(r for r in rows if r["id"] == middle)["pinned"]
    assert client.put("/projects/999999/pin", headers=ADMIN).status_code == 404


def test_project_order_per_user_within_pin_groups(client):
    """長按拖曳排序：每人各自的順序；釘選的仍在最前面；沒排過的新建案排在群組最前面"""
    a, b, c = (client.post("/projects", headers=ADMIN, json={"name": f"排序測試{n}"}).json()["id"] for n in "ABC")
    ids = [r["id"] for r in client.get("/projects", headers=ADMIN).json()]
    # 把 A 拖到 C 前面、B 最後（其餘維持）
    rest = [i for i in ids if i not in (a, b, c)]
    assert client.put("/projects/order", headers=ADMIN, json={"project_ids": [a, c, *rest, b, 999999]}).status_code == 204
    rows = [r["id"] for r in client.get("/projects", headers=ADMIN).json() if not r["pinned"]]
    assert rows[:2] == [a, c] and rows[-1] == b

    # 新建案還沒排過 → 排在最前面
    d = client.post("/projects", headers=ADMIN, json={"name": "排序測試D"}).json()["id"]
    rows = [r["id"] for r in client.get("/projects", headers=ADMIN).json() if not r["pinned"]]
    assert rows[:3] == [d, a, c]

    # 釘選 B → 排在釘選群組最上面（換群組時清掉原本排的位置）
    client.put(f"/projects/{b}/pin", headers=ADMIN)
    assert client.get("/projects", headers=ADMIN).json()[0]["id"] == b
    client.delete(f"/projects/{b}/pin", headers=ADMIN)


def test_schedule_counts_two_weeks(client):
    """行程頁兩週日曆：每天的預約數"""
    with SessionLocal() as db:
        pid = client.post("/projects", headers=ADMIN, json={"name": "行程日曆建案"}).json()["id"]
        units = [Unit(project_id=pid, unit_no=f"S-{i}") for i in range(3)]
        db.add_all(units)
        db.flush()
        day1, day2 = TODAY + timedelta(days=2), TODAY + timedelta(days=5)
        b1 = make_batch(db, pid, ServiceType.VISIT, day1)
        b2 = make_batch(db, pid, ServiceType.INSPECTION, day2)
        book(db, b1, units[0])
        book(db, b1, units[1])
        book(db, b2, units[2])
        db.add(Booking(batch_id=b2.id, slot_id=b2.slots[0].id, unit_id=units[0].id, contact_name="取消", contact_phone="0",
                       status=BookingStatus.CANCELLED))  # 取消的不算
        db.commit()
    rows = client.get("/inspections/schedule/counts", headers=ADMIN, params={"start": str(TODAY), "days": 14}).json()
    assert len(rows) == 14 and rows[0]["date"] == str(TODAY)
    counts = {r["date"]: r["count"] for r in rows}
    assert counts[str(day1)] >= 2 and counts[str(day2)] >= 1
    assert client.get("/inspections/schedule/counts", headers=ADMIN, params={"start": str(TODAY), "days": 100}).status_code == 422
