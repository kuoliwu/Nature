"""建案備份檔（.zip）：匯出一個建案的全部資料與檔案，刪除後可以匯入還原。

zip 內容：
  manifest.json   格式、版本、匯出時間、建案名稱
  data.json       {資料表: [每列的欄位值]}（保留原本的編號，匯入時重新編號並換掉外鍵）
  users.json      {人員編號: 手機號碼}（匯入時用手機號碼對應現有人員，找不到就留空）
  files/...       照片、簽名、報告、手冊 PDF、封面照片（storage 相對路徑）

匯入一律建立新的建案（新編號），原建案還在也不會互相影響：
  - 同名建案已存在 → 名稱加「（還原）」
  - 檔案放到 storage/restored/<時間>/ 底下（不和原建案共用檔案）
  - 預約連結 token 沒有衝突就沿用（屋主手上的舊連結還原後還能用），衝突才重新產生
"""

import io
import json
import secrets
import uuid
import zipfile
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import Column, Date, DateTime, Enum, Table, Time, func, insert, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import Project, User

FORMAT = "hompro-project-backup"
VERSION = 1

# 依外鍵相依順序排列；scope：這張表的哪些列屬於這個建案（(外鍵欄位, 上層資料表)）
SCOPE: list[tuple[str, str, str]] = [
    ("projects", "id", "projects"),
    ("units", "project_id", "projects"),
    ("booking_batches", "project_id", "projects"),
    ("batch_services", "batch_id", "booking_batches"),
    ("time_slots", "batch_id", "booking_batches"),
    ("batch_faqs", "batch_id", "booking_batches"),
    ("batch_attachments", "batch_id", "booking_batches"),
    ("custom_forms", "batch_id", "booking_batches"),
    ("custom_form_fields", "form_id", "custom_forms"),
    ("unit_invites", "batch_id", "booking_batches"),
    ("bookings", "batch_id", "booking_batches"),
    ("form_submissions", "form_id", "custom_forms"),
    ("form_submission_files", "submission_id", "form_submissions"),
    ("inspection_categories", "project_id", "projects"),
    ("inspection_items", "category_id", "inspection_categories"),
    ("inspection_check_points", "item_id", "inspection_items"),
    ("inspections", "booking_id", "bookings"),
    ("inspection_results", "booking_id", "bookings"),
    ("inspection_photos", "booking_id", "bookings"),
    ("authorizations", "booking_id", "bookings"),
    ("access_links", "booking_id", "bookings"),
    ("reports", "booking_id", "bookings"),
    ("report_reminders", "booking_id", "bookings"),
    ("handbook_sections", "project_id", "projects"),
    ("handbook_fields", "section_id", "handbook_sections"),
    ("unit_handbooks", "unit_id", "units"),
    ("handbook_values", "unit_id", "units"),
    ("handbook_attachments", "project_id", "projects"),
    ("handbook_entries", "unit_id", "units"),
    ("handbook_photos", "entry_id", "handbook_entries"),
]
TOKEN_COLUMNS = {("unit_invites", "token"), ("access_links", "token"), ("authorizations", "invite_token")}


class BackupError(Exception):
    pass


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _path_columns(table: Table) -> list[str]:
    return [c.name for c in table.columns if c.name.endswith("path")]


def _to_json(col: Column, value):
    if value is None:
        return None
    if isinstance(col.type, Enum) and hasattr(value, "value"):
        return value.value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _from_json(col: Column, value):
    if value is None:
        return None
    if isinstance(col.type, Enum) and col.type.enum_class:
        return col.type.enum_class(value)
    if isinstance(col.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(col.type, Date):
        return date.fromisoformat(value)
    if isinstance(col.type, Time):
        return time.fromisoformat(value)
    return value


def backup_filename(project: Project) -> str:
    name = f"建案備份_{project.name}_{datetime.now():%Y%m%d_%H%M}.zip"
    return "".join(ch for ch in name if ch not in '\\/:*?"<>|')


def export_project(db: Session, project: Project) -> bytes:
    data: dict[str, list[dict]] = {}
    ids: dict[str, list[int]] = {}
    files: set[str] = set()
    user_ids: set[int] = set()
    for name, fk, parent in SCOPE:
        table = _table(name)
        parent_ids = [project.id] if parent == "projects" else ids.get(parent, [])
        rows = db.execute(select(table).where(table.c[fk].in_(parent_ids))).mappings().all() if parent_ids else []
        data[name] = [{c.name: _to_json(c, row[c.name]) for c in table.columns} for row in rows]
        ids[name] = [row["id"] for row in rows]
        for row in rows:
            files.update(row[c] for c in _path_columns(table) if row[c])
            user_ids.update(
                row[c.name] for c in table.columns
                if row[c.name] and any(fk.column.table.name == "users" for fk in c.foreign_keys)
            )
    users = {str(u.id): u.phone for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({
            "format": FORMAT, "version": VERSION, "exported_at": datetime.now().isoformat(timespec="seconds"),
            "project_name": project.name, "counts": {k: len(v) for k, v in data.items() if v},
        }, ensure_ascii=False, indent=2))
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False))
        zf.writestr("users.json", json.dumps(users, ensure_ascii=False))
        for rel in sorted(files):
            path = settings.storage_dir / rel
            if path.is_file():
                # 照片、PDF 本身已壓縮，直接存放比較快
                zf.write(path, f"files/{rel}", compress_type=zipfile.ZIP_STORED)
    return buf.getvalue()


