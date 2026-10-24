"""M2 第一階段：建案、住戶、健檢日期與時段、各建案的檢查項目清單"""

from datetime import date, datetime

import pytest

from app.database import SessionLocal
from app.models import Booking, InspectionCategory, InspectionResult, Project
from tests.conftest import ADMIN


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def new_project(client, name="M2 測試建案") -> dict:
    r = client.post("/projects", headers=ADMIN, json={
        "name": name, "phone": "02-1234-5678", "address": "台北市大安區建案路 1 號",
        "community_address": "台北市大安區社區路 2 號", "community_manager": "李經理",
    })
    assert r.status_code == 201, r.text
    return r.json()


def book(batch_id: int, slot_id: int, unit_id: int) -> int:
    with SessionLocal() as db:
        b = Booking(batch_id=batch_id, slot_id=slot_id, unit_id=unit_id, contact_name="屋主", contact_phone="0900")
        db.add(b)
        db.commit()
        return b.id


# --- 建案 -------------------------------------------------------------------
def test_project_crud(client):
    p = new_project(client)
    assert (p["unit_count"], p["batch_count"]) == (0, 0)
    assert (p["address"], p["community_address"]) == ("台北市大安區建案路 1 號", "台北市大安區社區路 2 號")

    r = client.patch(f"/projects/{p['id']}", headers=ADMIN, json={"community_manager": "張經理", "phone": None})
    assert r.json()["community_manager"] == "張經理" and r.json()["phone"] is None and r.json()["name"] == "M2 測試建案"

    assert client.delete(f"/projects/{p['id']}", headers=ADMIN).status_code == 204
    assert client.get(f"/projects/{p['id']}", headers=ADMIN).status_code == 404


# --- 住戶 -------------------------------------------------------------------
def test_units(client):
    pid = new_project(client)["id"]
    unit = {
        "unit_no": "A-3F-1", "building": "A", "floor": "3F", "address": "台北市大安區某路 1 號 3 樓",
        "owner_name": "王小明", "owner_phone": "0912345678", "owner_email": "owner@example.com",
        "area_ping": 35.5, "handover_date": "2026-12-20", "note": "邊間",
    }
    r = client.post(f"/projects/{pid}/units", headers=ADMIN, json=unit)
    assert r.status_code == 201, r.text
    u = r.json()
    assert (u["area_ping"], u["handover_date"], u["note"]) == (35.5, "2026-12-20", "邊間")

    # 部分更新：只改有傳的欄位，傳 null 會清空
    r = client.patch(f"/units/{u['id']}", headers=ADMIN, json={"note": None, "area_ping": 36})
    assert (r.json()["note"], r.json()["area_ping"], r.json()["owner_name"]) == (None, 36, "王小明")

    bulk = client.post(f"/projects/{pid}/units/bulk", headers=ADMIN,
                       json={"unit_nos": ["A-3F-1", "A-3F-2", " A-3F-3 ", "A-3F-2", ""], "building": "A"}).json()
    assert bulk == {"created": ["A-3F-2", "A-3F-3"], "skipped": ["A-3F-1", "A-3F-2"]}
    units = client.get(f"/projects/{pid}/units", headers=ADMIN).json()
    assert [x["unit_no"] for x in units] == ["A-3F-1", "A-3F-2", "A-3F-3"]
    assert client.get(f"/projects/{pid}", headers=ADMIN).json()["unit_count"] == 3

    assert client.patch(f"/units/{u['id']}", headers=ADMIN, json={"unit_no": "A-3F-2"}).status_code == 409
    assert client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "X", "owner_email": "not-mail"}).status_code == 422
    assert client.delete(f"/units/{units[2]['id']}", headers=ADMIN).status_code == 204


# --- 健檢日期與時段 ---------------------------------------------------------
def test_batch_generates_30min_slots(client):
    pid = new_project(client)["id"]
    r = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "交屋前健檢", "start_date": "2026-12-01", "end_date": "2026-12-03",
        "day_start": "09:00", "day_end": "12:00",
    })
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["day_count"], b["slot_count"], b["slot_minutes"], b["slot_capacity"]) == (3, 18, 30, 3)
    first_day = b["days"][0]
    assert first_day["date"] == "2026-12-01"
    assert [(s["start_time"], s["end_time"]) for s in first_day["slots"]][:2] == [("09:00:00", "09:30:00"), ("09:30:00", "10:00:00")]
    assert all(s["capacity"] == 3 and s["is_open"] for s in first_day["slots"])

    # 追加日期：重疊的不重複產生
    r = client.post(f"/batches/{b['id']}/dates", headers=ADMIN, json={
        "start_date": "2026-12-03", "end_date": "2026-12-04", "day_start": "09:00", "day_end": "12:00",
    })
    assert (r.json()["day_count"], r.json()["slot_count"]) == (4, 24)
    assert client.get(f"/projects/{pid}/batches", headers=ADMIN).json()[0]["slot_count"] == 24


