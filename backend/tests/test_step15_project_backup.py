"""建案備份檔：匯出（資料＋檔案）→ 刪除（有預約也可以刪）→ 匯入還原；原建案還在時匯入則成為副本"""

import io
import json
import zipfile
from datetime import date, timedelta
from urllib.parse import urlsplit

import pytest
from PIL import Image
from pypdf import PdfWriter

from tests.conftest import ADMIN

TOMORROW = date.today() + timedelta(days=1)
STROKES = [[[10, 10], [60, 40], [120, 20]]]


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def jpeg(color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), color).save(buf, "JPEG")
    return buf.getvalue()


def pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def get(client, url: str):
    return client.get(urlsplit(url).path)


def build_full_project(client) -> dict:
    """建案＋住戶＋驗屋預約（屋主自己預約）＋檢查結果、照片、簽名＋外部報告＋住屋手冊＋封面照片"""
    pid = client.post("/projects", headers=ADMIN, json={"name": "備份測試建案", "address": "高雄市備份路 1 號"}).json()["id"]
    uid = client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "D-1", "owner_name": "林屋主", "owner_email": "d1@example.com"}).json()["id"]
    client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "D-2"})
    batch = client.post(f"/projects/{pid}/batches", headers=ADMIN, json={
        "name": "交屋驗屋", "service_type": "inspection", "start_date": str(TOMORROW), "end_date": str(TOMORROW),
        "day_start": "10:00", "day_end": "11:00",
    }).json()
    client.post(f"/batches/{batch['id']}/invites/send", headers=ADMIN, json={})
    token = next(r for r in client.get(f"/batches/{batch['id']}/invites", headers=ADMIN).json() if r["unit_no"] == "D-1")["link"].rsplit("/", 1)[1]
    assert client.post(f"/api/public/book/{token}", json={
        "slot_id": batch["days"][0]["slots"][0]["id"], "contact_name": "林屋主", "contact_phone": "0912000999", "contact_email": "d1@example.com",
    }).status_code == 200
    bid = next(r for r in client.get(f"/batches/{batch['id']}/invites", headers=ADMIN).json() if r["unit_no"] == "D-1")["booking"]["id"]

    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    pts = [p for c in ins["categories"] for i in c["items"] for p in i["points"]]
    for p in pts:
        client.put(f"/inspections/{bid}/results/{p['id']}", headers=ADMIN, json={"result": "pass"})
    client.put(f"/inspections/{bid}/results/{pts[0]['id']}", headers=ADMIN, json={"result": "fail", "note": "窗框刮傷"})
    client.post(f"/inspections/{bid}/photos", headers=ADMIN, data={"check_point_id": str(pts[0]["id"])}, files={"file": ("p.jpg", jpeg(), "image/jpeg")})
    assert client.post(f"/inspections/{bid}/sign", headers=ADMIN, json={"signer_name": "林屋主", "strokes": STROKES, "width": 300, "height": 150}).status_code == 200
    assert client.post(f"/bookings/{bid}/report", headers=ADMIN, files={"file": ("外部報告.pdf", pdf(), "application/pdf")}).status_code == 201

    fields = client.get(f"/units/{uid}/handbook", headers=ADMIN).json()["sections"][0]["fields"]
    client.put(f"/units/{uid}/handbook/values", headers=ADMIN, json={"values": {fields[0]["field_id"]: "2026-11-01"}})
    entry = client.post(f"/units/{uid}/handbook/entries", headers=ADMIN, json={"entry_date": "2026-10-01", "note": "防水試水"}).json()
    client.post(f"/handbook/entries/{entry['id']}/photos", headers=ADMIN, files={"file": ("e.jpg", jpeg("blue"), "image/jpeg")})
    client.post(f"/projects/{pid}/handbook/attachments", headers=ADMIN, files={"file": ("型錄.pdf", pdf(), "application/pdf")})
    client.post(f"/projects/{pid}/covers/inspection", headers=ADMIN, files={"file": ("c.jpg", jpeg("green"), "image/jpeg")})
    client.put(f"/projects/{pid}/pin", headers=ADMIN)
    return {"pid": pid, "uid": uid, "bid": bid, "token": token, "batch": batch["id"]}


