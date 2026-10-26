from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.models import (
    CHECKLIST_SERVICES,
    Booking,
    BookingBatch,
    InspectionCategory,
    InspectionItem,
    Project,
    ProjectOrder,
    ProjectPin,
    ServiceType,
    Unit,
    User,
)
from app.schemas import (
    DownloadLinkOut,
    InspectionCategoryOut,
    ProjectImportOut,
    ProjectOrderIn,
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
from app.services.handbook import ensure_template as ensure_handbook_template
from app.services.dashboard import build_dashboard
from app.services.inspection_media import MediaError, save_image
from app.services.project_backup import BackupError, backup_filename, export_project, import_project
from app.services.timeline import build_timeline
from app.services.project_report import build_html, build_xlsx
from app.services.auth import create_download_token, get_current_user, read_download_token, require_permission
from app.services.security import hash_id_number
from app.services.units_excel import ExcelFormatError, export_units, export_units_csv, parse_units_excel

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ExportFormat = Literal["xlsx", "csv"]
MAX_IMPORT_BYTES = 5 * 1024 * 1024

# 登入即可讀取；新增 / 修改需要「建案 / 戶別管理」權限
router = APIRouter(dependencies=[Depends(get_current_user)])
manage = [Depends(require_permission("project.manage"))]
MAX_BACKUP_BYTES = 500 * 1024 * 1024  # 建案備份檔（含照片）上限


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


COVER_MINUTES = 12 * 60


def cover_path_attr(service: ServiceType) -> str:
    return f"{service.value}_cover_path"


def _project_out(db: Session, project: Project, request: Request) -> ProjectOut:
    unit_count = db.scalar(select(func.count(Unit.id)).where(Unit.project_id == project.id))
    batch_count = db.scalar(select(func.count(BookingBatch.id)).where(BookingBatch.project_id == project.id))
    out = ProjectOut.model_validate(project)
    out.unit_count, out.batch_count = unit_count or 0, batch_count or 0
    rows = db.execute(
        select(BookingBatch.service_type, func.count(BookingBatch.id))
        .where(BookingBatch.project_id == project.id)
        .group_by(BookingBatch.service_type)
    ).all()
    out.batch_counts = {s.value: 0 for s in ServiceType} | {s.value: n for s, n in rows}
    base = str(request.base_url).rstrip("/")
    for s in ServiceType:
        url = None
        if getattr(project, cover_path_attr(s)):
            token, _ = create_download_token({"kind": "project_cover", "project_id": project.id, "service": s.value}, minutes=COVER_MINUTES)
            url = f"{base}/downloads/{token}"
        out.covers[s.value] = url
    return out


# ---------------------------------------------------------------------------
# 建案
# ---------------------------------------------------------------------------
@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["建案"], dependencies=manage)
def create_project(body: ProjectIn, request: Request, db: Session = Depends(get_db)):
    project = Project(**body.model_dump())
    db.add(project)
    db.flush()
    for service in CHECKLIST_SERVICES:  # 驗屋、健檢各一份，從公司範本複製
        copy_template_to_project(db, project, service)
    ensure_handbook_template(db, project)  # 步驟 5 住屋手冊的欄位範本
    db.commit()
    return _project_out(db, project, request)