@pytest.mark.parametrize("body, message", [
    ({"start_date": "2026-12-05", "end_date": "2026-12-01"}, "結束日期"),
    ({"start_date": "2026-01-01", "end_date": "2026-12-31"}, "最多"),
    ({"start_date": "2026-12-01", "end_date": "2026-12-01", "day_start": "12:00", "day_end": "09:00"}, "結束時間"),
    ({"start_date": "2026-12-01", "end_date": "2026-12-01", "day_start": "09:00", "day_end": "09:10"}, "產生不出"),
])
def test_batch_validation(client, body, message):
    pid = new_project(client)["id"]
    r = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={"name": "x", **body})
    assert r.status_code == 422 and message in r.json()["detail"]


def test_close_slots_and_capacity(client):
    pid = new_project(client)["id"]
    unit_id = client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "B-1"}).json()["id"]
    b = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "健檢", "start_date": "2026-12-10", "end_date": "2026-12-11", "day_start": "14:00", "day_end": "15:00",
    }).json()
    slot = b["days"][0]["slots"][0]

    r = client.patch(f"/slots/{slot['id']}", headers=ADMIN, json={"is_open": False, "capacity": 5})
    assert (r.json()["is_open"], r.json()["capacity"]) == (False, 5)

    day = client.patch(f"/batches/{b['id']}/days/2026-12-11", headers=ADMIN, json={"is_open": False}).json()
    assert not any(s["is_open"] for s in day["slots"])
    assert client.get(f"/batches/{b['id']}", headers=ADMIN).json()["open_slot_count"] == 1

    # 有預約時：名額不能低於已預約數；批次與建案不能刪除
    book(b["id"], slot["id"], unit_id)
    detail = client.get(f"/batches/{b['id']}", headers=ADMIN).json()
    assert detail["booked_count"] == 1 and detail["days"][0]["slots"][0]["booked"] == 1
    assert client.patch(f"/slots/{slot['id']}", headers=ADMIN, json={"capacity": 0}).status_code == 422
    assert client.delete(f"/batches/{b['id']}", headers=ADMIN).status_code == 409
    assert client.delete(f"/units/{unit_id}", headers=ADMIN).status_code == 409
    assert client.delete(f"/projects/{pid}", headers=ADMIN).status_code == 409


# --- 檢查項目清單 -----------------------------------------------------------
def tree(categories) -> dict:
    return {c["name"]: {i["name"]: [p["name"] for p in i["check_points"]] for i in c["items"]} for c in categories}


def test_project_checklist_is_independent_copy(client):
    a, b = new_project(client, "A 案")["id"], new_project(client, "B 案")["id"]
    cl = client.get(f"/projects/{a}/checklist", headers=ADMIN).json()
    assert list(tree(cl)) == ["窗戶", "水電", "其他"]
    windows = next(c for c in cl if c["name"] == "窗戶")

    # 新增「浴室窗」：自動沿用窗戶的檢查點
    r = client.post(f"/checklist/categories/{windows['id']}/items", headers=ADMIN, json={"name": "浴室窗"})
    assert tree([r.json()])["窗戶"]["浴室窗"] == ["膠條", "密合度", "五金"]
    item = next(i for i in r.json()["items"] if i["name"] == "浴室窗")
    assert client.post(f"/checklist/categories/{windows['id']}/items", headers=ADMIN, json={"name": "浴室窗"}).status_code == 409

    r = client.post(f"/checklist/items/{item['id']}/points", headers=ADMIN, json={"name": "紗窗"})
    assert tree([r.json()])["窗戶"]["浴室窗"][-1] == "紗窗"

    cat = client.post(f"/projects/{a}/checklist/categories", headers=ADMIN, json={"name": "門"}).json()
    client.post(f"/checklist/categories/{cat['id']}/items", headers=ADMIN, json={"name": "大門", "check_points": ["門鎖", "門框"]})

    a_tree = tree(client.get(f"/projects/{a}/checklist", headers=ADMIN).json())
    b_tree = tree(client.get(f"/projects/{b}/checklist", headers=ADMIN).json())
    assert a_tree["門"] == {"大門": ["門鎖", "門框"]}
    assert "浴室窗" not in b_tree["窗戶"] and "門" not in b_tree  # B 案不受影響
    template = tree(client.get("/inspection/checklist", headers=ADMIN).json())
    assert "浴室窗" not in template["窗戶"]  # 公司範本不受影響


