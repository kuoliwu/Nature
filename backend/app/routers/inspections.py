"""第三、四階段：驗屋與報告。

驗屋中 →（屋主簽名）已簽名 →（Review OK）已確認 →（寄送）報告已寄出
  - 簽名後檢查結果鎖定、預約標記完成；確認前可「重新開啟」（清除簽名）
  - 簽名後隨時可預覽報告 PDF；確認後才能寄送，寄送會附上 PDF 與感謝信
"""

import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    CHECKLIST_SERVICES,
    Booking,
    BookingStatus,
    CheckResult,
    Inspection,
    InspectionCheckPoint,
    InspectionPhoto,
    InspectionResult,
    InspectionStatus,
    Report,
    TimeSlot,
    User,
)
from app.schemas import (
    InspectionCategoryBlock,
    InspectionItemOut,
    InspectionNoteIn,
    InspectionOut,
    InspectionPhotoOut,
    InspectionPointOut,
    ReportLinkOut,
    ReportSendIn,
    ResultIn,
    ScheduleItem,
    SignIn,
)
from app.seed import ensure_project_checklist
from app.services.auth import create_download_token, require_any_permission, require_permission
from app.services.booking import SERVICE_LABEL, slot_label
from app.services.inspection_media import MediaError, render_signature, save_photo, save_signature_png
from app.services.mailer import Attachment, send_email_safely
from app.services.report_pdf import ReportData, ReportPhoto, ReportPoint, build_report


def external_report_out(db, request, booking):  # 延遲匯入，避免 routers 之間循環匯入
    from app.routers.reports import external_report_out as impl

    return impl(db, request, booking)

router = APIRouter(tags=["驗屋"])
can_view = require_any_permission("inspection.edit", "booking.view")
can_edit = require_permission("inspection.edit")
can_report = require_permission("report.manage")

MEDIA_MINUTES = 12 * 60  # 照片網址有效時間；APP 每次載入都會拿到新的


# ---------------------------------------------------------------------------
# 共用
# ---------------------------------------------------------------------------
def _media_url(request: Request, kind: str, obj_id: int) -> str:
    token, _ = create_download_token({"kind": kind, "id": obj_id}, minutes=MEDIA_MINUTES)
    return f"{str(request.base_url).rstrip('/')}/downloads/{token}"