def download_backup(client, pid: int) -> bytes:
    link = client.post(f"/projects/{pid}/backup-link", headers=ADMIN).json()
    assert link["filename"].startswith("建案備份_備份測試建案_") and link["filename"].endswith(".zip")
    r = get(client, link["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    return r.content


def restore(client, content: bytes) -> dict:
    r = client.post("/projects/import", headers=ADMIN, files={"file": ("backup.zip", content, "application/zip")})
    assert r.status_code == 201, r.text
    return r.json()


def test_backup_delete_and_restore(client):
    p = build_full_project(client)
    content = download_backup(client, p["pid"])
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        files = [n for n in zf.namelist() if n.startswith("files/")]
    assert manifest["project_name"] == "備份測試建案" and manifest["counts"]["bookings"] == 1
    assert len(files) == 6  # 檢查照片、簽名、外部報告、手冊照片、共用 PDF、封面照片

    # 有預約紀錄的建案也可以刪除
    assert client.delete(f"/projects/{p['pid']}", headers=ADMIN).status_code == 204
    assert client.get(f"/projects/{p['pid']}", headers=ADMIN).status_code == 404
    assert client.get(f"/api/public/book/{p['token']}").status_code == 404

    out = restore(client, content)
    new = out["project"]
    assert new["name"] == "備份測試建案" and new["unit_count"] == 2
    assert out["counts"]["bookings"] == 1 and out["counts"]["inspection_results"] == manifest["counts"]["inspection_results"]
    assert new["covers"]["inspection"] and get(client, new["covers"]["inspection"]).headers["content-type"] == "image/jpeg"
    assert not new["pinned"]  # 釘選是個人設定，不在備份裡

    # 屋主原本的預約連結還能用（token 沒有衝突就沿用）
    info = client.get(f"/api/public/book/{p['token']}").json()
    assert info["project_name"] == "備份測試建案" and info["current"]["contact_name"] == "林屋主"

    # 驗屋：結果、備註、照片、簽名、外部報告都回來了
    units = client.get(f"/projects/{new['id']}/units", headers=ADMIN).json()
    d1 = next(u for u in units if u["unit_no"] == "D-1")
    batch = client.get(f"/projects/{new['id']}/batches", headers=ADMIN).json()[0]
    bid = next(r for r in client.get(f"/batches/{batch['id']}/invites", headers=ADMIN).json() if r["unit_no"] == "D-1")["booking"]["id"]
    ins = client.get(f"/inspections/{bid}", headers=ADMIN).json()
    assert ins["status"] == "signed" and ins["signer_name"] == "林屋主"
    failed = [p for c in ins["categories"] for i in c["items"] for p in i["points"] if p["result"] == "fail"]
    assert len(failed) == 1 and failed[0]["note"] == "窗框刮傷" and len(failed[0]["photos"]) == 1
    assert get(client, failed[0]["photos"][0]["url"]).headers["content-type"] == "image/jpeg"
    assert get(client, ins["signature_url"]).headers["content-type"] == "image/png"
    assert ins["external_report"]["filename"] == "外部報告.pdf" and get(client, ins["external_report"]["url"]).status_code == 200
    assert client.post(f"/inspections/{bid}/report-link", headers=ADMIN).status_code == 200  # 報告 PDF 也能重新產生

    # 住屋手冊：欄位值、生產履歷紀錄與照片、共用 PDF
    hb = client.get(f"/units/{d1['id']}/handbook", headers=ADMIN).json()
    assert hb["sections"][0]["fields"][0]["value"] == "2026-11-01"
    assert hb["entries"][0]["note"] == "防水試水" and len(hb["entries"][0]["photos"]) == 1
    assert [a["title"] for a in hb["attachments"]] == ["型錄"]
    assert client.post(f"/units/{d1['id']}/handbook/preview-link", headers=ADMIN).status_code == 200


def test_restore_while_original_exists_makes_a_copy(client):
    p = build_full_project(client)
    content = download_backup(client, p["pid"])
    copy = restore(client, content)["project"]
    assert copy["name"].startswith("備份測試建案（還原") and copy["id"] != p["pid"]

    # 原建案不受影響，原預約連結仍指向原建案；副本的連結是新的
    assert client.get(f"/api/public/book/{p['token']}").json()["current"]["contact_name"] == "林屋主"
    batch = client.get(f"/projects/{copy['id']}/batches", headers=ADMIN).json()[0]
    links = [r["link"].rsplit("/", 1)[1] for r in client.get(f"/batches/{batch['id']}/invites", headers=ADMIN).json() if r["link"]]
    assert links and p["token"] not in links

    # 檢查清單在副本裡各自一份（刪原建案不影響副本）
    assert client.delete(f"/projects/{p['pid']}", headers=ADMIN).status_code == 204
    units = client.get(f"/projects/{copy['id']}/units", headers=ADMIN).json()
    assert {u["unit_no"] for u in units} == {"D-1", "D-2"}
    assert client.get(f"/projects/{copy['id']}/checklist", headers=ADMIN, params={"service": "inspection"}).status_code == 200


def test_import_rejects_other_files(client):
    r = client.post("/projects/import", headers=ADMIN, files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert r.status_code == 422 and "備份檔" in r.json()["detail"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "other"}))
    r = client.post("/projects/import", headers=ADMIN, files={"file": ("x.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422


def test_backup_scope_covers_all_project_tables():
    """新增的資料表若掛在建案底下（外鍵指向備份範圍內的表），必須加進 SCOPE，否則備份會漏資料"""
    from app.database import Base
    from app.services.project_backup import SCOPE

    scoped = {name for name, _, _ in SCOPE}
    not_backed_up = {"project_pins", "project_orders", "user_permissions"}  # 個人釘選與排序、依建案指定的人員權限：刻意不放
    missing = [
        t.name for t in Base.metadata.sorted_tables
        if t.name not in scoped | not_backed_up
        and any(fk.column.table.name in scoped for c in t.columns for fk in c.foreign_keys)
    ]
    assert missing == []
