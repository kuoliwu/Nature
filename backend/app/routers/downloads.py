"""短效下載連結（不需登入 header，憑連結中的 token）。只掛在管理用的 8000，不經過對外通道。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Booking, Inspection, InspectionPhoto, Project, Report, ServiceType
from app.routers.projects import cover_path_attr, project_report_response, units_export_response
from app.services.auth import read_download_token

router = APIRouter(tags=["下載"])


@router.get("/downloads/{token}", include_in_schema=False)
def download(token: str, db: Session = Depends(get_db)):
    payload = read_download_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_410_GONE, "下載連結已過期，請回到 APP 重新匯出")
    if payload.get("kind") == "units":
        project = db.get(Project, payload["project_id"])
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
        return units_export_response(db, project, payload["fmt"])
    if payload.get("kind") == "project_report":
        project = db.get(Project, payload["project_id"])
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
        return project_report_response(db, project, payload["fmt"])
    if payload.get("kind") == "sheet":
        from app.routers.sheets import sheet_response

        return sheet_response(db, payload["name"], payload, payload["fmt"])
    if payload.get("kind") == "project_cover":
        project = db.get(Project, payload["project_id"])
        rel = project and getattr(project, cover_path_attr(ServiceType(payload["service"])))
        if not rel:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "封面照片已刪除")
        return FileResponse(settings.storage_dir / rel, media_type="image/jpeg")
    if payload.get("kind") == "photo":
        photo = db.get(InspectionPhoto, payload["id"])
        if photo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "照片已刪除")
        return FileResponse(settings.storage_dir / photo.file_path, media_type="image/jpeg")
    if payload.get("kind") == "inspection_signature":
        inspection = db.scalar(select(Inspection).where(Inspection.booking_id == payload["id"]))
        if inspection is None or not inspection.signature_path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "沒有簽名")
        return FileResponse(settings.storage_dir / inspection.signature_path, media_type="image/png")
    if payload.get("kind") == "external_report":
        report = db.get(Report, payload["id"])
        if report is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "報告已刪除")
        return FileResponse(
            settings.storage_dir / report.file_path, media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=report.pdf; filename*=UTF-8''{quote(report.original_filename)}"},
        )
    if payload.get("kind") == "inspection_report":
        from app.routers.inspections import build_inspection_report, report_filename  # 避免循環匯入

        booking = db.get(Booking, payload["id"])
        if booking is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到預約")
        filename = report_filename(booking)
        return Response(
            build_inspection_report(db, booking),
            media_type="application/pdf",
            # inline：瀏覽器直接預覽，不強制下載
            headers={"Content-Disposition": f"inline; filename=report.pdf; filename*=UTF-8''{quote(filename)}"},
        )
    raise HTTPException(status.HTTP_404_NOT_FOUND, "連結無效")
