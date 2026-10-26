"""建案儀表板資料：APP 儀表板、互動網頁報表、Excel 報表共用同一份計算結果"""

from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CHECKLIST_SERVICES,
    Booking,
    BookingBatch,
    CheckResult,
    Inspection,
    InspectionCheckPoint,
    InspectionResult,
    InspectionStatus,
    Project,
    Report,
    ServiceType,
    Unit,
    UnitInvite,
)
from app.services.booking import SERVICE_LABEL
from app.services.reports import overdue_bookings
from app.services.slots import ACTIVE_STATUSES

DONE_INSPECTION = (InspectionStatus.SIGNED, InspectionStatus.APPROVED, InspectionStatus.SENT)
PHASE_ORDER = (ServiceType.VISIT, ServiceType.INSPECTION, ServiceType.HEALTH_CHECK)
# 各戶在某階段的進度（互斥，取最前面的）
STAGES = ("completed", "booked", "invited", "not_invited")
STAGE_LABEL = {"completed": "已完成", "booked": "已預約未完成", "invited": "已邀請未預約", "not_invited": "未邀請"}


def collect_phases(db: Session, project: Project) -> dict:
    """各服務階段的住戶進度；儀表板與售服時間軸共用"""
    units = list(db.scalars(select(Unit).where(Unit.project_id == project.id)))
    unit_ids = {u.id for u in units}
    batches = list(db.scalars(select(BookingBatch).where(BookingBatch.project_id == project.id)))
    batch_service = {b.id: b.service_type for b in batches}

    bookings = list(db.scalars(
        select(Booking).where(Booking.batch_id.in_(batch_service), Booking.status.in_(ACTIVE_STATUSES))
    )) if batches else []
    inspections = {
        i.booking_id: i for i in db.scalars(select(Inspection).where(Inspection.booking_id.in_([b.id for b in bookings])))
    } if bookings else {}
    external = set(db.scalars(select(Report.booking_id).where(Report.booking_id.in_([b.id for b in bookings])))) if bookings else set()
    invited = defaultdict(set)
    for inv in db.scalars(select(UnitInvite).where(UnitInvite.batch_id.in_(batch_service), UnitInvite.sent_at.is_not(None))) if batches else []:
        invited[batch_service[inv.batch_id]].add(inv.unit_id)

    # --- 各階段 ---
    phases = []
    for service in PHASE_ORDER:
        svc_batches = [b for b in batches if b.service_type == service]
        svc_bookings = [b for b in bookings if batch_service[b.batch_id] == service]
        slots = [s for b in svc_batches for s in b.slots]
        booked_units = {b.unit_id for b in svc_bookings}
        if service == ServiceType.VISIT:
            done_units = {b.unit_id for b in svc_bookings if b.checked_in_at}
        else:
            done_units = {b.unit_id for b in svc_bookings if b.id in inspections and inspections[b.id].status in DONE_INSPECTION}
        report_sent = sum(
            1 for b in svc_bookings
            if b.id in external or (b.id in inspections and inspections[b.id].status == InspectionStatus.SENT)
        )
        stages = {
            "completed": len(done_units),
            "booked": len(booked_units - done_units),
            "invited": len((invited[service] & unit_ids) - booked_units),
        }
        stages["not_invited"] = max(len(units) - sum(stages.values()), 0)
        slot_dates = [s.slot_date for s in slots]
        phases.append({
            "service": service.value,
            "label": SERVICE_LABEL[service],
            "date_from": min(slot_dates).isoformat() if slot_dates else None,
            "date_to": max(slot_dates).isoformat() if slot_dates else None,
            "batches": len(svc_batches),
            "slots": len(slots),
            "open_slots": sum(1 for s in slots if s.is_open),
            "capacity": sum(s.capacity for s in slots if s.is_open),
            "bookings": len(svc_bookings),
            "stages": stages,
            "reports_sent": report_sent if service.value in CHECKLIST_SERVICES else None,
            "has_reports": service.value in CHECKLIST_SERVICES,
        })
    return {"units": units, "batches": batches, "batch_service": batch_service, "bookings": bookings, "phases": phases}


def build_dashboard(db: Session, project: Project) -> dict:
    collected = collect_phases(db, project)
    units, batches, bookings, phases = collected["units"], collected["batches"], collected["bookings"], collected["phases"]
    batch_service = collected["batch_service"]

    # --- 每日預約數（依服務）---
    slot_of = {s.id: s for b in batches for s in b.slots}
    per_day: dict[date, Counter] = defaultdict(Counter)
    for b in bookings:
        per_day[slot_of[b.slot_id].slot_date][batch_service[b.batch_id].value] += 1
    daily = [{"date": d.isoformat(), **{s.value: per_day[d][s.value] for s in PHASE_ORDER}} for d in sorted(per_day)]

    # --- 檢查結果與最常見的不合格項目 ---
    booking_service = {b.id: batch_service[b.batch_id].value for b in bookings}
    results_count = {s: Counter() for s in CHECKLIST_SERVICES}
    fail_counter: Counter = Counter()
    if bookings:
        rows = db.execute(
            select(InspectionResult.booking_id, InspectionResult.result, InspectionCheckPoint.id)
            .join(InspectionCheckPoint, InspectionResult.check_point_id == InspectionCheckPoint.id)
            .where(InspectionResult.booking_id.in_(booking_service))
        ).all()
        labels = {}
        for booking_id, result, point_id in rows:
            service = booking_service[booking_id]
            if service in results_count and result != CheckResult.PENDING:
                results_count[service][result.value] += 1
            if result == CheckResult.FAIL:
                if point_id not in labels:
                    p = db.get(InspectionCheckPoint, point_id)
                    labels[point_id] = f"{p.item.category.name}／{p.item.name}／{p.name}"
                fail_counter[(service, labels[point_id])] += 1
    top_fails = [
        {"service": s, "service_label": SERVICE_LABEL[ServiceType(s)], "label": label, "count": n}
        for (s, label), n in fail_counter.most_common(10)
    ]

    overdue = sum(1 for o in overdue_bookings(db) if o.booking.unit.project_id == project.id)
    with_email = sum(1 for u in units if u.owner_email)
    return {
        "project": {"id": project.id, "name": project.name, "address": project.address or project.community_address or ""},
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "units": {"total": len(units), "with_email": with_email, "without_email": len(units) - with_email},
        "stage_labels": STAGE_LABEL,
        "phases": phases,
        "daily": daily,
        "results": {s: {k: results_count[s][k] for k in ("pass", "fail", "na")} for s in CHECKLIST_SERVICES},
        "top_fails": top_fails,
        "overdue_reports": overdue,
    }
