"""通用 Excel / CSV 匯出匯入：建案、檢查清單、時段、預約名單、人員、驗屋結果（規則見 services/sheets.py）"""

from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CHECKLIST_SERVICES, PERMISSIONS, BookingBatch, Project, User
from app.schemas import DownloadLinkOut, ImportRowError
from app.services.auth import create_download_token, get_current_user, user_permissions
from app.services.sheet_datasets import DATASETS
from app.services.sheets import Dataset, ImportOutcome, export_csv, export_xlsx, parse
from app.services.units_excel import ExcelFormatError

router = APIRouter(tags=["Excel 匯出匯入"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_IMPORT_BYTES = 5 * 1024 * 1024
SheetName = Literal["projects", "checklist", "slots", "bookings", "users", "results"]
Service = Literal["inspection", "health_check"]


class SheetImportOut(BaseModel):
    dry_run: bool  # True：只檢查、沒有寫入
    created: list[str]
    updated: list[str]
    unchanged: int
    errors: list[ImportRowError]


def _dataset(name: str) -> Dataset:
    ds = DATASETS.get(name)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "沒有這種資料")
    return ds


def _check(user: User, code: str | None) -> None:
    if code and code not in user_permissions(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"沒有「{PERMISSIONS[code]}」權限")


def build_context(db: Session, ds: Dataset, project_id: int | None, service: str | None, batch_id: int | None) -> dict:
    """依資料範圍找出建案 / 批次；回傳給 export_rows / apply 的 ctx"""
    ctx: dict = {}
    if ds.scope == "project_service":
        project = db.get(Project, project_id) if project_id else None
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
        if service not in CHECKLIST_SERVICES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "請指定驗屋或健檢清單")
        ctx.update(project=project, service=service)
    elif ds.scope == "batch":
        batch = db.get(BookingBatch, batch_id) if batch_id else None
        if batch is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到這組預約日期")
        if ds.name == "results" and batch.service_type.value not in CHECKLIST_SERVICES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "參觀沒有檢查結果")
        ctx.update(batch=batch, project=batch.project, service=batch.service_type.value)
    return ctx


def sheet_filename(ds: Dataset, ctx: dict, fmt: str) -> str:
    parts = [ds.sheet]
    if "project" in ctx:
        parts.append(ctx["project"].name)
    if ds.name == "checklist":
        parts.append("驗屋" if ctx["service"] == "inspection" else "健檢")
    if "batch" in ctx:
        parts.append(ctx["batch"].name)
    safe = "_".join("".join(ch for ch in p if ch not in '\\/:*?"<>|') for p in parts)
    return f"{safe}_{date.today():%Y%m%d}.{fmt}"


def sheet_response(db: Session, name: str, ctx_ids: dict, fmt: str) -> Response:
    """下載連結（downloads.py）呼叫：權限已在產生連結時檢查"""
    ds = _dataset(name)
    ctx = build_context(db, ds, ctx_ids.get("project_id"), ctx_ids.get("service"), ctx_ids.get("batch_id"))
    rows = ds.export_rows(db, ctx)
    content, mime = (export_xlsx(ds, rows), XLSX_MIME) if fmt == "xlsx" else (export_csv(ds, rows), "text/csv; charset=utf-8")
    return Response(
        content, media_type=mime,
        headers={"Content-Disposition": f"attachment; filename=data.{fmt}; filename*=UTF-8''{quote(sheet_filename(ds, ctx, fmt))}"},
    )


@router.post("/sheets/{name}/export-link", response_model=DownloadLinkOut, summary="匯出 Excel / CSV 的 5 分鐘下載連結（沒有資料時即為空白範本）")
def sheet_export_link(
    name: SheetName,
    request: Request,
    format: Literal["xlsx", "csv"] = "xlsx",
    project_id: int | None = None,
    service: Service | None = None,
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = _dataset(name)
    _check(user, ds.export_permission)
    ctx = build_context(db, ds, project_id, service, batch_id)
    ids = {"project_id": project_id, "service": service, "batch_id": batch_id}
    token, expires = create_download_token({"kind": "sheet", "name": name, "fmt": format, **ids})
    return DownloadLinkOut(
        url=f"{str(request.base_url).rstrip('/')}/downloads/{token}",
        filename=sheet_filename(ds, ctx, format),
        expires_at=expires,
    )


@router.post("/sheets/{name}/import", response_model=SheetImportOut, summary="匯入 Excel / CSV（先 dry_run 預覽；有任何錯誤整份不寫入）")
async def sheet_import(
    name: SheetName,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="True：只檢查並回報會新增 / 更新哪些資料，不寫入"),
    project_id: int | None = None,
    service: Service | None = None,
    batch_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ds = _dataset(name)
    _check(user, ds.import_permission)
    ctx = build_context(db, ds, project_id, service, batch_id)
    ctx["user"] = user
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "檔案超過 5MB")
    try:
        rows, present, errors = parse(ds, data)
    except ExcelFormatError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    outcome = ImportOutcome(errors=list(errors))
    ds.apply(db, ctx, rows, present, outcome)
    db.flush()
    applied = not dry_run and not outcome.errors
    if applied:
        db.commit()
    else:
        db.rollback()
    return SheetImportOut(
        dry_run=not applied,
        created=outcome.created,
        updated=outcome.updated,
        unchanged=outcome.unchanged,
        errors=[{"row": r, "message": m} for r, m in sorted(outcome.errors)],
    )