def test_checklist_disable_instead_of_delete_when_used(client):
    pid = new_project(client)["id"]
    unit_id = client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "C-1"}).json()["id"]
    b = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "健檢", "start_date": "2026-12-15", "end_date": "2026-12-15", "day_start": "10:00", "day_end": "10:30",
    }).json()
    booking_id = book(b["id"], b["days"][0]["slots"][0]["id"], unit_id)

    cl = client.get(f"/projects/{pid}/checklist", headers=ADMIN).json()
    item = cl[0]["items"][0]
    used, unused = item["check_points"][0], item["check_points"][1]
    with SessionLocal() as db:
        db.add(InspectionResult(booking_id=booking_id, check_point_id=used["id"], inspected_at=datetime.now()))
        db.commit()

    assert client.delete(f"/checklist/points/{used['id']}", headers=ADMIN).status_code == 409
    assert client.delete(f"/checklist/items/{item['id']}", headers=ADMIN).status_code == 409
    assert client.delete(f"/checklist/categories/{cl[0]['id']}", headers=ADMIN).status_code == 409
    r = client.patch(f"/checklist/points/{used['id']}", headers=ADMIN, json={"is_active": False})
    assert next(p for p in r.json()["items"][0]["check_points"] if p["id"] == used["id"])["is_active"] is False
    assert client.delete(f"/checklist/points/{unused['id']}", headers=ADMIN).status_code == 200


def test_template_not_editable_and_legacy_project_gets_copy(client):
    template_cat = client.get("/inspection/checklist", headers=ADMIN).json()[0]
    assert client.patch(f"/checklist/categories/{template_cat['id']}", headers=ADMIN, json={"name": "x"}).status_code == 404

    with SessionLocal() as db:  # 模擬此功能上線前建立、沒有清單的建案
        p = Project(name="舊建案")
        db.add(p)
        db.commit()
        pid = p.id
    assert len(client.get(f"/projects/{pid}/checklist", headers=ADMIN).json()) == 3
    with SessionLocal() as db:
        assert db.query(InspectionCategory).filter_by(project_id=pid).count() == 3


def test_permissions(client):
    phone = "0966000111"
    client.post("/users", headers=ADMIN, json={"name": "唯讀", "phone": phone, "password": "readonly-1"})
    token = client.post("/auth/login", json={"phone": phone, "password": "readonly-1"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    pid = new_project(client)["id"]

    assert client.get(f"/projects/{pid}/units", headers=h).status_code == 200
    assert client.get(f"/projects/{pid}/checklist", headers=h).status_code == 200
    assert client.post(f"/projects/{pid}/units", headers=h, json={"unit_no": "Z"}).status_code == 403
    assert client.patch(f"/projects/{pid}", headers=h, json={"name": "改名"}).status_code == 403
    assert client.post(f"/projects/{pid}/batches", headers=h, json={
        "name": "x", "start_date": str(date.today()), "end_date": str(date.today()),
    }).status_code == 403


def test_batch_breaks_skip_blocked_slots(client):
    pid = new_project(client)["id"]
    r = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "有午休", "start_date": "2026-12-20", "end_date": "2026-12-20",
        "day_start": "09:00", "day_end": "17:00",
        "breaks": [{"start": "12:00", "end": "13:00"}, {"start": "15:15", "end": "15:45"}],
    })
    assert r.status_code == 201, r.text
    starts = [s["start_time"][:5] for s in r.json()["days"][0]["slots"]]
    assert "11:30" in starts and "12:00" not in starts and "12:30" not in starts and "13:00" in starts
    assert "15:00" not in starts and "15:30" not in starts  # 部分重疊也屏蔽
    assert len(starts) == 16 - 2 - 2

    bad = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "x", "start_date": "2026-12-20", "end_date": "2026-12-20", "breaks": [{"start": "13:00", "end": "12:00"}],
    })
    assert bad.status_code == 422 and "屏蔽區段" in bad.json()["detail"]


def test_bulk_units_with_building_and_floor(client):
    pid = new_project(client)["id"]
    r = client.post(f"/projects/{pid}/units/bulk", headers=ADMIN, json={"units": [
        {"unit_no": "A-2F-1", "building": "A", "floor": "2F"},
        {"unit_no": "B-2F-1", "building": "B", "floor": "2F"},
    ]})
    assert r.json() == {"created": ["A-2F-1", "B-2F-1"], "skipped": []}
    b = next(u for u in client.get(f"/projects/{pid}/units", headers=ADMIN).json() if u["unit_no"] == "B-2F-1")
    assert (b["building"], b["floor"]) == ("B", "2F")
    assert client.post(f"/projects/{pid}/units/bulk", headers=ADMIN, json={}).status_code == 422
