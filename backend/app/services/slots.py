"""排程規則：產生 30 分鐘時段、計算剩餘名額（共用 / 獨立兩種模式）"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingBatch, BookingStatus, BatchService, QuotaMode, TimeSlot

# 會佔用名額的預約狀態
ACTIVE_STATUSES = (BookingStatus.BOOKED, BookingStatus.COMPLETED)


def generate_slots(
    db: Session,
    batch: BookingBatch,
    slot_date: date,
    day_start: time,
    day_end: time,
    breaks: list[tuple[time, time]] = (),
) -> list[TimeSlot]:
    """在 day_start ~ day_end 之間依 batch.slot_minutes 切時段；
    與任一屏蔽區段（例如午休 12:00–13:00）重疊的時段不產生；已存在的時段略過。"""
    existing = set(
        db.scalars(
            select(TimeSlot.start_time).where(
                TimeSlot.batch_id == batch.id, TimeSlot.slot_date == slot_date
            )
        )
    )
    step = timedelta(minutes=batch.slot_minutes)
    cursor = datetime.combine(slot_date, day_start)
    end = datetime.combine(slot_date, day_end)

    created: list[TimeSlot] = []
    while cursor + step <= end:
        slot_start, slot_end = cursor.time(), (cursor + step).time()
        blocked = any(slot_start < b_end and slot_end > b_start for b_start, b_end in breaks)
        if not blocked and slot_start not in existing:
            slot = TimeSlot(
                batch_id=batch.id,
                slot_date=slot_date,
                start_time=cursor.time(),
                end_time=(cursor + step).time(),
                capacity=batch.slot_capacity,
            )
            db.add(slot)
            created.append(slot)
        cursor += step
    db.flush()
    return created


def remaining_capacity(db: Session, slot: TimeSlot, service: BatchService | None = None) -> int:
    """
    共用名額 (shared)：同時段所有服務項目合計不得超過 slot.capacity（預設 3 組）。
    獨立計算 (independent)：每個服務項目各自不得超過 service.capacity_per_slot。
    """
    query = select(func.count(Booking.id)).where(
        Booking.slot_id == slot.id, Booking.status.in_(ACTIVE_STATUSES)
    )

    if slot.batch.quota_mode == QuotaMode.SHARED:
        used = db.scalar(query) or 0
        return max(slot.capacity - used, 0)

    if service is None:
        raise ValueError("獨立計算模式下必須指定服務項目")
    used = db.scalar(query.where(Booking.service_id == service.id)) or 0
    return max(service.capacity_per_slot - used, 0)
