"""健檢日期（預約批次）：設定日期區間後自動產生 30 分鐘時段，產生後可個別關閉時段或調整名額"""

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, BookingBatch, ServiceType, TimeSlot, Unit
from app.routers.projects import get_project_or_404
from app.schemas import (
    BatchDatesIn,
    BatchDayOut,
    BatchDetailOut,
    BatchIn,
    BatchOut,
    BatchUpdate,
    DayUpdate,
    SlotOut,
    SlotUpdate,
)
from app.services.auth import get_current_user, require_permission
from app.services.slots import ACTIVE_STATUSES, generate_slots

router = APIRouter(tags=["健檢日期與時段"], dependencies=[Depends(get_current_user)])
manage = [Depends(require_permission("batch.manage"))]

MAX_DAYS = 92  # 一次最多產生約三個月，避免手誤產生上萬個時段


def _get_batch(db: Session, batch_id: int) -> BookingBatch:
    batch = db.get(BookingBatch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此健檢日期設定")
    return batch


def _booked_counts(db: Session, batch_id: int) -> dict[int, int]:
    rows = db.execute(
        select(Booking.slot_id, func.count(Booking.id))
        .where(Booking.batch_id == batch_id, Booking.status.in_(ACTIVE_STATUSES))
        .group_by(Booking.slot_id)
    )
    return dict(rows.all())


def _breaks(body: BatchIn | BatchDatesIn) -> list[tuple]:
    for b in body.breaks:
        if b.end <= b.start:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"屏蔽區段 {b.start:%H:%M}–{b.end:%H:%M} 的結束時間必須晚於開始時間")
    return [(b.start, b.end) for b in body.breaks]


def _booked_units(db: Session, batch_id: int) -> dict[int, list[str]]:
    rows = db.execute(
        select(Booking.slot_id, Unit.unit_no)
        .join(Unit, Booking.unit_id == Unit.id)
        .where(Booking.batch_id == batch_id, Booking.status.in_(ACTIVE_STATUSES))
        .order_by(Unit.unit_no)
    )
    out: dict[int, list[str]] = defaultdict(list)
    for slot_id, unit_no in rows:
        out[slot_id].append(unit_no)
    return out


def _validate_range(start: date, end: date, day_start, day_end) -> list[date]:
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "結束日期不能早於開始日期")
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"日期區間最多 {MAX_DAYS} 天")
    if day_end <= day_start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "每天的結束時間必須晚於開始時間")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _generate(db: Session, batch: BookingBatch, dates: list[date], day_start, day_end, breaks=()) -> int:
    created = sum(len(generate_slots(db, batch, d, day_start, day_end, breaks)) for d in dates)
    if created == 0 and not batch.slots:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "這個時間範圍產生不出任何時段，請檢查開始與結束時間")
    return created


def _batch_out(db: Session, batch: BookingBatch, with_days: bool = False) -> BatchOut | BatchDetailOut:
    booked = _booked_counts(db, batch.id)
    slots = sorted(batch.slots, key=lambda s: (s.slot_date, s.start_time))
    dates = sorted({s.slot_date for s in slots})
    data = dict(
        id=batch.id,
        project_id=batch.project_id,
        name=batch.name,
        service_type=batch.service_type.value,
        slot_minutes=batch.slot_minutes,
        slot_capacity=batch.slot_capacity,
        quota_mode=batch.quota_mode.value,
        is_active=batch.is_active,
        description=batch.description,
        booking_open_at=batch.booking_open_at,
        booking_close_at=batch.booking_close_at,
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        day_count=len(dates),
        slot_count=len(slots),
        open_slot_count=sum(s.is_open for s in slots),
        booked_count=sum(booked.values()),
    )
    if not with_days:
        return BatchOut(**data)

    units = _booked_units(db, batch.id)
    by_day: dict[date, list[SlotOut]] = defaultdict(list)
    for s in slots:
        by_day[s.slot_date].append(
            SlotOut(
                id=s.id, start_time=s.start_time, end_time=s.end_time,
                capacity=s.capacity, booked=booked.get(s.id, 0), is_open=s.is_open, units=units.get(s.id, []),
            )
        )
    return BatchDetailOut(**data, days=[BatchDayOut(date=d, slots=by_day[d]) for d in dates])


