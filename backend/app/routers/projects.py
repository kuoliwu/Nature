from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Booking, BookingBatch, InspectionCategory, InspectionItem, Project, Unit
from app.schemas import (
    DownloadLinkOut,
    InspectionCategoryOut,
    ProjectIn,
    ProjectOut,
    ProjectUpdate,
    UnitBulkIn,
    UnitBulkItem,
    UnitBulkOut,
    UnitImportOut,
    UnitIn,
    UnitOut,
    UnitUpdate,
)
from app.seed import copy_template_to_project
from app.services.auth import create_download_token, get_current_user, read_download_token, require_permission
from app.services.security import hash_id_number
from app.services.units_excel import ExcelFormatError, export_units, export_units_csv, parse_units_excel

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ExportFormat = Literal["xlsx", "csv"]
MAX_IMPORT_BYTES = 5 * 1024 * 1024

# 登入即可讀取；新增 / 修改需要「建案 / 戶別管理」權限
router = APIRouter(dependencies=[Depends(get_current_user)])
manage = [Depends(require_permission("project.manage"))]


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
    return project


def _get_unit(db: Session, unit_id: int) -> Unit:
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此戶")
    return unit


def _project_out(db: Session, project: Project) -> ProjectOut:
    unit_count = db.scalar(select(func.count(Unit.id)).where(Unit.project_id == project.id))
    batch_count = db.scalar(select(func.count(BookingBatch.id)).where(BookingBatch.project_id == project.id))
    out = ProjectOut.model_validate(project)
    out.unit_count, out.batch_count = unit_count or 0, batch_count or 0
    return out


# ---------------------------------------------------------------------------
# 建案
# ---------------------------------------------------------------------------
@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["建案"], dependencies=manage)
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    project = Project(**body.model_dump())
    db.add(project)
    db.flush()
    copy_template_to_project(db, project)  # 新建案自動帶入公司範本的檢查項目
    db.commit()
    return _project_out(db, project)


@router.get("/projects", response_model=list[ProjectOut], tags=["建案"])
def list_projects(db: Session = Depends(get_db)):
    return [_project_out(db, p) for p in db.scalars(select(Project).order_by(Project.id.desc()))]


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["建案"])
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _project_out(db, get_project_or_404(db, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut, tags=["建案"], dependencies=manage)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "name" and value is None:
            continue
        setattr(project, key, value)
    db.commit()
    return _project_out(db, project)


@router.delete("/projects/{project_id}", status_code=204, tags=["建案"], dependencies=manage)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    has_bookings = db.scalar(
        select(func.count(Booking.id)).join(Unit, Booking.unit_id == Unit.id).where(Unit.project_id == project.id)
    )
    if has_bookings:
        raise HTTPException(status.HTTP_409_CONFLICT, "此建案已有預約紀錄，不能刪除")
    db.delete(project)
    db.commit()


# ---------------------------------------------------------------------------
# 住戶
# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/units", response_model=list[UnitOut], tags=["住戶"])
def list_units(project_id: int, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    return db.scalars(select(Unit).where(Unit.project_id == project_id).order_by(Unit.unit_no)).all()


@router.post("/projects/{project_id}/units", response_model=UnitOut, status_code=201, tags=["住戶"], dependencies=manage)
def create_unit(project_id: int, body: UnitIn, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    unit = Unit(project_id=project_id, **body.model_dump(exclude={"owner_id_number"}))
    if body.owner_id_number:
        unit.owner_id_hash = hash_id_number(body.owner_id_number)
    db.add(unit)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"戶別 {body.unit_no} 已存在")
    return unit


@router.post(
    "/projects/{project_id}/units/bulk", response_model=UnitBulkOut, status_code=201, tags=["住戶"], dependencies=manage
)
def bulk_create_units(project_id: int, body: UnitBulkIn, db: Session = Depends(get_db)):
    """一次新增多戶；已存在或重複的會略過"""
    get_project_or_404(db, project_id)
    items = [UnitBulkItem(unit_no=n, building=body.building) for n in body.unit_nos or []] + (body.units or [])
    if not items:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "沒有要新增的戶別")
    existing = set(db.scalars(select(Unit.unit_no).where(Unit.project_id == project_id)))
    created, skipped = [], []
    for item in items:
        unit_no = item.unit_no.strip()
        if not unit_no:
            continue
        if unit_no in existing:
            skipped.append(unit_no)
            continue
        db.add(Unit(project_id=project_id, unit_no=unit_no, building=item.building, floor=item.floor))
        existing.add(unit_no)
        created.append(unit_no)
    db.commit()
    return UnitBulkOut(created=created, skipped=skipped)


def _export_filename(project: Project, fmt: str) -> str:
    safe = "".join(ch for ch in project.name if ch not in '\\/:*?"<>|')
    return f"住戶_{safe}_{date.today():%Y%m%d}.{fmt}"


def units_export_response(db: Session, project: Project, fmt: str) -> Response:
    units = list(db.scalars(select(Unit).where(Unit.project_id == project.id).order_by(Unit.unit_no)))
    filename = _export_filename(project, fmt)
    content, mime = (export_units(units), XLSX_MIME) if fmt == "xlsx" else (export_units_csv(units), "text/csv; charset=utf-8")
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f"attachment; filename=units.{fmt}; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/projects/{project_id}/units/export", tags=["住戶"], response_class=Response, summary="匯出住戶 Excel / CSV（沒有住戶時即為空白範本）")
def export_units_file(project_id: int, format: ExportFormat = "xlsx", db: Session = Depends(get_db)):
    return units_export_response(db, get_project_or_404(db, project_id), format)


