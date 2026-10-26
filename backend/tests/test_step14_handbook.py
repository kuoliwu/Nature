"""售服步驟 5：住屋手冊（範本、逐戶填寫、外部 PDF 合併、Review OK、寄送）"""

import io
from email import message_from_bytes, policy
from urllib.parse import urlsplit

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.config import settings
from tests.conftest import ADMIN


@pytest.fixture(autouse=True)
def _login(admin_token):
    pass


def outbox() -> set:
    return set((settings.storage_dir / "outbox").glob("*.eml"))


def blank_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def upload(client, url: str, pages: int, name: str):
    return client.post(url, headers=ADMIN, files={"file": (name, blank_pdf(pages), "application/pdf")})


def pdf_pages(client, url: str) -> int:
    r = client.get(urlsplit(url).path)
    assert r.status_code == 200, r.text
    return len(PdfReader(io.BytesIO(r.content)).pages)


@pytest.fixture
def project(client):
    pid = client.post("/projects", headers=ADMIN, json={"name": "手冊建案", "address": "新竹市手冊路 1 號"}).json()["id"]
    units = [
        client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": n, "owner_name": f"屋主{n}", "owner_email": f"{n}@example.com"}).json()["id"]
        for n in ("A-1", "A-2")
    ]
    return pid, units


def fill_required(client, unit_id: int) -> dict:
    hb = client.get(f"/units/{unit_id}/handbook", headers=ADMIN).json()
    values = {f["field_id"]: f"內容{f['field_id']}" for s in hb["sections"] for f in s["fields"] if f["required"] and not f["default_value"]}
    r = client.put(f"/units/{unit_id}/handbook/values", headers=ADMIN, json={"values": values})
    assert r.status_code == 200, r.text
    return r.json()


def test_template_seeded_and_editable(client, project):
    pid, (u1, _) = project
    t = client.get(f"/projects/{pid}/handbook/template", headers=ADMIN).json()
    assert [s["name"] for s in t["sections"]] == ["住屋手冊：保固", "住屋手冊：聯絡資訊"]
    structure = next(f for f in t["sections"][0]["fields"] if f["label"] == "結構體保固")
    assert structure["default_value"] == "15 年" and not structure["required"]
    assert not any(f["required"] for s in t["sections"] for f in s["fields"])  # 預設全部選填

    # 新增分類與欄位、設共用預設值、排序
    t = client.post(f"/projects/{pid}/handbook/sections", headers=ADMIN, json={"name": "智慧家庭"}).json()
    sid = t["sections"][-1]["id"]
    t = client.post(f"/handbook/sections/{sid}/fields", headers=ADMIN, json={"label": "網路設備", "default_value": "光纖到府", "required": False}).json()
    fid = t["sections"][-1]["fields"][0]["id"]
    t = client.post(f"/handbook/sections/{sid}/move", headers=ADMIN, json={"direction": "up"}).json()
    assert t["sections"][-2]["name"] == "智慧家庭"
    t = client.patch(f"/handbook/fields/{fid}", headers=ADMIN, json={"default_value": None}).json()
    assert next(f for s in t["sections"] for f in s["fields"] if f["id"] == fid)["default_value"] is None

    # 有住戶填過的欄位不能刪，只能停用
    assert client.put(f"/units/{u1}/handbook/values", headers=ADMIN, json={"values": {fid: "Wi-Fi 6"}}).status_code == 200
    assert client.delete(f"/handbook/fields/{fid}", headers=ADMIN).status_code == 409
    assert client.delete(f"/handbook/sections/{sid}", headers=ADMIN).status_code == 409
    t = client.patch(f"/handbook/fields/{fid}", headers=ADMIN, json={"is_active": False}).json()
    assert next(f for s in t["sections"] for f in s["fields"] if f["id"] == fid)["has_values"]
    assert all(f["field_id"] != fid for s in client.get(f"/units/{u1}/handbook", headers=ADMIN).json()["sections"] for f in s["fields"])


