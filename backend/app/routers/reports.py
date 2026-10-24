"""外部報告上傳（單一 PDF、≤30MB，上傳後自動關閉該戶的上傳開關）、報告追蹤與提醒、手動備份"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Booking, BookingStatus, Report, Unit, User
from app.schemas import BackupRunOut, ExternalReportOut, OverdueOut, ReminderRunOut, UploadSwitchIn
from app.services.auth import create_download_token, require_any_permission, require_permission
from app.services.backup import run_backup
from app.services.reports import MAX_PDF_BYTES, overdue_bookings, run_reminders

router = APIRouter(tags=["報告"])
can_report = require_permission("report.manage")
can_view = require_any_permission("report.manage", "inspection.edit", "booking.view")


def external_report_out(db: Session, request: Request, booking: Booking) -> ExternalReportOut | None:
    report = db.scalar(select(Report).where(Report.booking_id == booking.id))
    if report is None:
        return None
    token, _ = create_download_token({"kind": "external_report", "id": report.id}, minutes=12 * 60)
    uploader = db.get(User, report.uploaded_by) if report.uploaded_by else None
    return ExternalReportOut(
        filename=report.original_filename,
        size=report.file_size,
        uploaded_at=report.uploaded_at,
        uploaded_by=uploader.name if uploader else None,
        url=f"{str(request.base_url).rstrip('/')}/downloads/{token}",
    )


def _booking(db: Session, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到有效的預約")
    return booking


@router.post("/bookings/{booking_id}/report", response_model=ExternalReportOut, status_code=201)
async def upload_external_report(
    booking_id: int, request: Request, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(can_report),
):
    booking = _booking(db, booking_id)
    unit = booking.unit
    existing = db.scalar(select(Report).where(Report.booking_id == booking.id))
    if not unit.report_upload_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "此戶的報告上傳開關已關閉（已上傳過）；如需重新上傳，請先開啟上傳開關")

    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "報告 PDF 不能超過 30MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "只接受 PDF 檔")

    rel = Path("reports") / f"external{booking.id}_{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}.pdf"
    (settings.storage_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / rel).write_bytes(data)
    if existing:  # 重新上傳：取代舊檔
        (settings.storage_dir / existing.file_path).unlink(missing_ok=True)
        db.delete(existing)
        db.flush()
    filename = (file.filename or "report.pdf").rsplit("/", 1)[-1][:255]
    db.add(Report(
        booking_id=booking.id, unit_id=unit.id, file_path=rel.as_posix(),
        original_filename=filename if filename.lower().endswith(".pdf") else f"{filename}.pdf",
        file_size=len(data), uploaded_by=user.id,
    ))
    unit.report_upload_enabled = False  # 上傳成功後自動關閉，避免重複上傳
    db.commit()
    return external_report_out(db, request, booking)


@router.delete("/bookings/{booking_id}/report", status_code=204, dependencies=[Depends(can_report)])
def delete_external_report(booking_id: int, db: Session = Depends(get_db)):
    booking = _booking(db, booking_id)
    report = db.scalar(select(Report).where(Report.booking_id == booking.id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "沒有上傳的報告")
    (settings.storage_dir / report.file_path).unlink(missing_ok=True)
    db.delete(report)
    booking.unit.report_upload_enabled = True
    db.commit()


@router.patch("/units/{unit_id}/report-upload", status_code=204, dependencies=[Depends(can_report)])
def set_upload_switch(unit_id: int, body: UploadSwitchIn, db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此戶")
    unit.report_upload_enabled = body.enabled
    db.commit()


@router.get("/reports/overdue", response_model=list[OverdueOut], dependencies=[Depends(can_view)])
def list_overdue(db: Session = Depends(get_db)):
    """預約日後超過 7 天、報告尚未完成的預約"""
    return [
        OverdueOut(
            booking_id=o.booking.id, project_name=o.booking.unit.project.name, unit_no=o.booking.unit.unit_no,
            date=o.booking.slot.slot_date, start_time=o.booking.slot.start_time, days=o.days,
            inspection_status=o.inspection_status, contact_name=o.booking.contact_name,
            contact_phone=o.booking.contact_phone, reminded=o.reminded,
        )
        for o in sorted(overdue_bookings(db), key=lambda o: -o.days)
    ]


@router.post("/reminders/run", response_model=ReminderRunOut, dependencies=[Depends(can_report)])
def run_reminders_now(db: Session = Depends(get_db)):
    """立即檢查並寄出提醒（平常每天自動執行一次）"""
    return run_reminders(db)


@router.post("/backup/run", response_model=BackupRunOut, dependencies=[Depends(require_permission("user.manage"))])
def run_backup_now():
    return run_backup()
