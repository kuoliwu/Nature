"""第二階段：屋主預約。名額檢查、改期、取消，以及通知信內容。"""

import secrets
from collections import defaultdict
from datetime import date, datetime

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingBatch, BookingStatus, ServiceType, TimeSlot, Unit, UnitInvite
from app.services.mailer import send_email_safely
from app.services.slots import ACTIVE_STATUSES

SERVICE_LABEL = {ServiceType.HEALTH_CHECK: "健檢", ServiceType.INSPECTION: "驗屋"}
WEEKDAYS = "一二三四五六日"


def slot_label(slot: TimeSlot) -> str:
    return f"{slot.slot_date:%Y-%m-%d}（{WEEKDAYS[slot.slot_date.weekday()]}）{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"


def slot_started(slot: TimeSlot) -> bool:
    return datetime.combine(slot.slot_date, slot.start_time) <= datetime.now()


def booking_window(batch: BookingBatch) -> str | None:
    """可以預約時回傳 None，否則回傳原因"""
    now = datetime.now()
    if not batch.is_active:
        return "此預約目前未開放"
    if batch.booking_open_at and now < batch.booking_open_at:
        return f"預約將於 {batch.booking_open_at:%Y-%m-%d %H:%M} 開放"
    if batch.booking_close_at and now > batch.booking_close_at:
        return f"預約已於 {batch.booking_close_at:%Y-%m-%d %H:%M} 截止"
    return None


def booked_counts(db: Session, batch_id: int) -> dict[int, int]:
    rows = db.execute(
        select(Booking.slot_id, func.count(Booking.id))
        .where(Booking.batch_id == batch_id, Booking.status.in_(ACTIVE_STATUSES))
        .group_by(Booking.slot_id)
    )
    return dict(rows.all())


def available_days(db: Session, batch: BookingBatch) -> list[tuple[date, list[tuple[TimeSlot, int]]]]:
    """開放中、尚未開始的時段與剩餘名額（額滿的也列出，剩餘為 0）"""
    booked = booked_counts(db, batch.id)
    by_day: dict[date, list[tuple[TimeSlot, int]]] = defaultdict(list)
    for s in sorted(batch.slots, key=lambda s: (s.slot_date, s.start_time)):
        if s.is_open and not slot_started(s):
            by_day[s.slot_date].append((s, max(s.capacity - booked.get(s.id, 0), 0)))
    return sorted(by_day.items())


def active_booking(db: Session, batch_id: int, unit_id: int) -> Booking | None:
    return db.scalar(
        select(Booking).where(
            Booking.batch_id == batch_id, Booking.unit_id == unit_id, Booking.status == BookingStatus.BOOKED
        )
    )


def get_or_create_invite(db: Session, batch: BookingBatch, unit: Unit) -> UnitInvite:
    invite = db.scalar(select(UnitInvite).where(UnitInvite.batch_id == batch.id, UnitInvite.unit_id == unit.id))
    if invite is None:
        invite = UnitInvite(batch_id=batch.id, unit_id=unit.id, token=secrets.token_urlsafe(24))
        db.add(invite)
        db.flush()
    return invite


def book(
    db: Session, invite: UnitInvite, slot_id: int, contact: dict
) -> tuple[Booking, TimeSlot | None]:
    """新增或改期；回傳 (預約, 改期前的時段)。名額不足時丟 409。呼叫端負責 commit。"""
    batch, unit = invite.batch, invite.unit
    reason = booking_window(batch)
    if reason:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)

    slot = db.get(TimeSlot, slot_id)
    if slot is None or slot.batch_id != batch.id or not slot.is_open:
        raise HTTPException(status.HTTP_409_CONFLICT, "這個時段已不開放，請選擇其他時段")
    if slot_started(slot):
        raise HTTPException(status.HTTP_409_CONFLICT, "這個時段已經開始或結束，請選擇其他時段")

    current = active_booking(db, batch.id, unit.id)
    previous_slot = None
    if current and current.slot_id == slot.id:
        for key, value in contact.items():  # 同一時段只更新聯絡資料
            setattr(current, key, value)
        db.flush()
        return current, None
    if current:
        if slot_started(current.slot):
            raise HTTPException(status.HTTP_409_CONFLICT, "原預約時段已開始，無法再改期，請聯絡管理單位")
        previous_slot = current.slot
        current.slot_id = slot.id
        for key, value in contact.items():
            setattr(current, key, value)
        booking = current
    else:
        booking = Booking(batch_id=batch.id, slot_id=slot.id, unit_id=unit.id, **contact)
        db.add(booking)

    # 先寫入再數：SQLite 同時只允許一個寫入交易，後到的人會等前一筆 commit 後才數，不會超賣
    db.flush()
    used = db.scalar(
        select(func.count(Booking.id)).where(Booking.slot_id == slot.id, Booking.status.in_(ACTIVE_STATUSES))
    )
    if used > slot.capacity:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "這個時段剛好額滿了，請選擇其他時段")
    return booking, previous_slot


# ---------------------------------------------------------------------------
# 通知信
# ---------------------------------------------------------------------------
def _place(unit: Unit) -> str:
    project = unit.project
    return unit.address or project.address or project.community_address or ""


def queue_invite_email(tasks: BackgroundTasks, invite: UnitInvite, link: str) -> None:
    unit, batch = invite.unit, invite.batch
    label = SERVICE_LABEL[batch.service_type]
    lines = [
        f"{unit.owner_name or '屋主'} 您好：",
        "",
        f"{unit.project.name} {unit.unit_no} 的{label}開放預約了，請點以下連結選擇方便的日期與時段：",
        link,
        "",
    ]
    if batch.description:
        lines += [batch.description, ""]
    if batch.booking_close_at:
        lines.append(f"預約截止：{batch.booking_close_at:%Y-%m-%d %H:%M}")
    lines += ["此連結為您專屬，請勿轉傳。預約後也可以用同一個連結改期或取消。", ""]
    tasks.add_task(send_email_safely, [invite.sent_to], f"【{unit.project.name}】{label}預約邀請（{unit.unit_no}）", "\n".join(lines))


def queue_booking_email(
    tasks: BackgroundTasks, booking: Booking, link: str, previous: TimeSlot | None = None, cancelled: bool = False
) -> None:
    if not booking.contact_email:
        return
    unit, slot = booking.unit, booking.slot
    label = SERVICE_LABEL[booking.slot.batch.service_type]
    if cancelled:
        subject = f"【{unit.project.name}】{label}預約已取消（{unit.unit_no}）"
        head = f"您的{label}預約已取消：{slot_label(slot)}"
        tail = f"如需重新預約，請使用同一個連結：\n{link}"
    else:
        subject = f"【{unit.project.name}】{label}預約{'改期' if previous else ''}確認（{unit.unit_no}）"
        head = (f"您的{label}預約已改期：\n  原時段：{slot_label(previous)}\n  新時段：{slot_label(slot)}" if previous
                else f"您的{label}預約已完成：{slot_label(slot)}")
        tail = f"如需改期或取消，請使用同一個連結：\n{link}"
    body = "\n".join([
        f"{booking.contact_name} 您好：",
        "",
        head,
        "",
        f"  建案：{unit.project.name}",
        f"  戶別：{unit.unit_no}",
        f"  地點：{_place(unit)}",
        f"  聯絡電話：{booking.contact_phone}",
        "",
        tail,
        "",
    ])
    tasks.add_task(send_email_safely, [booking.contact_email], subject, body)