def test_unit_flow_merge_approve_send(client, project, monkeypatch):
    monkeypatch.setattr(settings, "mail_from", "service@example.com")  # 售服信箱
    pid, (u1, u2) = project
    # 預設範本都是選填；自己設一個必填欄位來測試
    t = client.get(f"/projects/{pid}/handbook/template", headers=ADMIN).json()
    hotline = next(f for s in t["sections"] for f in s["fields"] if f["label"] == "售服專線")
    client.patch(f"/handbook/fields/{hotline['id']}", headers=ADMIN, json={"required": True})
    rows = client.get(f"/projects/{pid}/handbooks", headers=ADMIN).json()
    assert [r["unit_no"] for r in rows] == ["A-1", "A-2"] and rows[0]["missing"] > 0 and rows[0]["status"] == "draft"

    # 必填沒填完不能 Review OK
    r = client.post(f"/units/{u1}/handbook/approve", headers=ADMIN)
    assert r.status_code == 409 and "必填" in r.json()["detail"]

    # 外部 PDF：建案共用 2 份、單戶 1 份；不是 PDF 的拒收
    assert client.post(f"/units/{u1}/handbook/attachments", headers=ADMIN, files={"file": ("x.pdf", b"hello", "application/pdf")}).status_code == 422
    t = upload(client, f"/projects/{pid}/handbook/attachments", 2, "建材型錄.pdf").json()
    t = upload(client, f"/projects/{pid}/handbook/attachments", 1, "設備說明書.pdf").json()
    assert [a["title"] for a in t["attachments"]] == ["建材型錄", "設備說明書"]
    t = client.post(f"/handbook/attachments/{t['attachments'][1]['id']}/move", headers=ADMIN, json={"direction": "up"}).json()
    assert [a["title"] for a in t["attachments"]] == ["設備說明書", "建材型錄"]
    hb = upload(client, f"/units/{u1}/handbook/attachments", 3, "A-1 管線圖.pdf").json()
    assert [(a["title"], a["shared"]) for a in hb["attachments"]] == [("設備說明書", True), ("建材型錄", True), ("A-1 管線圖", False)]

    hb = fill_required(client, u1)
    assert hb["missing"] == []
    # 預覽：系統頁 + 共用 3 頁 + 單戶 3 頁
    link = client.post(f"/units/{u1}/handbook/preview-link", headers=ADMIN).json()
    total = pdf_pages(client, link["url"])
    assert total >= 1 + 3 + 3

    # Review OK → 內容鎖定 → 取消確認 → 再確認
    assert client.post(f"/units/{u1}/handbook/approve", headers=ADMIN).json()["status"] == "approved"
    some_field = hb["sections"][0]["fields"][0]["field_id"]
    assert client.put(f"/units/{u1}/handbook/values", headers=ADMIN, json={"values": {some_field: "改"}}).status_code == 409
    assert upload(client, f"/units/{u1}/handbook/attachments", 1, "晚到.pdf").status_code == 409
    assert client.post(f"/units/{u1}/handbook/unapprove", headers=ADMIN).json()["status"] == "draft"
    assert client.post(f"/units/{u1}/handbook/approve", headers=ADMIN).json()["approved_by"] == "測試管理者"

    # 寄送：附上合併後的完整 PDF；時間軸步驟 5 已寄送 1/2
    before = outbox()
    hb = client.post(f"/units/{u1}/handbook/send", headers=ADMIN, json={}).json()
    assert hb["status"] == "sent" and hb["sent_to"] == "service@example.com" and hb["service_email"] == "service@example.com"
    [path] = sorted(outbox() - before)
    mail = message_from_bytes(path.read_bytes(), policy=policy.default)
    assert mail["Subject"].startswith("【手冊匯出】") and mail["To"] == "service@example.com"
    assert "A-1@example.com" in mail.get_body(("plain",)).get_content()  # 內文帶屋主資料給售服
    [att] = list(mail.iter_attachments())
    assert len(PdfReader(io.BytesIO(att.get_content())).pages) == total

    step = next(s for s in client.get(f"/projects/{pid}/timeline", headers=ADMIN).json()["steps"] if s["key"] == "handbook")
    assert (step["status"], step["done"], step["total"]) == ("active", 1, 2)

    # 第二戶也寄出 → 步驟 5 完成
    fill_required(client, u2)
    client.post(f"/units/{u2}/handbook/approve", headers=ADMIN)
    assert client.post(f"/units/{u2}/handbook/send", headers=ADMIN, json={"to": "other@example.com"}).json()["sent_to"] == "other@example.com"
    step = next(s for s in client.get(f"/projects/{pid}/timeline", headers=ADMIN).json()["steps"] if s["key"] == "handbook")
    assert (step["status"], step["note"]) == ("done", "已寄送 2/2")


def test_send_requires_approval(client, project):
    _, (u1, _) = project
    r = client.post(f"/units/{u1}/handbook/send", headers=ADMIN, json={})
    assert r.status_code == 409 and "Review OK" in r.json()["detail"]


def jpeg(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), color).save(buf, "JPEG")
    return buf.getvalue()


