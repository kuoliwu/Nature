"""住屋手冊（售服步驟 5）：範本、逐戶填寫、外部 PDF、預覽 → Review OK → 寄送"""

import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    HandbookAttachment,
    HandbookEntry,
    HandbookField,
    HandbookPhoto,
    HandbookSection,
    HandbookStatus,
    HandbookValue,
    Project,
    Unit,
    UnitHandbook,
    User,
)
from app.schemas import (
    HandbookAttachmentOut,
    HandbookEntryIn,
    HandbookEntryOut,
    HandbookFieldIn,
    HandbookFieldOut,
    HandbookFieldValue,
    HandbookPhotoOut,
    HandbookSectionIn,
    HandbookSectionOut,
    HandbookTemplateOut,
    HandbookUnitRow,
    HandbookValueSection,
    HandbookValuesIn,
    MoveIn,
    ReportLinkOut,
    ReportSendIn,
    UnitHandbookOut,
)
from app.services import handbook as hb
from app.services.auth import create_download_token, require_any_permission, require_permission, user_permissions
from app.services.inspection_media import MediaError, save_image
from app.services.mailer import Attachment, send_email_safely
from app.services.reports import MAX_PDF_BYTES

router = APIRouter(tags=["住屋手冊"])
can_view = require_any_permission("project.manage", "report.manage", "booking.view")
can_template = require_permission("project.manage")
can_edit = require_any_permission("project.manage", "report.manage")
can_report = require_permission("report.manage")

LINK_MINUTES = 12 * 60


# ---------------------------------------------------------------------------
# 共用
# ---------------------------------------------------------------------------
def _project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
    hb.ensure_template(db, project)
    return project


def _unit(db: Session, unit_id: int) -> Unit:
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此戶")
    hb.ensure_template(db, unit.project)
    return unit


def _url(request: Request, kind: str, obj_id: int) -> str:
    token, _ = create_download_token({"kind": kind, "id": obj_id}, minutes=LINK_MINUTES)
    return f"{str(request.base_url).rstrip('/')}/downloads/{token}"


def _attachment_out(request: Request, a: HandbookAttachment) -> HandbookAttachmentOut:
    return HandbookAttachmentOut(
        id=a.id, title=a.title, size=a.file_size, page_count=a.page_count, shared=a.unit_id is None,
        uploaded_at=a.uploaded_at, url=_url(request, "handbook_attachment", a.id),
    )


def _entry_out(db: Session, request: Request, e: HandbookEntry) -> HandbookEntryOut:
    author = db.get(User, e.created_by) if e.created_by else None
    return HandbookEntryOut(
        id=e.id, entry_date=e.entry_date, note=e.note, created_by=author.name if author else None,
        photos=[HandbookPhotoOut(id=p.id, url=_url(request, "handbook_photo", p.id), width=p.width, height=p.height) for p in e.photos],
    )


def _require_draft(handbook: UnitHandbook) -> None:
    if handbook.status != HandbookStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "手冊已確認，請先「取消確認」才能修改")


def _template_out(db: Session, request: Request, project: Project) -> HandbookTemplateOut:
    used = set(db.scalars(
        select(HandbookValue.field_id).join(Unit, Unit.id == HandbookValue.unit_id).where(Unit.project_id == project.id)
    ))
    shared = db.scalars(
        select(HandbookAttachment)
        .where(HandbookAttachment.project_id == project.id, HandbookAttachment.unit_id.is_(None))
        .order_by(HandbookAttachment.sort_order, HandbookAttachment.id)
    )
    return HandbookTemplateOut(
        sections=[
            HandbookSectionOut(
                id=s.id, name=s.name, is_active=s.is_active,
                fields=[
                    HandbookFieldOut(id=f.id, label=f.label, default_value=f.default_value, required=f.required,
                                     is_active=f.is_active, has_values=f.id in used)
                    for f in s.fields
                ],
            )
            for s in hb.sections(db, project.id)
        ],
        attachments=[_attachment_out(request, a) for a in shared],
    )


