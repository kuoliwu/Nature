"""第二階段：寄送預約邀請、屋主線上預約

管理端：
  PATCH /batches/{id}/settings        預約說明、開放 / 截止時間
  POST  /batches/{id}/invites/send    寄邀請信給各戶
  GET   /batches/{id}/invites         各戶狀態（未寄 / 已寄 / 已預約哪個時段）
  POST  /bookings/{id}/cancel         管理端取消預約
屋主（公開，可經對外網址開啟）：
  GET   /book/{token}                 預約網頁
  GET   /api/public/book/{token}      可預約的日期時段
  POST  /api/public/book/{token}      預約 / 改期（寄確認信）
  POST  /api/public/book/{token}/cancel
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, BookingBatch, BookingStatus, Unit, UnitInvite
from app.schemas import (
    BatchOut,
    BatchSettingsIn,
    InviteBookingOut,
    InviteSendIn,
    InviteSendOut,
    InviteStatusOut,
    PublicBookIn,
    PublicBookingInfo,
    PublicBookOut,
    PublicCurrentBooking,
    PublicDay,
    PublicSlot,
)
from app.services.auth import require_permission
from app.services.booking import (
    SERVICE_LABEL,
    active_booking,
    available_days,
    book,
    booking_window,
    get_or_create_invite,
    queue_booking_email,
    queue_invite_email,
    slot_label,
    slot_started,
)
from app.services.links import public_base_url

admin = APIRouter(tags=["預約邀請（管理）"])
public = APIRouter(tags=["屋主預約（公開）"])
can_view = [Depends(require_permission("booking.view"))]
can_manage = [Depends(require_permission("booking.manage"))]

BOOK_PAGE = (Path(__file__).resolve().parent.parent / "templates" / "book.html").read_text("utf-8")


def _base_url(request: Request) -> str:
    # 屋主多半在外網，有對外網址（PUBLIC_BASE_URL / 通道）就用對外網址
    return public_base_url() or str(request.base_url).rstrip("/")


def _link(request: Request, invite: UnitInvite) -> str:
    return f"{_base_url(request)}/book/{invite.token}"


def _get_batch(db: Session, batch_id: int) -> BookingBatch:
    batch = db.get(BookingBatch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此健檢日期設定")
    return batch


# ---------------------------------------------------------------------------
# 管理端
# ---------------------------------------------------------------------------
@admin.patch("/batches/{batch_id}/settings", response_model=BatchOut, dependencies=[Depends(require_permission("batch.manage"))])
def update_settings(batch_id: int, body: BatchSettingsIn, db: Session = Depends(get_db)):
    from app.routers.batches import _batch_out  # 避免循環匯入

    batch = _get_batch(db, batch_id)
    if body.booking_open_at and body.booking_close_at and body.booking_close_at <= body.booking_open_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "截止時間必須晚於開放時間")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(batch, key, (value.strip() or None) if isinstance(value, str) else value)
    db.commit()
    return _batch_out(db, batch)


@admin.post("/batches/{batch_id}/invites/send", response_model=InviteSendOut, dependencies=can_manage)
def send_invites(
    batch_id: int, body: InviteSendIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    batch = _get_batch(db, batch_id)
    query = select(Unit).where(Unit.project_id == batch.project_id).order_by(Unit.unit_no)
    if body.unit_ids is not None:
        query = query.where(Unit.id.in_(body.unit_ids))
    out = InviteSendOut(sent=[], no_email=[], already_sent=[], already_booked=[])
    for unit in db.scalars(query):
        if not unit.owner_email:
            out.no_email.append(unit.unit_no)
            continue
        if active_booking(db, batch.id, unit.id):
            out.already_booked.append(unit.unit_no)
            continue
        invite = get_or_create_invite(db, batch, unit)
        if invite.sent_at and not body.resend:
            out.already_sent.append(unit.unit_no)
            continue
        invite.sent_at, invite.sent_to = datetime.now(), unit.owner_email
        invite.send_count += 1
        queue_invite_email(tasks, invite, _link(request, invite))
        out.sent.append(unit.unit_no)
    db.commit()
    return out


@admin.get("/batches/{batch_id}/invites", response_model=list[InviteStatusOut], dependencies=can_view)
def list_invites(batch_id: int, request: Request, db: Session = Depends(get_db)):
    batch = _get_batch(db, batch_id)
    invites = {i.unit_id: i for i in db.scalars(select(UnitInvite).where(UnitInvite.batch_id == batch.id))}
    bookings = {
        b.unit_id: b
        for b in db.scalars(select(Booking).where(Booking.batch_id == batch.id, Booking.status == BookingStatus.BOOKED))
    }
    rows = []
    for unit in db.scalars(select(Unit).where(Unit.project_id == batch.project_id).order_by(Unit.unit_no)):
        inv, b = invites.get(unit.id), bookings.get(unit.id)
        rows.append(InviteStatusOut(
            unit_id=unit.id,
            unit_no=unit.unit_no,
            owner_name=unit.owner_name,
            owner_email=unit.owner_email,
            link=_link(request, inv) if inv else None,
            sent_at=inv.sent_at if inv else None,
            send_count=inv.send_count if inv else 0,
            last_opened_at=inv.last_opened_at if inv else None,
            booking=InviteBookingOut(
                id=b.id, slot_id=b.slot_id, date=b.slot.slot_date, start_time=b.slot.start_time, end_time=b.slot.end_time,
                contact_name=b.contact_name, contact_phone=b.contact_phone, contact_email=b.contact_email,
            ) if b else None,
        ))
    return rows


@admin.post("/batches/{batch_id}/units/{unit_id}/invite-link", response_model=InviteStatusOut, dependencies=can_manage)
def create_invite_link(batch_id: int, unit_id: int, request: Request, db: Session = Depends(get_db)):
    """不寄信，只產生連結（給沒有 Email 的屋主，用 LINE / 簡訊傳）"""
    batch = _get_batch(db, batch_id)
    unit = db.get(Unit, unit_id)
    if unit is None or unit.project_id != batch.project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此戶")
    get_or_create_invite(db, batch, unit)
    db.commit()
    return next(r for r in list_invites(batch_id, request, db) if r.unit_id == unit_id)


@admin.post("/bookings/{booking_id}/cancel", status_code=204, dependencies=can_manage)
def admin_cancel(booking_id: int, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if booking is None or booking.status != BookingStatus.BOOKED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到有效的預約")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    invite = get_or_create_invite(db, booking.slot.batch, booking.unit)
    db.commit()
    queue_booking_email(tasks, booking, _link(request, invite), cancelled=True)


# ---------------------------------------------------------------------------
# 屋主
# ---------------------------------------------------------------------------
def _get_invite(db: Session, token: str) -> UnitInvite:
    invite = db.scalar(select(UnitInvite).where(UnitInvite.token == token))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預約連結無效，請確認網址是否完整")
    return invite


def _current(booking: Booking | None) -> PublicCurrentBooking | None:
    if booking is None:
        return None
    s = booking.slot
    return PublicCurrentBooking(
        slot_id=s.id, date=s.slot_date, start_time=s.start_time, end_time=s.end_time,
        contact_name=booking.contact_name, contact_phone=booking.contact_phone, contact_email=booking.contact_email,
        can_change=not slot_started(s) and booking_window(s.batch) is None,
    )


@public.get("/book/{token}", response_class=HTMLResponse, include_in_schema=False)
def book_page(token: str):
    payload = json.dumps({"token": token}).replace("<", "\\u003c")
    return HTMLResponse(BOOK_PAGE.replace("__CONFIG__", payload))


@public.get("/api/public/book/{token}", response_model=PublicBookingInfo)
def booking_info(token: str, db: Session = Depends(get_db)):
    invite = _get_invite(db, token)
    invite.last_opened_at = datetime.now()
    db.commit()
    batch, unit = invite.batch, invite.unit
    current = active_booking(db, batch.id, unit.id)
    project = unit.project
    return PublicBookingInfo(
        project_name=project.name,
        unit_no=unit.unit_no,
        place=unit.address or project.address or project.community_address or "",
        batch_name=batch.name,
        service_label=SERVICE_LABEL[batch.service_type],
        description=batch.description,
        closed_reason=booking_window(batch),
        close_at=batch.booking_close_at,
        defaults={"contact_name": unit.owner_name or "", "contact_phone": unit.owner_phone or "", "contact_email": unit.owner_email or ""},
        current=_current(current),
        days=[
            PublicDay(date=d, slots=[PublicSlot(id=s.id, start_time=s.start_time, end_time=s.end_time, remaining=r) for s, r in slots])
            for d, slots in available_days(db, batch)
        ],
    )


@public.post("/api/public/book/{token}", response_model=PublicBookOut)
def make_booking(token: str, body: PublicBookIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    invite = _get_invite(db, token)
    contact = body.model_dump(exclude={"slot_id"})
    booking, previous = book(db, invite, body.slot_id, contact)
    unit = invite.unit
    if not unit.owner_email:  # 屋主原本沒留 Email 時順便補上
        unit.owner_email = body.contact_email
    db.commit()
    db.refresh(booking)
    queue_booking_email(tasks, booking, _link(request, invite), previous=previous)
    verb = "改期" if previous else "預約"
    return PublicBookOut(message=f"{verb}完成：{slot_label(booking.slot)}，確認信已寄到 {body.contact_email}", current=_current(booking))


@public.post("/api/public/book/{token}/cancel", status_code=204)
def cancel_booking(token: str, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    invite = _get_invite(db, token)
    booking = active_booking(db, invite.batch_id, invite.unit_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目前沒有預約")
    if slot_started(booking.slot):
        raise HTTPException(status.HTTP_409_CONFLICT, "預約時段已開始，無法取消，請聯絡管理單位")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    queue_booking_email(tasks, booking, _link(request, invite), cancelled=True)