def test_production_entries_with_photos(client, project):
    pid, (u1, _) = project
    r = client.post(f"/units/{u1}/handbook/entries", headers=ADMIN, json={"entry_date": "2026-10-20", "note": "防水試水 48 小時無滲漏"})
    assert r.status_code == 201, r.text
    entry = r.json()
    assert entry["created_by"] == "測試管理者" and entry["photos"] == []
    for color in ("red", "blue", "green"):
        entry = client.post(f"/handbook/entries/{entry['id']}/photos", headers=ADMIN, files={"file": ("p.jpg", jpeg(color), "image/jpeg")}).json()
    assert len(entry["photos"]) == 3 and entry["photos"][0]["width"] == 800
    assert client.get(urlsplit(entry["photos"][0]["url"]).path).headers["content-type"] == "image/jpeg"
    assert client.post(f"/handbook/entries/{entry['id']}/photos", headers=ADMIN, files={"file": ("x.jpg", b"nope", "image/jpeg")}).status_code == 422
    entry = client.delete(f"/handbook/photos/{entry['photos'][2]['id']}", headers=ADMIN).json()
    assert len(entry["photos"]) == 2

    # 只有文字、沒有照片的紀錄；日期較早的排前面
    early = client.post(f"/units/{u1}/handbook/entries", headers=ADMIN, json={"entry_date": "2026-09-01", "note": "結構體完成"}).json()
    hb = client.get(f"/units/{u1}/handbook", headers=ADMIN).json()
    assert [e["id"] for e in hb["entries"]] == [early["id"], entry["id"]]
    assert next(r for r in client.get(f"/projects/{pid}/handbooks", headers=ADMIN).json() if r["unit_id"] == u1)["entries"] == 2
    upd = client.patch(f"/handbook/entries/{early['id']}", headers=ADMIN, json={"entry_date": "2026-09-02", "note": " "}).json()
    assert (upd["entry_date"], upd["note"]) == ("2026-09-02", None)

    # 紀錄與照片會放進手冊 PDF（照片頁數比沒照片時多）
    link = client.post(f"/units/{u1}/handbook/preview-link", headers=ADMIN).json()
    pdf = PdfReader(io.BytesIO(client.get(urlsplit(link["url"]).path).content))
    assert sum(len(page.images) for page in pdf.pages) == 2

    # 確認後鎖定：不能新增、修改、刪除紀錄或照片
    fill_required(client, u1)
    client.post(f"/units/{u1}/handbook/approve", headers=ADMIN)
    assert client.post(f"/units/{u1}/handbook/entries", headers=ADMIN, json={"entry_date": "2026-10-26"}).status_code == 409
    assert client.delete(f"/handbook/entries/{early['id']}", headers=ADMIN).status_code == 409
    assert client.delete(f"/handbook/photos/{entry['photos'][0]['id']}", headers=ADMIN).status_code == 409
    client.post(f"/units/{u1}/handbook/unapprove", headers=ADMIN)
    assert client.delete(f"/handbook/entries/{entry['id']}", headers=ADMIN).status_code == 204
    assert len(client.get(f"/units/{u1}/handbook", headers=ADMIN).json()["entries"]) == 1


def test_template_v1_migrated_once(client):
    """舊版（第 1 版）範本：拿掉的分類沒人填就刪、有人填就停用；保固、聯絡資訊改選填；只遷移一次"""
    from app.database import SessionLocal
    from app.models import HandbookField, HandbookSection, HandbookValue, Project, Unit
    from app.services.handbook import migrate_template

    pid = client.post("/projects", headers=ADMIN, json={"name": "舊範本建案"}).json()["id"]
    uid = client.post(f"/projects/{pid}/units", headers=ADMIN, json={"unit_no": "B-1"}).json()["id"]
    with SessionLocal() as db:
        for sec in db.query(HandbookSection).filter_by(project_id=pid):
            db.delete(sec)
        v1 = [("生產履歷：建築概要", True), ("生產履歷：廠商通訊錄", True), ("住屋手冊：保固", True), ("住屋手冊：使用與保養", True)]
        for i, (name, req) in enumerate(v1):
            db.add(HandbookSection(project_id=pid, name=name, sort_order=i, fields=[HandbookField(label=f"{name}欄位", required=req)]))
        db.flush()
        used = db.query(HandbookField).filter_by(label="生產履歷：建築概要欄位").one()
        db.add(HandbookValue(unit_id=uid, field_id=used.id, value="已填"))
        db.get(Project, pid).handbook_template_version = None
        db.commit()
        assert migrate_template(db) >= 1
        t = client.get(f"/projects/{pid}/handbook/template", headers=ADMIN).json()
        assert [(s["name"], s["is_active"]) for s in t["sections"]] == [("住屋手冊：保固", True), ("生產履歷：建築概要", False)]
        assert not any(f["required"] for s in t["sections"] if s["is_active"] for f in s["fields"])
        assert client.get(f"/units/{uid}/handbook", headers=ADMIN).json()["missing"] == []  # 停用的分類不算必填

        # 之後自己加回同名分類，不會再被遷移刪掉
        client.post(f"/projects/{pid}/handbook/sections", headers=ADMIN, json={"name": "生產履歷：廠商通訊錄"})
        assert migrate_template(db) == 0
        names = [s["name"] for s in client.get(f"/projects/{pid}/handbook/template", headers=ADMIN).json()["sections"]]
        assert "生產履歷：廠商通訊錄" in names