def _unit_out(db: Session, request: Request, unit: Unit) -> UnitHandbookOut:
    handbook = hb.get_handbook(db, unit)
    values = hb.unit_values(db, unit.id)
    groups = hb.active_fields(db, unit.project_id)
    return UnitHandbookOut(
        unit_id=unit.id, project_id=unit.project_id, unit_no=unit.unit_no,
        owner_name=unit.owner_name, owner_email=unit.owner_email,
        status=handbook.status.value,
        missing=hb.missing_fields(groups, values),
        approved_at=handbook.approved_at,
        approved_by=handbook.approver.name if handbook.approver else None,
        sent_at=handbook.sent_at, sent_to=handbook.sent_to, service_email=settings.service_mailbox,
        sections=[
            HandbookValueSection(
                id=s.id, name=s.name,
                fields=[
                    HandbookFieldValue(field_id=f.id, label=f.label, required=f.required,
                                       default_value=f.default_value, value=values.get(f.id))
                    for f in fields
                ],
            )
            for s, fields in groups if fields
        ],
        attachments=[_attachment_out(request, a) for a in hb.attachments(db, unit)],
        entries=[_entry_out(db, request, e) for e in hb.entries(db, unit.id)],
    )


def _move(items: list, target, direction: str) -> None:
    """在同一組裡上移 / 下移，並把 sort_order 重新編號"""
    i = items.index(target)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
    for n, item in enumerate(items):
        item.sort_order = n