@router.post("/projects/{project_id}/batches", response_model=BatchDetailOut, status_code=201, dependencies=manage)
def create_batch(project_id: int, body: BatchIn, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    dates = _validate_range(body.start_date, body.end_date, body.day_start, body.day_end)
    batch = BookingBatch(
        project_id=project_id,
        name=body.name,
        service_type=ServiceType(body.service_type),
        slot_minutes=body.slot_minutes,
        slot_capacity=body.slot_capacity,
    )
    breaks = _breaks(body)
    db.add(batch)
    db.flush()
    _generate(db, batch, dates, body.day_start, body.day_end, breaks)
    db.commit()
    db.refresh(batch)
    return _batch_out(db, batch, with_days=True)


@router.get("/projects/{project_id}/batches", response_model=list[BatchOut])
def list_batches(project_id: int, db: Session = Depends(get_db)):
    get_project_or_404(db, project_id)
    batches = db.scalars(
        select(BookingBatch).where(BookingBatch.project_id == project_id).order_by(BookingBatch.id.desc())
    )
    return [_batch_out(db, b) for b in batches]


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    return _batch_out(db, _get_batch(db, batch_id), with_days=True)


@router.patch("/batches/{batch_id}", response_model=BatchOut, dependencies=manage)
def update_batch(batch_id: int, body: BatchUpdate, db: Session = Depends(get_db)):
    batch = _get_batch(db, batch_id)
    if body.name is not None:
        batch.name = body.name
    if body.is_active is not None:
        batch.is_active = body.is_active
    db.commit()
    return _batch_out(db, batch)


@router.post("/batches/{batch_id}/dates", response_model=BatchDetailOut, dependencies=manage)
def add_dates(batch_id: int, body: BatchDatesIn, db: Session = Depends(get_db)):
    """追加日期（已存在的時段不會重複產生）"""
    batch = _get_batch(db, batch_id)
    dates = _validate_range(body.start_date, body.end_date, body.day_start, body.day_end)
    _generate(db, batch, dates, body.day_start, body.day_end, _breaks(body))
    db.commit()
    db.refresh(batch)
    return _batch_out(db, batch, with_days=True)


@router.delete("/batches/{batch_id}", status_code=204, dependencies=manage)
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = _get_batch(db, batch_id)
    if db.scalar(select(func.count(Booking.id)).where(Booking.batch_id == batch.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "已有預約紀錄，不能刪除；可改為停用")
    db.delete(batch)
    db.commit()


@router.patch("/slots/{slot_id}", response_model=SlotOut, dependencies=manage)
def update_slot(slot_id: int, body: SlotUpdate, db: Session = Depends(get_db)):
    slot = db.get(TimeSlot, slot_id)
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此時段")
    booked = _booked_counts(db, slot.batch_id).get(slot.id, 0)
    if body.capacity is not None:
        if body.capacity < booked:
            raise HTTPException(status.HTTP_409_CONFLICT, f"此時段已有 {booked} 組預約，名額不能少於 {booked}")
        slot.capacity = body.capacity
    if body.is_open is not None:
        slot.is_open = body.is_open  # 關閉只是不再接受新預約，既有預約保留
    db.commit()
    return SlotOut(
        id=slot.id, start_time=slot.start_time, end_time=slot.end_time,
        capacity=slot.capacity, booked=booked, is_open=slot.is_open, units=_booked_units(db, slot.batch_id).get(slot.id, []),
    )


@router.patch("/batches/{batch_id}/days/{day}", response_model=BatchDayOut, dependencies=manage)
def update_day(batch_id: int, day: date, body: DayUpdate, db: Session = Depends(get_db)):
    """整天開放 / 關閉"""
    batch = _get_batch(db, batch_id)
    day_slots = [s for s in batch.slots if s.slot_date == day]
    if not day_slots:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "這一天沒有時段")
    for s in day_slots:
        s.is_open = body.is_open
    db.commit()
    detail = _batch_out(db, batch, with_days=True)
    return next(d for d in detail.days if d.date == day)
