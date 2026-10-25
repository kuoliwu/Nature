"""四階段：建立系統 → 預約參觀（報到）→ 預約驗屋 → 預約健檢（驗屋、健檢各一份清單）"""

from datetime import date, time, timedelta

import pytest

from app.database import SessionLocal
from app.models import Booking, BookingBatch, InspectionCategory, Project, ServiceType, Unit
from app.seed import migrate_checklist_services
from app.services.slots import generate_slots
from tests.conftest import ADMIN

TOMORROW = date.today() + timedelta(days=1)


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def project(client, name="四階段建案") -> int:
    return client.post("/projects", headers=ADMIN, json={"name": name}).json()["id"]


def booking(client, pid: int, service: str, unit_no: str, days: int = 1) -> int:
    with SessionLocal() as db:
        unit = Unit(project_id=pid, unit_no=unit_no, owner_email=f"{unit_no}@example.com")
        batch = BookingBatch(project_id=pid, name=service, service_type=ServiceType(service))
        db.add_all([unit, batch])
        db.flush()
        slot = generate_slots(db, batch, date.today() + timedelta(days=days), time(10), time(10, 30))[0]
        b = Booking(batch_id=batch.id, slot_id=slot.id, unit_id=unit.id, contact_name="屋主", contact_phone="0900")
        db.add(b)
        db.commit()
        return b.id


def names(categories) -> dict:
    return {c["name"]: [i["name"] for i in c["items"]] for c in categories}


def test_separate_checklists_for_inspection_and_health(client):
    pid = project(client)
    ins = client.get(f"/projects/{pid}/checklist", headers=ADMIN, params={"service": "inspection"}).json()
    health = client.get(f"/projects/{pid}/checklist", headers=ADMIN, params={"service": "health_check"}).json()
    assert names(ins) == names(health) and {c["id"] for c in ins}.isdisjoint({c["id"] for c in health})

    client.post(f"/checklist/categories/{health[0]['id']}/items", headers=ADMIN, json={"name": "一年後滲水"})
    client.post(f"/projects/{pid}/checklist/categories", headers=ADMIN, params={"service": "health_check"}, json={"name": "外牆"})
    ins2 = names(client.get(f"/projects/{pid}/checklist", headers=ADMIN, params={"service": "inspection"}).json())
    health2 = names(client.get(f"/projects/{pid}/checklist", headers=ADMIN, params={"service": "health_check"}).json())
    assert "一年後滲水" in health2["窗戶"] and "外牆" in health2
    assert "一年後滲水" not in ins2["窗戶"] and "外牆" not in ins2
    assert client.get(f"/projects/{pid}/checklist", headers=ADMIN, params={"service": "visit"}).status_code == 422


def test_inspection_uses_checklist_of_its_service(client):
    pid = project(client)
    client.post(f"/projects/{pid}/checklist/categories", headers=ADMIN, params={"service": "health_check"}, json={"name": "外牆"})
    health_cat = next(c for c in client.get(f"/projects/{pid}/checklist", headers=ADMIN, params={"service": "health_check"}).json() if c["name"] == "外牆")
    client.post(f"/checklist/categories/{health_cat['id']}/items", headers=ADMIN, json={"name": "磁磚", "check_points": ["空心"]})

    hb = booking(client, pid, "health_check", "H-1")
    ib = booking(client, pid, "inspection", "I-1")
    assert "外牆" in [c["name"] for c in client.get(f"/inspections/{hb}", headers=ADMIN).json()["categories"]]
    ins = client.get(f"/inspections/{ib}", headers=ADMIN).json()
    assert "外牆" not in [c["name"] for c in ins["categories"]] and ins["service_type"] == "inspection"

    # 健檢預約不能填驗屋清單的檢查點
    inspection_point = ins["categories"][0]["items"][0]["points"][0]["id"]
    assert client.put(f"/inspections/{hb}/results/{inspection_point}", headers=ADMIN, json={"result": "pass"}).status_code == 404


def test_visit_check_in(client):
    pid = project(client)
    vid = booking(client, pid, "visit", "V-1")
    batches = client.get(f"/projects/{pid}/batches", headers=ADMIN, params={"service": "visit"}).json()
    assert [b["service_type"] for b in batches] == ["visit"]
    assert client.get(f"/projects/{pid}/batches", headers=ADMIN, params={"service": "inspection"}).json() == []

    v = client.get(f"/inspections/{vid}", headers=ADMIN).json()
    assert (v["service_type"], v["status"], v["categories"], v["total"]) == ("visit", "not_started", [], 0)
    assert client.patch(f"/inspections/{vid}", headers=ADMIN, json={"general_note": "x"}).status_code == 409

    row = next(r for r in client.get("/inspections/schedule", headers=ADMIN, params={"day": str(TOMORROW)}).json() if r["booking_id"] == vid)
    assert (row["service_type"], row["status"]) == ("visit", "not_started")

    v = client.post(f"/bookings/{vid}/checkin", headers=ADMIN).json()
    assert v["status"] == "checked_in" and v["checked_in_at"]
    with SessionLocal() as db:
        assert db.get(Booking, vid).status.value == "completed"
    assert client.post(f"/bookings/{vid}/checkin/undo", headers=ADMIN).json()["status"] == "not_started"

    ib = booking(client, pid, "inspection", "I-2")
    assert client.post(f"/bookings/{ib}/checkin", headers=ADMIN).status_code == 409


def test_visits_not_in_report_reminders(client):
    pid = project(client, "提醒排除參觀")
    booking(client, pid, "visit", "V-old", days=-10)
    booking(client, pid, "inspection", "I-old", days=-10)
    units = [r["unit_no"] for r in client.get("/reports/overdue", headers=ADMIN).json()]
    assert "I-old" in units and "V-old" not in units


def test_visit_batch_and_invite_wording(client):
    pid = project(client, "參觀建案")
    client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "P-1", "owner_email": "p1@example.com"})
    b = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "預約參觀", "service_type": "visit", "start_date": str(TOMORROW), "end_date": str(TOMORROW),
        "day_start": "10:00", "day_end": "11:00",
    })
    assert b.status_code == 201 and b.json()["service_type"] == "visit"
    client.post(f"/batches/{b.json()['id']}/invites/send", headers=ADMIN, json={})
    token = client.get(f"/batches/{b.json()['id']}/invites", headers=ADMIN).json()[0]["link"].rsplit("/", 1)[1]
    assert client.get(f"/api/public/book/{token}").json()["service_label"] == "參觀"


def test_legacy_checklist_migrated_to_inspection(client):
    with SessionLocal() as db:
        p = Project(name="舊清單建案")
        db.add(p)
        db.flush()
        db.add(InspectionCategory(code=f"legacy-{p.id}", name="舊類別", project_id=p.id))
        db.commit()
        pid = p.id
        assert migrate_checklist_services(db) >= 1
        assert db.query(InspectionCategory).filter_by(code=f"legacy-{pid}").one().service_type == "inspection"
