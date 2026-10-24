from datetime import date, time

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import (
    BatchService,
    Booking,
    BookingBatch,
    BookingStatus,
    QuotaMode,
    ServiceType,
    Unit,
)
from app.services.slots import generate_slots, remaining_capacity
from tests.conftest import ADMIN

REQUIRED_TABLES = {
    "projects", "units", "bookings", "time_slots", "booking_batches",
    "inspection_items", "inspection_check_points", "authorizations", "reports",
}


def test_health_before_init(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["db_initialized"] is False


def test_init_db_requires_key(client):
    assert client.post("/init-db").status_code == 422
    assert client.post("/init-db", headers={"X-Admin-Key": "wrong"}).status_code == 403


def test_init_db_creates_schema_and_seeds(client):
    r = client.post("/init-db", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["was_initialized"] is False
    assert REQUIRED_TABLES <= set(body["tables"])
    assert body["seeded"] == {"categories": 2, "items": 5, "check_points": 15}
    assert client.get("/health").json()["db_initialized"] is True


def test_init_db_is_idempotent(client):
    body = client.post("/init-db", headers=ADMIN).json()
    assert body["was_initialized"] is True
    assert body["seeded"] == {"categories": 0, "items": 0, "check_points": 0}


def test_reset_requires_confirm(client):
    r = client.post("/init-db", headers=ADMIN, json={"reset": True})
    assert r.status_code == 400


def test_checklist_tree(client, admin_token):
    data = client.get("/inspection/checklist", headers=ADMIN).json()
    tree = {c["name"]: {i["name"]: [p["name"] for p in i["check_points"]] for i in c["items"]} for c in data}
    assert tree["窗類"]["工作陽台門"] == ["膠條", "密合度", "五金"]
    assert tree["水電類"]["排水"] == ["浴室", "陽台", "廚房"]


def test_project_and_unit(client, admin_token):
    project = client.post(
        "/projects",
        headers=ADMIN,
        json={"name": "測試建案", "phone": "02-1234-5678", "community_address": "台北市信義區", "community_manager": "王經理"},
    ).json()
    unit_body = {"unit_no": "A-5F-1", "address": "台北市信義區1號5樓", "owner_id_number": "a123456789"}
    r = client.post(f"/projects/{project['id']}/units", headers=ADMIN, json=unit_body)
    assert r.status_code == 201
    assert r.json()["has_id_verification"] is True
    assert "owner_id_hash" not in r.json()

    assert client.post(f"/projects/{project['id']}/units", headers=ADMIN, json=unit_body).status_code == 409


def _make_batch(db, quota_mode: QuotaMode) -> BookingBatch:
    project_id = db.query(Unit).first().project_id
    batch = BookingBatch(project_id=project_id, name=f"批次-{quota_mode.value}",
                         service_type=ServiceType.HEALTH_CHECK, quota_mode=quota_mode)
    batch.services = [BatchService(name="驗屋"), BatchService(name="健檢")]
    db.add(batch)
    db.flush()
    return batch


def _book(db, batch, slot, n, service=None):
    for i in range(n):
        unit = Unit(project_id=batch.project_id, unit_no=f"{batch.name}-{service and service.name}-{i}")
        db.add(unit)
        db.flush()
        db.add(Booking(batch_id=batch.id, slot_id=slot.id, unit_id=unit.id,
                       service_id=service and service.id, contact_name="x", contact_phone="0900"))
    db.flush()


def test_generate_30min_slots():
    with SessionLocal() as db:
        batch = _make_batch(db, QuotaMode.SHARED)
        slots = generate_slots(db, batch, date(2026, 11, 1), time(9, 0), time(12, 0))
        assert len(slots) == 6
        assert (slots[0].start_time, slots[0].end_time) == (time(9, 0), time(9, 30))
        assert all(s.capacity == 3 for s in slots)
        # 再產生一次不會重複
        assert generate_slots(db, batch, date(2026, 11, 1), time(9, 0), time(12, 0)) == []
        db.rollback()


def test_shared_quota_max_3_groups():
    with SessionLocal() as db:
        batch = _make_batch(db, QuotaMode.SHARED)
        slot = generate_slots(db, batch, date(2026, 11, 2), time(9, 0), time(9, 30))[0]
        inspect_svc, health_svc = batch.services
        _book(db, batch, slot, 2, inspect_svc)
        _book(db, batch, slot, 1, health_svc)
        assert remaining_capacity(db, slot) == 0  # 兩種服務合計 3 組，已滿
        db.rollback()


def test_independent_quota_per_service():
    with SessionLocal() as db:
        batch = _make_batch(db, QuotaMode.INDEPENDENT)
        slot = generate_slots(db, batch, date(2026, 11, 3), time(9, 0), time(9, 30))[0]
        inspect_svc, health_svc = batch.services
        _book(db, batch, slot, 3, inspect_svc)
        assert remaining_capacity(db, slot, inspect_svc) == 0
        assert remaining_capacity(db, slot, health_svc) == 3
        db.rollback()


def test_unit_cannot_double_book_same_batch():
    with SessionLocal() as db:
        batch = _make_batch(db, QuotaMode.SHARED)
        slot = generate_slots(db, batch, date(2026, 11, 4), time(9, 0), time(9, 30))[0]
        _book(db, batch, slot, 1)
        first = db.query(Booking).filter_by(batch_id=batch.id).one()

        # 取消後可重新預約
        first.status = BookingStatus.CANCELLED
        db.add(Booking(batch_id=batch.id, slot_id=slot.id, unit_id=first.unit_id, contact_name="x", contact_phone="0900"))
        db.flush()

        # 但同時有兩筆有效預約會被 DB 擋下
        db.add(Booking(batch_id=batch.id, slot_id=slot.id, unit_id=first.unit_id, contact_name="x", contact_phone="0900"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