@router.get("/projects", response_model=list[ProjectOut], tags=["建案"])
def list_projects(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    自己的排序：釘選的在最前面，其餘在後；各群組內依自己拖曳排出的順序，
    沒排過的（例如新建案）排在該群組最前面，再依釘選時間、建立時間新到舊。
    """
    pins = dict(db.execute(select(ProjectPin.project_id, ProjectPin.pinned_at).where(ProjectPin.user_id == user.id)).all())
    order = dict(db.execute(select(ProjectOrder.project_id, ProjectOrder.position).where(ProjectOrder.user_id == user.id)).all())
    projects = sorted(
        db.scalars(select(Project).order_by(Project.id.desc())),
        key=lambda p: (p.id not in pins, order.get(p.id, -1), -pins[p.id].timestamp() if p.id in pins else 0),
    )
    out = []
    for p in projects:
        item = _project_out(db, p, request)
        item.pinned = p.id in pins
        out.append(item)
    return out


@router.put("/projects/order", status_code=204, tags=["建案"], summary="儲存自己的建案順序（長按拖曳排序）")
def save_project_order(body: ProjectOrderIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = {o.project_id: o for o in db.scalars(select(ProjectOrder).where(ProjectOrder.user_id == user.id))}
    valid = set(db.scalars(select(Project.id).where(Project.id.in_(body.project_ids))))
    for position, project_id in enumerate(pid for pid in body.project_ids if pid in valid):
        if project_id in existing:
            existing[project_id].position = position
        else:
            db.add(ProjectOrder(user_id=user.id, project_id=project_id, position=position))
    db.commit()


@router.put("/projects/{project_id}/pin", status_code=204, tags=["建案"], summary="釘選建案（只影響自己的列表）")
def pin_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_project_or_404(db, project_id)
    if not db.scalar(select(ProjectPin).where(ProjectPin.user_id == user.id, ProjectPin.project_id == project_id)):
        db.add(ProjectPin(user_id=user.id, project_id=project_id))
        _clear_order(db, user, project_id)
        db.commit()


@router.delete("/projects/{project_id}/pin", status_code=204, tags=["建案"], summary="取消釘選")
def unpin_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pin = db.scalar(select(ProjectPin).where(ProjectPin.user_id == user.id, ProjectPin.project_id == project_id))
    if pin:
        db.delete(pin)
        _clear_order(db, user, project_id)
        db.commit()


def _clear_order(db: Session, user: User, project_id: int) -> None:
    """換到另一群（釘選／未釘選）時清掉自己排的位置 → 排在新群組最上面，之後可再拖曳調整"""
    db.execute(delete(ProjectOrder).where(ProjectOrder.user_id == user.id, ProjectOrder.project_id == project_id))


# 要放在 /projects/{project_id} 之前，否則 timeline 會被當成建案編號
@router.get("/projects/timeline", tags=["建案"], summary="全部建案的售服時間軸（七個步驟走到哪裡）")
def projects_timeline(db: Session = Depends(get_db)) -> list[dict]:
    return [build_timeline(db, p) for p in db.scalars(select(Project).order_by(Project.id.desc()))]


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["建案"])
def get_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    return _project_out(db, get_project_or_404(db, project_id), request)


@router.get("/projects/{project_id}/timeline", tags=["建案"], summary="建案的售服時間軸")
def project_timeline(project_id: int, db: Session = Depends(get_db)) -> dict:
    return build_timeline(db, get_project_or_404(db, project_id))


@router.post("/projects/{project_id}/covers/{service}", response_model=ProjectOut, tags=["建案"], dependencies=manage,
             summary="上傳屋主預約頁封面照片（驗屋＝預售屋照片、健檢＝成屋照片、參觀選填）")
async def upload_cover(project_id: int, service: ServiceType, request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    try:
        rel, _, _ = save_image(await file.read(), Path("projects") / str(project.id))
    except MediaError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    _remove_cover(project, service)
    setattr(project, cover_path_attr(service), rel)
    db.commit()
    return _project_out(db, project, request)


@router.delete("/projects/{project_id}/covers/{service}", response_model=ProjectOut, tags=["建案"], dependencies=manage)
def delete_cover(project_id: int, service: ServiceType, request: Request, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    _remove_cover(project, service)
    setattr(project, cover_path_attr(service), None)
    db.commit()
    return _project_out(db, project, request)


def _remove_cover(project: Project, service: ServiceType) -> None:
    if old := getattr(project, cover_path_attr(service)):
        (settings.storage_dir / old).unlink(missing_ok=True)


@router.patch("/projects/{project_id}", response_model=ProjectOut, tags=["建案"], dependencies=manage)
def update_project(project_id: int, body: ProjectUpdate, request: Request, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "name" and value is None:
            continue
        setattr(project, key, value)
    db.commit()
    return _project_out(db, project, request)


@router.delete("/projects/{project_id}", status_code=204, tags=["建案"], dependencies=manage)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """刪除建案與底下所有資料（有預約紀錄的也可以刪；APP 會提醒先匯出建案備份，之後可以匯入還原）"""
    project = get_project_or_404(db, project_id)
    # 預約要先刪：預約指向時段的外鍵是 RESTRICT，直接刪建案時時段會先被刪而失敗。
    # 驗屋結果、照片、報告等掛在預約底下的資料由資料庫外鍵 CASCADE 一起刪除。
    batch_ids = select(BookingBatch.id).where(BookingBatch.project_id == project.id)
    db.execute(delete(Booking).where(Booking.batch_id.in_(batch_ids)))
    db.delete(project)
    db.commit()


@router.post("/projects/import", response_model=ProjectImportOut, status_code=201, tags=["建案"], dependencies=manage,
             summary="從建案備份檔（.zip）還原成一個新建案")
async def import_project_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read(MAX_BACKUP_BYTES + 1)
    if len(content) > MAX_BACKUP_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"備份檔不能超過 {MAX_BACKUP_BYTES // 1024 // 1024}MB")
    try:
        project, counts = import_project(db, content)
    except BackupError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return ProjectImportOut(project=_project_out(db, project, request), counts=counts)


@router.post("/projects/{project_id}/backup-link", response_model=DownloadLinkOut, tags=["建案"], dependencies=manage,
             summary="匯出建案備份檔（資料＋照片等檔案，.zip）的 5 分鐘下載連結")
def project_backup_link(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    token, expires = create_download_token({"kind": "project_backup", "project_id": project.id})
    return DownloadLinkOut(
        url=f"{str(request.base_url).rstrip('/')}/downloads/{token}", filename=backup_filename(project), expires_at=expires,
    )


def project_backup_response(db: Session, project: Project) -> Response:
    return Response(
        export_project(db, project), media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=backup.zip; filename*=UTF-8''{quote(backup_filename(project))}"},
    )


@router.get("/projects/{project_id}/dashboard", tags=["建案"], summary="建案儀表板：各階段進度、每日預約、檢查結果")
def project_dashboard(project_id: int, db: Session = Depends(get_db)) -> dict:
    return build_dashboard(db, get_project_or_404(db, project_id))


def project_report_filename(project: Project, fmt: str) -> str:
    safe = "".join(ch for ch in project.name if ch not in '\\/:*?"<>|')
    return f"建案報表_{safe}_{date.today():%Y%m%d}.{fmt}"


def project_report_response(db: Session, project: Project, fmt: str) -> Response:
    data = build_dashboard(db, project)
    content, mime = (build_html(data), "text/html; charset=utf-8") if fmt == "html" else (build_xlsx(data), XLSX_MIME)
    filename = project_report_filename(project, fmt)
    # 互動網頁用 inline：手機瀏覽器直接顯示（attachment 在 iPhone 只會跳出下載詢問）；仍可從瀏覽器儲存
    disposition = "inline" if fmt == "html" else "attachment"
    return Response(
        content, media_type=mime,
        headers={"Content-Disposition": f"{disposition}; filename=report.{fmt}; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/projects/{project_id}/report-export-link", response_model=DownloadLinkOut, tags=["建案"],
             summary="匯出建案報表（互動網頁 html / Excel xlsx）的 5 分鐘下載連結")
def project_report_link(project_id: int, request: Request, format: Literal["html", "xlsx"] = "html", db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    token, expires = create_download_token({"kind": "project_report", "project_id": project.id, "fmt": format})
    return DownloadLinkOut(
        url=f"{str(request.base_url).rstrip('/')}/downloads/{token}",
        filename=project_report_filename(project, format),
        expires_at=expires,
    )


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