# ---------------------------------------------------------------------------
# 範本（分類、欄位、共用預設值）
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/handbook/template", response_model=HandbookTemplateOut, dependencies=[Depends(can_view)])
def get_template(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    db.commit()
    return _template_out(db, request, project)


@router.post("/projects/{project_id}/handbook/sections", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def add_section(project_id: int, body: HandbookSectionIn, request: Request, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    if not body.name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "請輸入分類名稱")
    count = len(hb.sections(db, project.id))
    db.add(HandbookSection(project_id=project.id, name=body.name.strip(), sort_order=count))
    db.commit()
    return _template_out(db, request, project)


def _section(db: Session, section_id: int) -> HandbookSection:
    section = db.get(HandbookSection, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到分類")
    return section


@router.patch("/handbook/sections/{section_id}", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def update_section(section_id: int, body: HandbookSectionIn, request: Request, db: Session = Depends(get_db)):
    section = _section(db, section_id)
    if body.name is not None:
        section.name = body.name.strip()
    if body.is_active is not None:
        section.is_active = body.is_active
    db.commit()
    return _template_out(db, request, _project(db, section.project_id))


@router.post("/handbook/sections/{section_id}/move", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def move_section(section_id: int, body: MoveIn, request: Request, db: Session = Depends(get_db)):
    section = _section(db, section_id)
    _move(hb.sections(db, section.project_id), section, body.direction)
    db.commit()
    return _template_out(db, request, _project(db, section.project_id))


@router.delete("/handbook/sections/{section_id}", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def delete_section(section_id: int, request: Request, db: Session = Depends(get_db)):
    section = _section(db, section_id)
    field_ids = [f.id for f in section.fields]
    if field_ids and db.scalar(select(func.count(HandbookValue.id)).where(HandbookValue.field_id.in_(field_ids))):
        raise HTTPException(status.HTTP_409_CONFLICT, "此分類已有住戶填寫的內容，不能刪除；可改為停用")
    project_id = section.project_id
    db.delete(section)
    db.commit()
    return _template_out(db, request, _project(db, project_id))


@router.post("/handbook/sections/{section_id}/fields", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def add_field(section_id: int, body: HandbookFieldIn, request: Request, db: Session = Depends(get_db)):
    section = _section(db, section_id)
    if not body.label:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "請輸入欄位名稱")
    section.fields.append(HandbookField(
        label=body.label.strip(), default_value=(body.default_value or "").strip() or None,
        required=body.required if body.required is not None else True, sort_order=len(section.fields),
    ))
    db.commit()
    return _template_out(db, request, _project(db, section.project_id))


def _field(db: Session, field_id: int) -> HandbookField:
    field = db.get(HandbookField, field_id)
    if field is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到欄位")
    return field


@router.patch("/handbook/fields/{field_id}", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def update_field(field_id: int, body: HandbookFieldIn, request: Request, db: Session = Depends(get_db)):
    field = _field(db, field_id)
    sent = body.model_fields_set
    if body.label is not None:
        field.label = body.label.strip()
    if "default_value" in sent:
        field.default_value = (body.default_value or "").strip() or None
    if body.required is not None:
        field.required = body.required
    if body.is_active is not None:
        field.is_active = body.is_active
    db.commit()
    return _template_out(db, request, _project(db, field.section.project_id))


@router.post("/handbook/fields/{field_id}/move", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def move_field(field_id: int, body: MoveIn, request: Request, db: Session = Depends(get_db)):
    field = _field(db, field_id)
    _move(list(field.section.fields), field, body.direction)
    db.commit()
    return _template_out(db, request, _project(db, field.section.project_id))


@router.delete("/handbook/fields/{field_id}", response_model=HandbookTemplateOut, dependencies=[Depends(can_template)])
def delete_field(field_id: int, request: Request, db: Session = Depends(get_db)):
    field = _field(db, field_id)
    if db.scalar(select(func.count(HandbookValue.id)).where(HandbookValue.field_id == field.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "此欄位已有住戶填寫的內容，不能刪除；可改為停用")
    project_id = field.section.project_id
    db.delete(field)
    db.commit()
    return _template_out(db, request, _project(db, project_id))


# ---------------------------------------------------------------------------
# 外部 PDF（建案共用 / 單戶專屬）
# ---------------------------------------------------------------------------
async def _save_pdf(file: UploadFile, title: str | None, project_id: int, unit_id: int | None, user: User, db: Session) -> HandbookAttachment:
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF 不能超過 30MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "只接受 PDF 檔")
    rel = Path("handbooks") / str(project_id) / f"{unit_id or 'shared'}_{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}.pdf"
    path = settings.storage_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        pages = len(PdfReader(path).pages)
    except (PdfReadError, ValueError, KeyError):
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "PDF 檔案損毀或有密碼保護，無法合併")
    name = (file.filename or "附件.pdf").rsplit("/", 1)[-1]
    same_group = select(func.count(HandbookAttachment.id)).where(HandbookAttachment.project_id == project_id)
    same_group = same_group.where(HandbookAttachment.unit_id == unit_id if unit_id else HandbookAttachment.unit_id.is_(None))
    attachment = HandbookAttachment(
        project_id=project_id, unit_id=unit_id,
        title=((title or "").strip() or name.removesuffix(".pdf").removesuffix(".PDF"))[:255],
        file_path=rel.as_posix(), file_size=len(data), page_count=pages,
        sort_order=db.scalar(same_group) or 0, uploaded_by=user.id,
    )
    db.add(attachment)
    db.commit()
    return attachment


@router.post("/projects/{project_id}/handbook/attachments", response_model=HandbookTemplateOut, status_code=201)
async def upload_shared(
    project_id: int, request: Request, file: UploadFile = File(...), title: str | None = Form(None),
    db: Session = Depends(get_db), user: User = Depends(can_template),
):
    project = _project(db, project_id)
    await _save_pdf(file, title, project.id, None, user, db)
    return _template_out(db, request, project)


@router.post("/units/{unit_id}/handbook/attachments", response_model=UnitHandbookOut, status_code=201)
async def upload_unit(
    unit_id: int, request: Request, file: UploadFile = File(...), title: str | None = Form(None),
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    unit = _unit(db, unit_id)
    _require_draft(hb.get_handbook(db, unit))
    await _save_pdf(file, title, unit.project_id, unit.id, user, db)
    return _unit_out(db, request, unit)


def _attachment(db: Session, attachment_id: int, user: User) -> HandbookAttachment:
    a = db.get(HandbookAttachment, attachment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到附件")
    if a.unit_id is None:
        if "project.manage" not in user_permissions(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "沒有權限修改建案共用的 PDF")
    else:
        _require_draft(hb.get_handbook(db, db.get(Unit, a.unit_id)))
    return a


def _attachment_result(db: Session, request: Request, project_id: int, unit_id: int | None):
    if unit_id is None:
        return _template_out(db, request, _project(db, project_id))
    return _unit_out(db, request, _unit(db, unit_id))


@router.post("/handbook/attachments/{attachment_id}/move", response_model=HandbookTemplateOut | UnitHandbookOut)
def move_attachment(attachment_id: int, body: MoveIn, request: Request, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    a = _attachment(db, attachment_id, user)
    group = select(HandbookAttachment).where(HandbookAttachment.project_id == a.project_id)
    group = group.where(HandbookAttachment.unit_id == a.unit_id if a.unit_id else HandbookAttachment.unit_id.is_(None))
    _move(list(db.scalars(group.order_by(HandbookAttachment.sort_order, HandbookAttachment.id))), a, body.direction)
    db.commit()
    return _attachment_result(db, request, a.project_id, a.unit_id)


@router.delete("/handbook/attachments/{attachment_id}", response_model=HandbookTemplateOut | UnitHandbookOut)
def delete_attachment(attachment_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    a = _attachment(db, attachment_id, user)
    project_id, unit_id = a.project_id, a.unit_id
    (settings.storage_dir / a.file_path).unlink(missing_ok=True)
    db.delete(a)
    db.commit()
    return _attachment_result(db, request, project_id, unit_id)


# ---------------------------------------------------------------------------
# 逐戶：列表、填寫、預覽、Review OK、寄送
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/handbooks", response_model=list[HandbookUnitRow], dependencies=[Depends(can_view)])
def list_handbooks(project_id: int, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    db.commit()
    groups = hb.active_fields(db, project.id)
    handbooks = {h.unit_id: h for h in db.scalars(
        select(UnitHandbook).join(Unit, Unit.id == UnitHandbook.unit_id).where(Unit.project_id == project.id)
    )}
    values: dict[int, dict[int, str]] = {}
    for v in db.scalars(select(HandbookValue).join(Unit, Unit.id == HandbookValue.unit_id).where(Unit.project_id == project.id)):
        values.setdefault(v.unit_id, {})[v.field_id] = v.value
    own_files = dict(db.execute(
        select(HandbookAttachment.unit_id, func.count(HandbookAttachment.id))
        .where(HandbookAttachment.project_id == project.id, HandbookAttachment.unit_id.is_not(None))
        .group_by(HandbookAttachment.unit_id)
    ).all())
    # 自然排序：A2、A3…A10（不是 A10 排在 A2 前面）
    entry_counts = dict(db.execute(
        select(HandbookEntry.unit_id, func.count(HandbookEntry.id))
        .join(Unit, Unit.id == HandbookEntry.unit_id).where(Unit.project_id == project.id)
        .group_by(HandbookEntry.unit_id)
    ).all())
    units = sorted(db.scalars(select(Unit).where(Unit.project_id == project.id)),
                   key=lambda u: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", u.unit_no)])
    return [
        HandbookUnitRow(
            unit_id=u.id, unit_no=u.unit_no, owner_name=u.owner_name, owner_email=u.owner_email,
            status=handbooks[u.id].status.value if u.id in handbooks else HandbookStatus.DRAFT.value,
            missing=len(hb.missing_fields(groups, values.get(u.id, {}))),
            attachments=own_files.get(u.id, 0),
            entries=entry_counts.get(u.id, 0),
            sent_at=handbooks[u.id].sent_at if u.id in handbooks else None,
        )
        for u in units
    ]


@router.get("/units/{unit_id}/handbook", response_model=UnitHandbookOut, dependencies=[Depends(can_view)])
def get_unit_handbook(unit_id: int, request: Request, db: Session = Depends(get_db)):
    unit = _unit(db, unit_id)
    out = _unit_out(db, request, unit)
    db.commit()
    return out


@router.put("/units/{unit_id}/handbook/values", response_model=UnitHandbookOut, dependencies=[Depends(can_edit)])
def save_values(unit_id: int, body: HandbookValuesIn, request: Request, db: Session = Depends(get_db)):
    unit = _unit(db, unit_id)
    _require_draft(hb.get_handbook(db, unit))
    fields = {f.id for _, fs in hb.active_fields(db, unit.project_id) for f in fs}
    unknown = set(body.values) - fields
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "欄位已停用或不存在，請重新整理")
    existing = {v.field_id: v for v in db.scalars(select(HandbookValue).where(HandbookValue.unit_id == unit.id))}
    for field_id, value in body.values.items():
        text = (value or "").strip()
        if field_id in existing:
            if text:
                existing[field_id].value = text
            else:
                db.delete(existing[field_id])
        elif text:
            db.add(HandbookValue(unit_id=unit.id, field_id=field_id, value=text))
    db.commit()
    return _unit_out(db, request, unit)


# ---------------------------------------------------------------------------
# 生產履歷紀錄：日期 + 照片 + 選填文字（手冊確認後鎖定）
# ---------------------------------------------------------------------------
def _entry(db: Session, entry_id: int) -> HandbookEntry:
    entry = db.get(HandbookEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到這筆紀錄")
    _require_draft(hb.get_handbook(db, db.get(Unit, entry.unit_id)))
    return entry


@router.post("/units/{unit_id}/handbook/entries", response_model=HandbookEntryOut, status_code=201)
def add_entry(unit_id: int, body: HandbookEntryIn, request: Request, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    unit = _unit(db, unit_id)
    _require_draft(hb.get_handbook(db, unit))
    entry = HandbookEntry(unit_id=unit.id, entry_date=body.entry_date, note=(body.note or "").strip() or None, created_by=user.id)
    db.add(entry)
    db.commit()
    return _entry_out(db, request, entry)


@router.patch("/handbook/entries/{entry_id}", response_model=HandbookEntryOut, dependencies=[Depends(can_edit)])
def update_entry(entry_id: int, body: HandbookEntryIn, request: Request, db: Session = Depends(get_db)):
    entry = _entry(db, entry_id)
    entry.entry_date, entry.note = body.entry_date, (body.note or "").strip() or None
    db.commit()
    return _entry_out(db, request, entry)


@router.delete("/handbook/entries/{entry_id}", status_code=204, dependencies=[Depends(can_edit)])
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = _entry(db, entry_id)
    for photo in entry.photos:
        (settings.storage_dir / photo.file_path).unlink(missing_ok=True)
    db.delete(entry)
    db.commit()


@router.post("/handbook/entries/{entry_id}/photos", response_model=HandbookEntryOut, status_code=201, dependencies=[Depends(can_edit)])
async def add_entry_photo(entry_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    entry = _entry(db, entry_id)
    try:
        rel, w, h = save_image(await file.read(), Path("handbooks") / str(db.get(Unit, entry.unit_id).project_id) / "photos")
    except MediaError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    entry.photos.append(HandbookPhoto(file_path=rel, width=w, height=h))
    db.commit()
    return _entry_out(db, request, entry)


@router.delete("/handbook/photos/{photo_id}", response_model=HandbookEntryOut, dependencies=[Depends(can_edit)])
def delete_entry_photo(photo_id: int, request: Request, db: Session = Depends(get_db)):
    photo = db.get(HandbookPhoto, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "照片已刪除")
    entry = _entry(db, photo.entry_id)
    (settings.storage_dir / photo.file_path).unlink(missing_ok=True)
    entry.photos.remove(photo)
    db.commit()
    return _entry_out(db, request, entry)


@router.post("/units/{unit_id}/handbook/preview-link", response_model=ReportLinkOut, dependencies=[Depends(can_view)])
def preview_link(unit_id: int, request: Request, db: Session = Depends(get_db)):
    unit = _unit(db, unit_id)
    hb.build_pdf(db, unit)  # 先確認能產生（外部 PDF 損毀等），錯誤直接回給 APP
    db.commit()
    return ReportLinkOut(url=_url(request, "handbook", unit.id), filename=hb.filename(unit))


@router.post("/units/{unit_id}/handbook/approve", response_model=UnitHandbookOut)
def approve(unit_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(can_report)):
    unit = _unit(db, unit_id)
    handbook = hb.get_handbook(db, unit)
    if handbook.status != HandbookStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "手冊已確認過")
    missing = hb.missing_fields(hb.active_fields(db, unit.project_id), hb.unit_values(db, unit.id))
    if missing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"還有 {len(missing)} 個必填欄位沒填：{'、'.join(missing[:5])}")
    handbook.status = HandbookStatus.APPROVED
    handbook.approved_at, handbook.approved_by = datetime.now(), user.id
    db.commit()
    return _unit_out(db, request, unit)


@router.post("/units/{unit_id}/handbook/unapprove", response_model=UnitHandbookOut, dependencies=[Depends(can_report)])
def unapprove(unit_id: int, request: Request, db: Session = Depends(get_db)):
    unit = _unit(db, unit_id)
    handbook = hb.get_handbook(db, unit)
    if handbook.status == HandbookStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "手冊尚未確認")
    # 已寄出的也可以取消確認：修改後重新確認、再寄一次新版
    handbook.status = HandbookStatus.DRAFT
    handbook.approved_at = handbook.approved_by = None
    db.commit()
    return _unit_out(db, request, unit)


@router.post("/units/{unit_id}/handbook/send", response_model=UnitHandbookOut, dependencies=[Depends(can_report)])
def send(unit_id: int, body: ReportSendIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    unit = _unit(db, unit_id)
    handbook = hb.get_handbook(db, unit)
    if handbook.status == HandbookStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "請先 Review OK（確認手冊內容）再寄送")
    to = body.to or settings.service_mailbox  # 匯出後寄到售服，由售服整理後再交給屋主
    if not to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "尚未設定售服信箱（MAIL_FROM），請輸入收件人")
    pdf = hb.build_pdf(db, unit)
    if len(pdf) > hb.MAX_EMAIL_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"完整手冊 {len(pdf) / 1024 / 1024:.1f}MB，超過 Email 附件上限 20MB；請壓縮外部 PDF 後再寄送",
        )
    rel = Path("handbooks") / str(unit.project_id) / f"handbook{unit.id}_{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}.pdf"
    (settings.storage_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / rel).write_bytes(pdf)
    handbook.file_path = rel.as_posix()
    handbook.status = HandbookStatus.SENT
    handbook.sent_at, handbook.sent_to = datetime.now(), to
    db.commit()

    project = unit.project
    approver = handbook.approver.name if handbook.approver else ""
    text = "\n".join([
        "售服部 您好：",
        "",
        f"{project.name} {unit.unit_no} 的「{hb.TITLE}」已 Review OK 並匯出，完整 PDF 請見附件。",
        "",
        f"  建案：{project.name}",
        f"  戶別：{unit.unit_no}",
        f"  屋主：{unit.owner_name or '—'}（{unit.owner_email or '未留 Email'}）",
        f"  確認：{approver} {handbook.approved_at:%Y-%m-%d %H:%M}".rstrip(),
        "",
    ])
    tasks.add_task(send_email_safely, [to], f"【手冊匯出】{project.name} {unit.unit_no} {hb.TITLE}", text,
                   [Attachment(hb.filename(unit), pdf)])
    return _unit_out(db, request, unit)