@router.post("/projects/{project_id}/units/export-link", response_model=DownloadLinkOut, tags=["住戶"], summary="產生 5 分鐘有效的下載連結（給手機瀏覽器開啟）")
def export_units_link(project_id: int, request: Request, format: ExportFormat = "xlsx", db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    token, expires = create_download_token({"kind": "units", "project_id": project.id, "fmt": format})
    return DownloadLinkOut(
        url=f"{str(request.base_url).rstrip('/')}/downloads/{token}",
        filename=_export_filename(project, format),
        expires_at=expires,
    )


@router.post("/projects/{project_id}/units/import", response_model=UnitImportOut, tags=["住戶"], dependencies=manage)
async def import_units_excel(
    project_id: int,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="True：只檢查並回報會新增 / 更新哪些戶，不寫入"),
    db: Session = Depends(get_db),
):
    """以戶別比對：已存在的更新、不存在的新增；有任何錯誤時整份不寫入"""
    get_project_or_404(db, project_id)
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "檔案超過 5MB")
    try:
        parsed = parse_units_excel(data)
    except ExcelFormatError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    existing = {u.unit_no: u for u in db.scalars(select(Unit).where(Unit.project_id == project_id))}
    created, updated, unchanged = [], [], 0
    for _, values in parsed.rows:
        unit = existing.get(values["unit_no"])
        if unit is None:
            created.append(values["unit_no"])
            if not dry_run and not parsed.errors:
                db.add(Unit(project_id=project_id, **values))
            continue
        changes = {k: v for k, v in values.items() if getattr(unit, k) != v}
        if not changes:
            unchanged += 1
            continue
        updated.append(values["unit_no"])
        if not dry_run and not parsed.errors:
            for k, v in changes.items():
                setattr(unit, k, v)

    applied = not dry_run and not parsed.errors
    if applied:
        db.commit()
    else:
        db.rollback()
    return UnitImportOut(
        dry_run=not applied,
        created=created,
        updated=updated,
        unchanged=unchanged,
        errors=[{"row": r, "message": m} for r, m in parsed.errors],
    )


@router.get("/units/{unit_id}", response_model=UnitOut, tags=["住戶"])
def get_unit(unit_id: int, db: Session = Depends(get_db)):
    return _get_unit(db, unit_id)


@router.patch("/units/{unit_id}", response_model=UnitOut, tags=["住戶"], dependencies=manage)
def update_unit(unit_id: int, body: UnitUpdate, db: Session = Depends(get_db)):
    unit = _get_unit(db, unit_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "unit_no" and value is None:
            continue
        setattr(unit, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"戶別 {body.unit_no} 已存在")
    return unit


@router.delete("/units/{unit_id}", status_code=204, tags=["住戶"], dependencies=manage)
def delete_unit(unit_id: int, db: Session = Depends(get_db)):
    unit = _get_unit(db, unit_id)
    if db.scalar(select(func.count(Booking.id)).where(Booking.unit_id == unit.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "此戶已有預約紀錄，不能刪除")
    db.delete(unit)
    db.commit()


# ---------------------------------------------------------------------------
# 公司範本（唯讀）；各建案的清單見 routers/checklist.py
# ---------------------------------------------------------------------------
@router.get("/inspection/checklist", response_model=list[InspectionCategoryOut], tags=["檢查項目"])
def get_template_checklist(db: Session = Depends(get_db)):
    return db.scalars(
        select(InspectionCategory)
        .where(InspectionCategory.project_id.is_(None))
        .options(selectinload(InspectionCategory.items).selectinload(InspectionItem.check_points))
        .order_by(InspectionCategory.sort_order)
    ).all()