def import_project(db: Session, content: bytes) -> tuple[Project, dict[str, int]]:
    """還原成一個新建案；回傳 (建案, 各資料表筆數)。任何錯誤整份 rollback（呼叫端負責）"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
        manifest = json.loads(zf.read("manifest.json"))
        data: dict[str, list[dict]] = json.loads(zf.read("data.json"))
        users: dict[str, str] = json.loads(zf.read("users.json"))
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise BackupError("不是建案備份檔（請選擇從本系統匯出的 .zip）")
    if manifest.get("format") != FORMAT:
        raise BackupError("不是建案備份檔（請選擇從本系統匯出的 .zip）")
    if manifest.get("version", 0) > VERSION:
        raise BackupError("備份檔來自較新版本的系統，請先更新系統後再匯入")
    if len(data.get("projects", [])) != 1:
        raise BackupError("備份檔內容不完整")

    phone_to_user = {u.phone: u.id for u in db.scalars(select(User))}
    user_map = {int(k): phone_to_user.get(v) for k, v in users.items()}
    folder = Path("restored") / f"{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}"
    new_ids: dict[str, dict[int, int]] = {}
    counts: dict[str, int] = {}
    exported = {name for name, _, _ in SCOPE}

    for name, _, _ in SCOPE:
        table = _table(name)
        new_ids[name] = {}
        for row in data.get(name, []):
            values = {}
            skip = False
            for col in table.columns:
                if col.name == "id" or col.name not in row:
                    continue  # 舊版備份沒有的新欄位：交給資料庫預設值
                value = _from_json(col, row.get(col.name))
                targets = [fk.column.table.name for fk in col.foreign_keys]
                if value is not None and targets:
                    target = targets[0]
                    if target == "users":
                        value = user_map.get(value)
                    elif target in exported:
                        mapped = new_ids.get(target, {}).get(value)
                        if mapped is None and not col.nullable:
                            skip = True  # 指向備份裡沒有的資料（例如舊版公司範本）：略過這一列
                            break
                        value = mapped
                if col.name.endswith("path") and value:
                    value = _restore_file(zf, value, folder)
                values[col.name] = value
            if skip:
                continue
            if name == "projects":
                values["name"] = _free_name(db, values["name"])
            if name == "inspection_categories" and values.get("code"):
                values["code"] = _free_code(db, values["code"], new_ids["projects"][data["projects"][0]["id"]])
            for t, c in TOKEN_COLUMNS:
                if t == name and values.get(c) and db.scalar(select(func.count()).select_from(table).where(table.c[c] == values[c])):
                    values[c] = secrets.token_urlsafe(24)
            new_id = db.execute(insert(table).values(**values)).inserted_primary_key[0]
            new_ids[name][row["id"]] = new_id
            counts[name] = counts.get(name, 0) + 1
    db.flush()
    project = db.get(Project, next(iter(new_ids["projects"].values())))
    return project, counts


def _restore_file(zf: zipfile.ZipFile, rel: str, folder: Path) -> str | None:
    try:
        content = zf.read(f"files/{rel}")
    except KeyError:
        return None  # 匯出時檔案就不在了
    new_rel = folder / rel
    target = settings.storage_dir / new_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return new_rel.as_posix()


def _free_name(db: Session, name: str) -> str:
    candidate, n = name, 1
    while db.scalar(select(func.count(Project.id)).where(Project.name == candidate)):
        candidate = f"{name}（還原{'' if n == 1 else n}）"
        n += 1
    return candidate


def _free_code(db: Session, code: str, project_id: int) -> str:
    table = _table("inspection_categories")
    rest = code.split("-", 1)[1] if code.startswith("p") and "-" in code else code
    candidate = f"p{project_id}-{rest}"[:40]
    while db.scalar(select(func.count()).select_from(table).where(table.c.code == candidate)):
        candidate = f"p{project_id}-{uuid.uuid4().hex[:8]}"
    return candidate
