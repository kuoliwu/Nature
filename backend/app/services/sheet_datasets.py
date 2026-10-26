"""各種資料的 Excel 匯出匯入定義（建案、檢查清單、時段、預約名單、人員、驗屋結果）。
住戶的匯出匯入在 units_excel.py（較早實作，規則相同）。"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CHECKLIST_SERVICES,
    PERMISSIONS,
    Booking,
    BookingStatus,
    CheckResult,
    Inspection,
    InspectionCategory,
    InspectionCheckPoint,
    InspectionItem,
    InspectionResult,
    InspectionStatus,
    Project,
    TimeSlot,
    Unit,
    UnitInvite,
    User,
    UserPermission,
    UserRole,
)
from app.schemas import password_problem
from app.seed import copy_template_to_project, ensure_project_checklist
from app.services.auth import hash_password, normalize_phone
from app.services.sheets import Col, Dataset, ImportOutcome
from app.services.slots import ACTIVE_STATUSES

Rows = list[tuple[int, dict]]


def _changed(obj, values: dict, present: list[str]) -> dict:
    return {k: v for k, v in values.items() if k in present and getattr(obj, k) != v}


# ---------------------------------------------------------------------------
# 建案
# ---------------------------------------------------------------------------
PROJECT_COLS = [
    Col("name", "案名", 24, required=True, max_len=100),
    Col("phone", "建案電話", 16, "phone", max_len=30),
    Col("address", "建案地址", 36),
    Col("community_address", "社區地址", 36),
    Col("community_manager", "社區經理", 12, max_len=50),
    Col("note", "備註", 30, max_len=2000),
    Col("unit_count", "住戶數", 10, "int", export_only=True),
]


def _projects_export(db: Session, ctx: dict) -> list[dict]:
    counts = dict(db.execute(select(Unit.project_id, func.count(Unit.id)).group_by(Unit.project_id)).all())
    return [
        {"name": p.name, "phone": p.phone, "address": p.address, "community_address": p.community_address, "community_manager": p.community_manager,
         "note": p.note, "unit_count": counts.get(p.id, 0)}
        for p in db.scalars(select(Project).order_by(Project.id))
    ]


def _projects_apply(db: Session, ctx: dict, rows: Rows, present: list[str], out: ImportOutcome) -> None:
    existing = {p.name: p for p in db.scalars(select(Project))}
    seen: dict[str, int] = {}
    for row_no, v in rows:
        if v["name"] in seen:
            out.error(row_no, f"案名「{v['name']}」與第 {seen[v['name']]} 列重複")
            continue
        seen[v["name"]] = row_no
        project = existing.get(v["name"])
        if project is None:
            project = Project(**{k: v.get(k) for k in ("name", "phone", "address", "community_address", "community_manager", "note")})
            db.add(project)
            db.flush()
            for service in CHECKLIST_SERVICES:
                copy_template_to_project(db, project, service)
            out.created.append(v["name"])
        elif changes := _changed(project, v, present):
            for k, val in changes.items():
                setattr(project, k, val)
            out.updated.append(v["name"])
        else:
            out.unchanged += 1


PROJECTS = Dataset(
    name="projects", sheet="建案", columns=PROJECT_COLS, scope="global",
    instructions=["・以「案名」比對：已存在的建案更新資料，不存在的會新增（並自動帶入驗屋、健檢檢查清單）。"],
    export_rows=_projects_export, apply=_projects_apply, import_permission="project.manage",
)


# ---------------------------------------------------------------------------
# 檢查項目清單（建案 + 驗屋 / 健檢）
# ---------------------------------------------------------------------------
CHECKLIST_COLS = [
    Col("category", "類別", 14, required=True, max_len=50),
    Col("item", "項目", 18, required=True, max_len=50),
    Col("point", "檢查點", 18, required=True, max_len=50),
    Col("active", "啟用", 8, "bool"),
]


def _checklist_export(db: Session, ctx: dict) -> list[dict]:
    cats = ensure_project_checklist(db, ctx["project"], ctx["service"])
    return [
        {"category": c.name, "item": i.name, "point": p.name, "active": c.is_active and i.is_active and p.is_active}
        for c in cats for i in c.items for p in i.check_points
    ]


def _checklist_apply(db: Session, ctx: dict, rows: Rows, present: list[str], out: ImportOutcome) -> None:
    project, service = ctx["project"], ctx["service"]
    cats = {c.name: c for c in ensure_project_checklist(db, project, service)}
    for row_no, v in rows:
        label = f"{v['category']}／{v['item']}／{v['point']}"
        cat = cats.get(v["category"])
        if cat is None:
            cat = InspectionCategory(
                code=f"p{project.id}-{uuid.uuid4().hex[:8]}", name=v["category"], project_id=project.id,
                service_type=service, sort_order=len(cats),
            )
            db.add(cat)
            cats[cat.name] = cat
        item = next((i for i in cat.items if i.name == v["item"]), None)
        if item is None:
            item = InspectionItem(name=v["item"], sort_order=len(cat.items))
            cat.items.append(item)
        point = next((p for p in item.check_points if p.name == v["point"]), None)
        active = v.get("active")
        if point is None:
            item.check_points.append(InspectionCheckPoint(
                name=v["point"], sort_order=len(item.check_points), is_active=True if active is None else active,
            ))
            out.created.append(label)
        elif "active" in present and active is not None and point.is_active != active:
            point.is_active = active
            out.updated.append(label)
        else:
            out.unchanged += 1


CHECKLIST = Dataset(
    name="checklist", sheet="檢查清單", columns=CHECKLIST_COLS, scope="project_service",
    instructions=[
        "・每列一個檢查點；以「類別＋項目＋檢查點」比對。新的類別、項目、檢查點會自動建立。",
        "・「啟用」填「否」可停用（已有檢查紀錄的檢查點不會被刪除）。",
    ],
    export_rows=_checklist_export, apply=_checklist_apply, import_permission="project.manage",
)


# ---------------------------------------------------------------------------
# 日期時段（預約批次）
# ---------------------------------------------------------------------------
SLOT_COLS = [
    Col("date", "日期", 13, "date", required=True),
    Col("start", "開始", 8, "time", required=True),
    Col("end", "結束", 8, "time"),
    Col("capacity", "名額", 8, "int"),
    Col("open", "開放", 8, "bool"),
    Col("booked", "已預約", 8, "int", export_only=True),
    Col("units", "預約戶別", 30, export_only=True),
]


def _booked(db: Session, batch_id: int) -> dict[int, list[str]]:
    rows = db.execute(
        select(Booking.slot_id, Unit.unit_no).join(Unit, Booking.unit_id == Unit.id)
        .where(Booking.batch_id == batch_id, Booking.status.in_(ACTIVE_STATUSES)).order_by(Unit.unit_no)
    )
    out: dict[int, list[str]] = {}
    for slot_id, unit_no in rows:
        out.setdefault(slot_id, []).append(unit_no)
    return out


def _slots_export(db: Session, ctx: dict) -> list[dict]:
    booked = _booked(db, ctx["batch"].id)
    return [
        {"date": s.slot_date, "start": s.start_time, "end": s.end_time, "capacity": s.capacity, "open": s.is_open,
         "booked": len(booked.get(s.id, [])), "units": "、".join(booked.get(s.id, []))}
        for s in sorted(ctx["batch"].slots, key=lambda s: (s.slot_date, s.start_time))
    ]


def _slots_apply(db: Session, ctx: dict, rows: Rows, present: list[str], out: ImportOutcome) -> None:
    batch = ctx["batch"]
    slots = {(s.slot_date, s.start_time): s for s in batch.slots}
    booked = {k: len(v) for k, v in _booked(db, batch.id).items()}
    for row_no, v in rows:
        label = f"{v['date']} {v['start']:%H:%M}"
        slot = slots.get((v["date"], v["start"]))
        if slot is None:
            if v.get("end") is None:
                out.error(row_no, "新增時段需要填「結束」時間")
                continue
            if v["end"] <= v["start"]:
                out.error(row_no, "結束時間必須晚於開始時間")
                continue
            if (v.get("capacity") or batch.slot_capacity) < 1:
                out.error(row_no, "名額至少 1")
                continue
            slot = TimeSlot(
                batch_id=batch.id, slot_date=v["date"], start_time=v["start"], end_time=v["end"],
                capacity=v.get("capacity") or batch.slot_capacity, is_open=True if v.get("open") is None else v["open"],
            )
            db.add(slot)
            slots[(v["date"], v["start"])] = slot
            out.created.append(label)
            continue
        changes = {}
        if "capacity" in present and v.get("capacity") is not None and v["capacity"] != slot.capacity:
            if v["capacity"] < max(1, booked.get(slot.id, 0)):
                out.error(row_no, f"{label} 已有 {booked.get(slot.id, 0)} 組預約，名額不能少於此數且至少 1")
                continue
            changes["capacity"] = v["capacity"]
        if "open" in present and v.get("open") is not None and v["open"] != slot.is_open:
            changes["is_open"] = v["open"]
        for k, val in changes.items():
            setattr(slot, k, val)
        if changes:
            out.updated.append(label)
        else:
            out.unchanged += 1


SLOTS = Dataset(
    name="slots", sheet="時段", columns=SLOT_COLS, scope="batch",
    instructions=[
        "・以「日期＋開始時間」比對：已存在的時段可修改名額與是否開放；不存在的會新增（需填結束時間）。",
        "・名額不能少於已預約的組數。時段不會因為檔案裡沒有而被刪除。",
    ],
    export_rows=_slots_export, apply=_slots_apply, import_permission="batch.manage",
)


# ---------------------------------------------------------------------------
# 預約名單（電話 / 紙本預約匯入）
# ---------------------------------------------------------------------------
STATUS_TEXT = {"booked": "已預約", "completed": "已完成"}
BOOKING_COLS = [
    Col("unit_no", "戶別", 12, required=True, max_len=30),
    Col("owner_name", "屋主", 10, export_only=True),
    Col("date", "日期", 13, "date"),
    Col("start", "開始時間", 9, "time"),
    Col("contact_name", "聯絡人", 10, max_len=50),
    Col("contact_phone", "電話", 13, "phone", max_len=20),
    Col("contact_email", "Email", 26, "email"),
    Col("note", "備註", 20, max_len=500),
    Col("status", "狀態", 8, export_only=True),
    Col("invite", "邀請", 10, export_only=True),
]


def _bookings_export(db: Session, ctx: dict) -> list[dict]:
    batch = ctx["batch"]
    bookings = {
        b.unit_id: b for b in db.scalars(select(Booking).where(Booking.batch_id == batch.id, Booking.status.in_(ACTIVE_STATUSES)))
    }
    invites = {i.unit_id: i for i in db.scalars(select(UnitInvite).where(UnitInvite.batch_id == batch.id))}
    rows = []
    for u in db.scalars(select(Unit).where(Unit.project_id == batch.project_id).order_by(Unit.unit_no)):
        b, inv = bookings.get(u.id), invites.get(u.id)
        rows.append({
            "unit_no": u.unit_no, "owner_name": u.owner_name,
            "date": b.slot.slot_date if b else None, "start": b.slot.start_time if b else None,
            "contact_name": b.contact_name if b else None, "contact_phone": b.contact_phone if b else None,
            "contact_email": b.contact_email if b else None, "note": b.note if b else None,
            "status": STATUS_TEXT.get(b.status.value) if b else "未預約",
            "invite": "已寄送" if inv and inv.sent_at else ("缺 Email" if not u.owner_email else "未寄送"),
        })
    return rows


def _bookings_apply(db: Session, ctx: dict, rows: Rows, present: list[str], out: ImportOutcome) -> None:
    batch = ctx["batch"]
    units = {u.unit_no: u for u in db.scalars(select(Unit).where(Unit.project_id == batch.project_id))}
    slots = {(s.slot_date, s.start_time): s for s in batch.slots}
    touched: set[int] = set()
    for row_no, v in rows:
        unit = units.get(v["unit_no"])
        if unit is None:
            out.error(row_no, f"找不到戶別「{v['unit_no']}」")
            continue
        if v.get("date") is None and v.get("start") is None:
            out.unchanged += 1  # 沒填日期時間：不預約、也不取消
            continue
        if v.get("date") is None or v.get("start") is None:
            out.error(row_no, "日期與開始時間要一起填")
            continue
        slot = slots.get((v["date"], v["start"]))
        if slot is None:
            out.error(row_no, f"沒有 {v['date']} {v['start']:%H:%M} 這個時段")
            continue
        contact = {
            "contact_name": v.get("contact_name") or unit.owner_name,
            "contact_phone": v.get("contact_phone") or unit.owner_phone,
            "contact_email": v.get("contact_email") or unit.owner_email,
            "note": v.get("note"),
        }
        if not contact["contact_name"] or not contact["contact_phone"]:
            out.error(row_no, "請填聯絡人與電話（或先在住戶資料填屋主姓名、電話）")
            continue
        current = db.scalar(select(Booking).where(
            Booking.batch_id == batch.id, Booking.unit_id == unit.id, Booking.status.in_(ACTIVE_STATUSES)
        ))
        if current and current.status == BookingStatus.COMPLETED:
            out.error(row_no, f"{unit.unit_no} 已完成，不能更改預約")
            continue
        if current is None:
            db.add(Booking(batch_id=batch.id, slot_id=slot.id, unit_id=unit.id, **contact))
            out.created.append(unit.unit_no)
        else:
            changes = {k: val for k, val in contact.items() if k in present and getattr(current, k) != val}
            if current.slot_id != slot.id:
                changes["slot_id"] = slot.id
            for k, val in changes.items():
                setattr(current, k, val)
            if changes:
                out.updated.append(unit.unit_no)
            else:
                out.unchanged += 1
        touched.add(slot.id)
    db.flush()
    for slot_id in touched:  # 寫入後再檢查名額，與線上預約相同規則
        slot = db.get(TimeSlot, slot_id)
        used = db.scalar(select(func.count(Booking.id)).where(Booking.slot_id == slot_id, Booking.status.in_(ACTIVE_STATUSES)))
        if used > slot.capacity:
            out.error(0, f"{slot.slot_date} {slot.start_time:%H:%M} 名額 {slot.capacity} 組，匯入後會有 {used} 組，超過名額")


BOOKINGS = Dataset(
    name="bookings", sheet="預約名單", columns=BOOKING_COLS, scope="batch",
    instructions=[
        "・每列一戶；填「日期」與「開始時間」即代表預約該時段（用於電話、紙本預約）。日期留空的戶別不會變動。",
        "・已預約的戶別改日期時間＝改期；已完成驗屋／報到的不能改。",
        "・聯絡人、電話留空時使用住戶資料中的屋主姓名、電話。",
        "・匯入不會寄確認信給屋主；名額規則與線上預約相同（不會超賣）。",
    ],
    export_rows=_bookings_export, apply=_bookings_apply,
    export_permission="booking.view", import_permission="booking.manage",
)


# ---------------------------------------------------------------------------
# 人員帳號
# ---------------------------------------------------------------------------
ROLE_CHOICES = {"最高管理者": "super_admin", "一般人員": "staff"}
USER_COLS = [
    Col("name", "姓名", 12, required=True, max_len=50),
    Col("phone", "手機", 14, "phone", required=True, max_len=20),
    Col("role", "身分", 12, "choice", choices=ROLE_CHOICES),
    Col("is_active", "啟用", 8, "bool"),
    *[Col(f"perm:{code}", label, 14, "bool") for code, label in PERMISSIONS.items()],
    Col("password", "新密碼", 14, max_len=72),
]


def _users_export(db: Session, ctx: dict) -> list[dict]:
    rows = []
    for u in db.scalars(select(User).order_by(User.id)):
        perms = {p.permission for p in u.permissions}
        row = {"name": u.name, "phone": u.phone, "role": u.role.value, "is_active": u.is_active, "password": None}
        for code in PERMISSIONS:
            row[f"perm:{code}"] = u.role == UserRole.SUPER_ADMIN or code in perms
        rows.append(row)
    return rows


def _users_apply(db: Session, ctx: dict, rows: Rows, present: list[str], out: ImportOutcome) -> None:
    me: User = ctx["user"]
    users = {u.phone: u for u in db.scalars(select(User))}
    seen: dict[str, int] = {}
    for row_no, v in rows:
        phone = normalize_phone(v["phone"])
        if phone in seen:
            out.error(row_no, f"手機「{phone}」與第 {seen[phone]} 列重複")
            continue
        seen[phone] = row_no
        password = v.get("password")
        if password is not None and (problem := password_problem(password)):
            out.error(row_no, problem)
            continue
        role = UserRole(v["role"]) if v.get("role") else None
        wanted = {code for code in PERMISSIONS if v.get(f"perm:{code}")}
        user = users.get(phone)
        if user is None:
            if not password:
                out.error(row_no, f"新帳號 {phone} 需要填「新密碼」")
                continue
            user = User(name=v["name"], phone=phone, password_hash=hash_password(password), role=role or UserRole.STAFF,
                        is_active=True if v.get("is_active") is None else v["is_active"])
            user.permissions = [UserPermission(permission=c) for c in sorted(wanted)] if user.role == UserRole.STAFF else []
            db.add(user)
            users[phone] = user
            out.created.append(f"{v['name']}（{phone}）")
            continue
        demote = role == UserRole.STAFF and user.role == UserRole.SUPER_ADMIN
        deactivate = v.get("is_active") is False and user.is_active
        if user.id == me.id and (demote or deactivate):
            out.error(row_no, "不能停用或降級自己的帳號")
            continue
        changed = False
        if user.name != v["name"]:
            user.name, changed = v["name"], True
        if role and role != user.role:
            user.role, changed = role, True
        if v.get("is_active") is not None and v["is_active"] != user.is_active:
            user.is_active, changed = v["is_active"], True
        perm_cols_present = any(k.startswith("perm:") for k in present)
        if perm_cols_present and user.role == UserRole.STAFF:
            current = {p.permission for p in user.permissions}
            if current != wanted:
                for p in list(user.permissions):
                    if p.permission not in wanted:
                        user.permissions.remove(p)
                user.permissions.extend(UserPermission(permission=c) for c in sorted(wanted - current))
                changed = True
        if password:
            user.password_hash, changed = hash_password(password), True
        if changed:
            out.updated.append(f"{user.name}（{phone}）")
        else:
            out.unchanged += 1
    db.flush()
    active_admins = db.scalar(select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN, User.is_active.is_(True)))
    if not active_admins:
        out.error(0, "至少要保留一位啟用中的最高管理者")


USERS = Dataset(
    name="users", sheet="人員", columns=USER_COLS, scope="global",
    instructions=[
        "・以「手機」比對：已存在的帳號更新姓名、身分、啟用與權限；不存在的會新增（新帳號必須填「新密碼」，至少 8 碼且含英文字母與數字）。",
        "・權限欄位填「是」或「否」；最高管理者擁有全部權限。",
        "・「新密碼」留空代表不修改；填了會重設密碼，該人員需要重新登入。匯出檔不含密碼。",
    ],
    export_rows=_users_export, apply=_users_apply, export_permission="user.manage", import_permission="user.manage",
)


# ---------------------------------------------------------------------------
# 驗屋 / 健檢結果
# ---------------------------------------------------------------------------
RESULT_CHOICES = {"合格": "pass", "不合格": "fail", "不適用": "na", "未檢查": "pending"}
RESULT_COLS = [
    Col("unit_no", "戶別", 12, required=True),
    Col("date", "預約日期", 12, "date", export_only=True),
    Col("category", "類別", 12, required=True),
    Col("item", "項目", 16, required=True),
    Col("point", "檢查點", 16, required=True),
    Col("result", "結果", 10, "choice", choices=RESULT_CHOICES),
    Col("note", "備註", 30, max_len=1000),
    Col("status", "狀態", 10, export_only=True),
]
INSPECTION_STATUS_TEXT = {"not_started": "未開始", "in_progress": "驗屋中", "signed": "已簽名", "approved": "已確認", "sent": "已寄出"}


def _booking_points(db: Session, booking: Booking):
    from app.routers.inspections import _checklist, _results  # 共用驗屋畫面的清單規則

    results = _results(db, booking.id)
    for cat, items in _checklist(db, booking, results):
        for item, points in items:
            for p in points:
                yield cat, item, p, results.get(p.id)


def _results_export(db: Session, ctx: dict) -> list[dict]:
    batch = ctx["batch"]
    rows = []
    bookings = db.scalars(
        select(Booking).join(Unit, Booking.unit_id == Unit.id)
        .where(Booking.batch_id == batch.id, Booking.status.in_(ACTIVE_STATUSES)).order_by(Unit.unit_no)
    )
    for b in bookings:
        inspection = db.scalar(select(Inspection).where(Inspection.booking_id == b.id))
        status = INSPECTION_STATUS_TEXT[inspection.status.value if inspection else "not_started"]
        for cat, item, p, r in _booking_points(db, b):
            rows.append({
                "unit_no": b.unit.unit_no, "date": b.slot.slot_date, "category": cat.name, "item": item.name, "point": p.name,
                "result": r.result.value if r and r.result != CheckResult.PENDING else None, "note": r.note if r else None,
                "status": status,
            })
    return rows


def _results_apply(db: Session, ctx: dict, rows: Rows, present: list[str], out: ImportOutcome) -> None:
    batch, user = ctx["batch"], ctx["user"]
    bookings = {
        b.unit.unit_no: b for b in db.scalars(select(Booking).where(Booking.batch_id == batch.id, Booking.status.in_(ACTIVE_STATUSES)))
    }
    point_cache: dict[int, dict] = {}
    for row_no, v in rows:
        booking = bookings.get(v["unit_no"])
        if booking is None:
            out.error(row_no, f"戶別「{v['unit_no']}」在這組日期沒有預約")
            continue
        if v.get("result") is None and v.get("note") is None:
            out.unchanged += 1
            continue
        if booking.id not in point_cache:
            point_cache[booking.id] = {(c.name, i.name, p.name): (p, r) for c, i, p, r in _booking_points(db, booking)}
        key = (v["category"], v["item"], v["point"])
        match = point_cache[booking.id].get(key)
        if match is None:
            out.error(row_no, f"清單中沒有「{v['category']}／{v['item']}／{v['point']}」")
            continue
        point, result = match
        old_result = result.result if result else CheckResult.PENDING
        old_note = result.note if result else None
        new_result = CheckResult(v["result"]) if v.get("result") else old_result
        new_note = v.get("note") if "note" in present else old_note
        if new_result == old_result and new_note == old_note:
            out.unchanged += 1  # 匯出後原封不動匯回（包含已簽名的戶別）不算錯誤
            continue
        inspection = db.scalar(select(Inspection).where(Inspection.booking_id == booking.id))
        if inspection and inspection.status != InspectionStatus.IN_PROGRESS:
            out.error(row_no, f"{v['unit_no']} 屋主已簽名，結果已鎖定，不能匯入修改")
            continue
        if inspection is None:
            db.add(Inspection(booking_id=booking.id, inspector_id=user.id))
            db.flush()
        label = f"{v['unit_no']} {v['category']}／{v['item']}／{v['point']}"
        if result is None:
            result = InspectionResult(booking_id=booking.id, check_point_id=point.id)
            db.add(result)
            point_cache[booking.id][key] = (point, result)
            out.created.append(label)
        else:
            out.updated.append(label)
        result.result, result.note = new_result, new_note
        result.inspected_by, result.inspected_at = user.id, datetime.now()


RESULTS = Dataset(
    name="results", sheet="檢查結果", columns=RESULT_COLS, scope="batch",
    instructions=[
        "・每列一個檢查點；以「戶別＋類別＋項目＋檢查點」比對。結果填：合格、不合格、不適用（或未檢查）。",
        "・只能匯入「屋主尚未簽名」的戶別；已簽名的請在 APP 按「重新開啟」後再匯入。",
        "・結果與備註都留空的列不會變動。屋主簽名仍需在 APP 上完成。",
    ],
    export_rows=_results_export, apply=_results_apply,
    export_permission="booking.view", import_permission="inspection.edit",
)

DATASETS = {d.name: d for d in (PROJECTS, CHECKLIST, SLOTS, BOOKINGS, USERS, RESULTS)}