def _get_booking(db: Session, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.status not in (BookingStatus.BOOKED, BookingStatus.COMPLETED):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到有效的預約")
    return booking


def _inspection(db: Session, booking: Booking) -> Inspection | None:
    return db.scalar(select(Inspection).where(Inspection.booking_id == booking.id))


def _service(booking: Booking) -> str:
    return booking.slot.batch.service_type.value


def _editable_inspection(db: Session, booking: Booking, user: User) -> Inspection:
    """取得可編輯的驗屋紀錄；第一次編輯時建立"""
    if _service(booking) not in CHECKLIST_SERVICES:
        raise HTTPException(status.HTTP_409_CONFLICT, "參觀預約沒有檢查項目，請使用「報到」")
    inspection = _inspection(db, booking)
    if inspection is None:
        inspection = Inspection(booking_id=booking.id, inspector_id=user.id)
        db.add(inspection)
        db.flush()
    elif inspection.status != InspectionStatus.IN_PROGRESS:
        raise HTTPException(status.HTTP_409_CONFLICT, "屋主已簽名，檢查結果已鎖定；如需修改請先「重新開啟」")
    return inspection


def _status(booking: Booking, inspection: Inspection | None) -> str:
    """參觀：not_started / checked_in；驗屋、健檢：驗屋紀錄的狀態"""
    if _service(booking) not in CHECKLIST_SERVICES:
        return "checked_in" if booking.checked_in_at else "not_started"
    return inspection.status.value if inspection else "not_started"


def _place(booking: Booking) -> str:
    unit, project = booking.unit, booking.unit.project
    return unit.address or project.address or project.community_address or ""


def _checklist(db: Session, booking: Booking, results: dict[int, InspectionResult]):
    """
    此預約服務（驗屋 / 健檢）目前啟用的檢查項目。
    已停用、或屬於另一份清單但這筆預約已有結果的檢查點也保留，避免紀錄消失。參觀沒有檢查項目。
    """
    service = _service(booking)
    if service not in CHECKLIST_SERVICES:
        return
    project = booking.unit.project
    ensure_project_checklist(db, project, service)
    for cat in sorted(project.checklist, key=lambda c: (c.service_type != service, c.sort_order)):
        current = cat.service_type == service
        items = []
        for item in cat.items:
            points = [p for p in item.check_points if (current and p.is_active and item.is_active and cat.is_active) or p.id in results]
            if points:
                items.append((item, points))
        if items:
            yield cat, items


def _counts(points: list[InspectionCheckPoint], results: dict[int, InspectionResult]) -> tuple[int, int, int]:
    checked = sum(1 for p in points if p.id in results and results[p.id].result != CheckResult.PENDING)
    fails = sum(1 for p in points if p.id in results and results[p.id].result == CheckResult.FAIL)
    return checked, len(points), fails


def _results(db: Session, booking_id: int) -> dict[int, InspectionResult]:
    return {r.check_point_id: r for r in db.scalars(select(InspectionResult).where(InspectionResult.booking_id == booking_id))}


def _photo_out(request: Request, p: InspectionPhoto) -> InspectionPhotoOut:
    return InspectionPhotoOut(id=p.id, check_point_id=p.check_point_id, url=_media_url(request, "photo", p.id), caption=p.caption)


def _inspection_out(db: Session, request: Request, booking: Booking) -> InspectionOut:
    inspection = _inspection(db, booking)
    results = _results(db, booking.id)
    photos = list(db.scalars(select(InspectionPhoto).where(InspectionPhoto.booking_id == booking.id).order_by(InspectionPhoto.id)))
    by_point: dict[int | None, list[InspectionPhotoOut]] = {}
    for p in photos:
        by_point.setdefault(p.check_point_id, []).append(_photo_out(request, p))

    blocks, all_points = [], []
    for cat, items in _checklist(db, booking, results):
        item_blocks = []
        for item, points in items:
            all_points += points
            item_blocks.append(InspectionItemOut(id=item.id, name=item.name, points=[
                InspectionPointOut(
                    id=p.id,
                    name=p.name,
                    result=results[p.id].result.value if p.id in results else "pending",
                    note=results[p.id].note if p.id in results else None,
                    photos=by_point.get(p.id, []),
                )
                for p in points
            ]))
        blocks.append(InspectionCategoryBlock(id=cat.id, name=cat.name, items=item_blocks))

    checked, total, fails = _counts(all_points, results)
    slot = booking.slot
    return InspectionOut(
        booking_id=booking.id,
        unit_id=booking.unit_id,
        project_name=booking.unit.project.name,
        unit_no=booking.unit.unit_no,
        place=_place(booking),
        date=slot.slot_date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        contact_name=booking.contact_name,
        contact_phone=booking.contact_phone,
        status=_status(booking, inspection),
        service_type=_service(booking),
        checked_in_at=booking.checked_in_at,
        general_note=inspection.general_note if inspection else None,
        inspector_name=inspection.inspector.name if inspection and inspection.inspector else None,
        signer_name=inspection.signer_name if inspection else None,
        signed_at=inspection.signed_at if inspection else None,
        signature_url=_media_url(request, "inspection_signature", booking.id) if inspection and inspection.signature_path else None,
        approved_at=inspection.approved_at if inspection else None,
        approver_name=inspection.approver.name if inspection and inspection.approver else None,
        sent_at=inspection.sent_at if inspection else None,
        sent_to=inspection.sent_to if inspection else None,
        default_email=booking.contact_email or booking.unit.owner_email,
        external_report=external_report_out(db, request, booking),
        upload_enabled=booking.unit.report_upload_enabled,
        checked=checked,
        total=total,
        fail_count=fails,
        categories=blocks,
        general_photos=by_point.get(None, []),
    )


# ---------------------------------------------------------------------------
# 行程
# ---------------------------------------------------------------------------
@router.get("/inspections/schedule", response_model=list[ScheduleItem])
def schedule(day: date, db: Session = Depends(get_db), _: User = Depends(can_view)):
    """某一天所有建案的預約（依時間排序）"""
    bookings = db.scalars(
        select(Booking)
        .join(TimeSlot, Booking.slot_id == TimeSlot.id)
        .where(TimeSlot.slot_date == day, Booking.status.in_((BookingStatus.BOOKED, BookingStatus.COMPLETED)))
        .order_by(TimeSlot.start_time, Booking.id)
    )
    out = []
    for b in bookings:
        inspection = _inspection(db, b)
        results = _results(db, b.id)
        points = [p for _, items in _checklist(db, b, results) for _, ps in items for p in ps]
        checked, total, fails = _counts(points, results)
        out.append(ScheduleItem(
            booking_id=b.id, project_id=b.unit.project_id, project_name=b.unit.project.name, unit_no=b.unit.unit_no,
            place=_place(b), date=b.slot.slot_date, start_time=b.slot.start_time, end_time=b.slot.end_time,
            contact_name=b.contact_name, contact_phone=b.contact_phone,
            status=_status(b, inspection),
            checked=checked, total=total, fail_count=fails,
            service_type=_service(b), checked_in_at=b.checked_in_at,
        ))
    return out


# ---------------------------------------------------------------------------
# 驗屋紀錄
# ---------------------------------------------------------------------------
@router.get("/inspections/{booking_id}", response_model=InspectionOut)
def get_inspection(booking_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(can_view)):
    return _inspection_out(db, request, _get_booking(db, booking_id))


@router.put("/inspections/{booking_id}/results/{point_id}", response_model=InspectionPointOut)
def set_result(
    booking_id: int, point_id: int, body: ResultIn, request: Request,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    booking = _get_booking(db, booking_id)
    point = db.get(InspectionCheckPoint, point_id)
    if point is None or point.item.category.project_id != booking.unit.project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "此檢查點不屬於這個建案")
    _editable_inspection(db, booking, user)
    if point.item.category.service_type != _service(booking) and point.id not in _results(db, booking.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "此檢查點不屬於這份檢查清單")

    result = db.scalar(select(InspectionResult).where(
        InspectionResult.booking_id == booking.id, InspectionResult.check_point_id == point.id
    ))
    if result is None:
        result = InspectionResult(booking_id=booking.id, check_point_id=point.id)
        db.add(result)
    fields = body.model_dump(exclude_unset=True)
    if "result" in fields and fields["result"] is not None:
        result.result = CheckResult(fields["result"])
    if "note" in fields:
        result.note = (fields["note"] or "").strip() or None
    result.inspected_by, result.inspected_at = user.id, datetime.now()
    db.commit()

    photos = db.scalars(select(InspectionPhoto).where(
        InspectionPhoto.booking_id == booking.id, InspectionPhoto.check_point_id == point.id
    ).order_by(InspectionPhoto.id))
    return InspectionPointOut(
        id=point.id, name=point.name, result=result.result.value, note=result.note,
        photos=[_photo_out(request, p) for p in photos],
    )


@router.patch("/inspections/{booking_id}", response_model=InspectionOut)
def update_note(
    booking_id: int, body: InspectionNoteIn, request: Request,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    booking = _get_booking(db, booking_id)
    inspection = _editable_inspection(db, booking, user)
    inspection.general_note = (body.general_note or "").strip() or None
    db.commit()
    return _inspection_out(db, request, booking)


@router.post("/inspections/{booking_id}/photos", response_model=InspectionPhotoOut, status_code=201)
async def upload_photo(
    booking_id: int,
    request: Request,
    file: UploadFile = File(...),
    check_point_id: int | None = Form(None),
    caption: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(can_edit),
):
    booking = _get_booking(db, booking_id)
    if check_point_id is not None:
        point = db.get(InspectionCheckPoint, check_point_id)
        if point is None or point.item.category.project_id != booking.unit.project_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "此檢查點不屬於這個建案")
    _editable_inspection(db, booking, user)
    try:
        rel, w, h = save_photo(await file.read(), booking.id)
    except MediaError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    photo = InspectionPhoto(
        booking_id=booking.id, check_point_id=check_point_id, file_path=rel, width=w, height=h,
        caption=(caption or "").strip()[:200] or None, taken_by=user.id,
    )
    db.add(photo)
    db.commit()
    return _photo_out(request, photo)


@router.delete("/inspection-photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    photo = db.get(InspectionPhoto, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到照片")
    _editable_inspection(db, _get_booking(db, photo.booking_id), user)
    (settings.storage_dir / photo.file_path).unlink(missing_ok=True)
    db.delete(photo)
    db.commit()


@router.post("/inspections/{booking_id}/sign", response_model=InspectionOut)
def sign(booking_id: int, body: SignIn, request: Request, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    """屋主在 APP 上簽名：檢查結果鎖定、預約標記完成"""
    booking = _get_booking(db, booking_id)
    inspection = _editable_inspection(db, booking, user)
    results = _results(db, booking.id)
    points = [p for _, items in _checklist(db, booking, results) for _, ps in items for p in ps]
    checked, total, _ = _counts(points, results)
    if checked < total:
        raise HTTPException(status.HTTP_409_CONFLICT, f"還有 {total - checked} 個檢查點未填寫，請全部填寫後再請屋主簽名")
    try:
        png = render_signature(body.strokes, body.width, body.height)
    except MediaError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    inspection.signature_path = save_signature_png(png, booking.id)
    inspection.signer_name = body.signer_name.strip()
    inspection.signed_at = datetime.now()
    inspection.status = InspectionStatus.SIGNED
    booking.status = BookingStatus.COMPLETED
    db.commit()
    return _inspection_out(db, request, booking)


@router.post("/inspections/{booking_id}/reopen", response_model=InspectionOut)
def reopen(booking_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(can_edit)):
    """簽名後發現要修改：重新開啟（清除簽名，需要屋主重簽）。報告已確認或寄出後不能重開。"""
    booking = _get_booking(db, booking_id)
    inspection = _inspection(db, booking)
    if inspection is None or inspection.status == InspectionStatus.IN_PROGRESS:
        raise HTTPException(status.HTTP_409_CONFLICT, "此驗屋紀錄尚未簽名")
    if inspection.status != InspectionStatus.SIGNED:
        raise HTTPException(status.HTTP_409_CONFLICT, "報告已確認或寄出，不能重新開啟")
    if inspection.signature_path:
        (settings.storage_dir / inspection.signature_path).unlink(missing_ok=True)
    inspection.status = InspectionStatus.IN_PROGRESS
    inspection.signature_path = inspection.signer_name = inspection.signed_at = None
    booking.status = BookingStatus.BOOKED
    db.commit()
    return _inspection_out(db, request, booking)



# ---------------------------------------------------------------------------
# 報告：預覽 PDF、Review OK、寄送
# ---------------------------------------------------------------------------
def report_title(booking: Booking) -> str:
    return f"{SERVICE_LABEL[booking.slot.batch.service_type]}報告"


def report_filename(booking: Booking) -> str:
    unit = booking.unit
    name = f"{report_title(booking)}_{unit.project.name}_{unit.unit_no}_{booking.slot.slot_date:%Y%m%d}.pdf"
    return "".join(ch for ch in name if ch not in '\\/:*?"<>|')


def build_inspection_report(db: Session, booking: Booking) -> bytes:
    inspection = _inspection(db, booking)
    if inspection is None or inspection.status == InspectionStatus.IN_PROGRESS:
        raise HTTPException(status.HTTP_409_CONFLICT, "屋主簽名後才能產生報告")
    results = _results(db, booking.id)
    photos: dict[int | None, list[ReportPhoto]] = {}
    for ph in db.scalars(select(InspectionPhoto).where(InspectionPhoto.booking_id == booking.id).order_by(InspectionPhoto.id)):
        photos.setdefault(ph.check_point_id, []).append(
            ReportPhoto(path=settings.storage_dir / ph.file_path, width=ph.width, height=ph.height, caption=ph.caption)
        )
    points = [
        ReportPoint(
            category=cat.name, item=item.name, name=p.name,
            result=results[p.id].result.value if p.id in results else "pending",
            note=results[p.id].note if p.id in results else None,
            photos=photos.get(p.id, []),
        )
        for cat, items in _checklist(db, booking, results) for item, ps in items for p in ps
    ]
    approved = None
    if inspection.approved_at:
        who = inspection.approver.name if inspection.approver else ""
        approved = f"{who} {inspection.approved_at:%Y-%m-%d %H:%M}".strip()
    return build_report(ReportData(
        title=report_title(booking),
        project_name=booking.unit.project.name,
        unit_no=booking.unit.unit_no,
        place=_place(booking),
        when=slot_label(booking.slot),
        contact=f"{booking.contact_name} {booking.contact_phone}",
        inspector=inspection.inspector.name if inspection.inspector else "",
        points=points,
        general_note=inspection.general_note,
        general_photos=photos.get(None, []),
        signer_name=inspection.signer_name,
        signed_at=inspection.signed_at,
        signature_path=settings.storage_dir / inspection.signature_path if inspection.signature_path else None,
        approved=approved,
    ))


@router.post("/inspections/{booking_id}/report-link", response_model=ReportLinkOut)
def report_link(booking_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(can_view)):
    """預覽報告：回傳 12 小時內有效的下載連結（在瀏覽器開啟）"""
    booking = _get_booking(db, booking_id)
    build_inspection_report(db, booking)  # 先確認能產生，錯誤直接回給 APP
    return ReportLinkOut(url=_media_url(request, "inspection_report", booking.id), filename=report_filename(booking))


@router.post("/inspections/{booking_id}/approve", response_model=InspectionOut)
def approve(booking_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(can_report)):
    """Review OK：管理者確認報告內容"""
    booking = _get_booking(db, booking_id)
    inspection = _inspection(db, booking)
    if inspection is None or inspection.status != InspectionStatus.SIGNED:
        raise HTTPException(status.HTTP_409_CONFLICT, "屋主簽名後才能確認報告")
    inspection.status = InspectionStatus.APPROVED
    inspection.approved_at, inspection.approved_by = datetime.now(), user.id
    db.commit()
    return _inspection_out(db, request, booking)


@router.post("/inspections/{booking_id}/unapprove", response_model=InspectionOut)
def unapprove(booking_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(can_report)):
    booking = _get_booking(db, booking_id)
    inspection = _inspection(db, booking)
    if inspection is None or inspection.status != InspectionStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "只有「已確認、尚未寄出」的報告可以取消確認")
    inspection.status = InspectionStatus.SIGNED
    inspection.approved_at = inspection.approved_by = None
    db.commit()
    return _inspection_out(db, request, booking)


@router.post("/inspections/{booking_id}/send", response_model=InspectionOut)
def send_report(
    booking_id: int, body: ReportSendIn, request: Request, tasks: BackgroundTasks,
    db: Session = Depends(get_db), _: User = Depends(can_report),
):
    """寄送報告 PDF 與感謝信給屋主；已寄出的可再寄一次"""
    booking = _get_booking(db, booking_id)
    inspection = _inspection(db, booking)
    if inspection is None or inspection.status not in (InspectionStatus.APPROVED, InspectionStatus.SENT):
        raise HTTPException(status.HTTP_409_CONFLICT, "請先 Review OK（確認報告）再寄送")
    to = body.to or booking.contact_email or booking.unit.owner_email
    if not to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "沒有屋主 Email，請輸入收件人")

    pdf = build_inspection_report(db, booking)
    rel = Path("reports") / f"inspection{booking.id}_{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}.pdf"
    (settings.storage_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / rel).write_bytes(pdf)
    inspection.report_path = rel.as_posix()
    inspection.status = InspectionStatus.SENT
    inspection.sent_at, inspection.sent_to = datetime.now(), to
    db.commit()

    unit, title = booking.unit, report_title(booking)
    body_text = "\n".join([
        f"{booking.contact_name} 您好：",
        "",
        f"感謝您撥冗協助完成 {unit.project.name} {unit.unit_no} 的{title.removesuffix('報告')}。",
        f"本次{title}已整理完成，請見附件 PDF。",
        "",
        f"  時間：{slot_label(booking.slot)}",
        f"  地點：{_place(booking)}",
        "",
        "報告中如有不合格項目，我們將儘速安排後續改善；如有任何疑問，歡迎與我們聯絡。",
        "再次感謝您的配合！",
        "",
    ])
    attachments = [Attachment(report_filename(booking), pdf)]
    external = db.scalar(select(Report).where(Report.booking_id == booking.id))
    if external:  # 有上傳外部報告時一併附上
        attachments.append(Attachment(external.original_filename, (settings.storage_dir / external.file_path).read_bytes()))
    tasks.add_task(
        send_email_safely, [to], f"【{unit.project.name}】{title}（{unit.unit_no}）", body_text, attachments,
    )
    return _inspection_out(db, request, booking)



# ---------------------------------------------------------------------------
# 參觀：現場報到
# ---------------------------------------------------------------------------
can_checkin = require_any_permission("booking.manage", "inspection.edit")


@router.post("/bookings/{booking_id}/checkin", response_model=InspectionOut)
def check_in(booking_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(can_checkin)):
    """參觀當天屋主到場：標記報到、預約完成"""
    booking = _get_booking(db, booking_id)
    if _service(booking) in CHECKLIST_SERVICES:
        raise HTTPException(status.HTTP_409_CONFLICT, "驗屋／健檢請填寫檢查項目並請屋主簽名")
    booking.checked_in_at = booking.checked_in_at or datetime.now()
    booking.status = BookingStatus.COMPLETED
    db.commit()
    return _inspection_out(db, request, booking)


@router.post("/bookings/{booking_id}/checkin/undo", response_model=InspectionOut)
def undo_check_in(booking_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(can_checkin)):
    booking = _get_booking(db, booking_id)
    if _service(booking) in CHECKLIST_SERVICES or booking.checked_in_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "此預約沒有報到紀錄")
    booking.checked_in_at = None
    booking.status = BookingStatus.BOOKED
    db.commit()
    return _inspection_out(db, request, booking)
