"""報告追蹤：外部報告 PDF、預約日後 7 / 14 天報告未完成的提醒

「報告完成」＝ 已上傳外部報告 PDF，或驗屋報告已寄送給屋主。
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Booking, BookingBatch, Inspection, InspectionStatus, Report, ReportReminder, ServiceType, TimeSlot
from app.services.booking import SERVICE_LABEL, slot_label
from app.services.mailer import send_email
from app.services.slots import ACTIVE_STATUSES

log = logging.getLogger(__name__)
REMINDER_DAYS = (7, 14)
MAX_PDF_BYTES = 30 * 1024 * 1024


@dataclass
class Overdue:
    booking: Booking
    days: int  # 預約日後第幾天
    inspection_status: str
    reminded: list[int]  # 已寄過的提醒（7 / 14）


def report_done(db: Session, booking: Booking) -> bool:
    if db.scalar(select(Report.id).where(Report.booking_id == booking.id)):
        return True
    status = db.scalar(select(Inspection.status).where(Inspection.booking_id == booking.id))
    return status == InspectionStatus.SENT


def overdue_bookings(db: Session, today: date | None = None) -> list[Overdue]:
    """預約日已過 7 天以上、報告尚未完成的預約（依逾期天數由多到少）"""
    today = today or date.today()
    bookings = db.scalars(
        select(Booking)
        .join(TimeSlot, Booking.slot_id == TimeSlot.id)
        .join(BookingBatch, Booking.batch_id == BookingBatch.id)
        .where(
            Booking.status.in_(ACTIVE_STATUSES),
            TimeSlot.slot_date <= today - timedelta(days=REMINDER_DAYS[0]),
            BookingBatch.service_type != ServiceType.VISIT,  # 參觀沒有報告
        )
        .order_by(TimeSlot.slot_date, TimeSlot.start_time)
    )
    out = []
    for b in bookings:
        if report_done(db, b):
            continue
        status = db.scalar(select(Inspection.status).where(Inspection.booking_id == b.id))
        reminded = sorted(db.scalars(select(ReportReminder.reminder_day).where(ReportReminder.booking_id == b.id)))
        out.append(Overdue(b, (today - b.slot.slot_date).days, status.value if status else "not_started", reminded))
    return out


def run_reminders(db: Session, today: date | None = None) -> dict:
    """
    每天執行一次：找出到達第 7 / 14 天、還沒寄過該階段提醒的預約，合併成一封提醒信。
    電腦當天沒開也沒關係，之後執行會補寄（已過 14 天的只寄 14 天那封）。
    """
    due: dict[int, list[Overdue]] = {7: [], 14: []}
    for item in overdue_bookings(db, today):
        stage = 14 if item.days >= 14 else 7
        if stage not in item.reminded:
            due[stage].append(item)
    total = len(due[7]) + len(due[14])
    if not total:
        return {"sent": 0, "day7": [], "day14": []}

    lines = ["以下預約的報告尚未完成（未上傳外部報告、也未寄出驗屋報告），請儘速處理：", ""]
    for stage in (14, 7):
        if due[stage]:
            lines.append(f"■ 預約日後已超過 {stage} 天（{len(due[stage])} 戶）")
            for item in due[stage]:
                b = item.booking
                label = SERVICE_LABEL[b.slot.batch.service_type]
                lines.append(
                    f"  - {b.unit.project.name} {b.unit.unit_no}｜{label} {slot_label(b.slot)}｜第 {item.days} 天｜"
                    f"驗屋狀態：{STATUS_TEXT.get(item.inspection_status, item.inspection_status)}｜聯絡人 {b.contact_name} {b.contact_phone}"
                )
            lines.append("")
    lines.append("可在 APP「驗屋」分頁 →「報告追蹤」查看與處理。")

    recipients = settings.reminder_recipients
    error = None
    try:
        send_email(recipients, f"【報告提醒】{total} 戶報告尚未完成", "\n".join(lines))
    except Exception as e:  # noqa: BLE001
        log.exception("寄送報告提醒失敗")
        error = str(e)[:500]

    for stage, items in due.items():
        for item in items:
            db.add(ReportReminder(
                booking_id=item.booking.id, reminder_day=stage, recipient_email=", ".join(recipients)[:255],
                success=error is None, error_message=error,
            ))
            if stage == 14 and 7 not in item.reminded:  # 直接跳到 14 天的，7 天那封視為已處理
                db.add(ReportReminder(booking_id=item.booking.id, reminder_day=7, recipient_email="(併入 14 天提醒)", success=error is None))
    db.commit()
    return {
        "sent": total if error is None else 0,
        "day7": [f"{i.booking.unit.project.name} {i.booking.unit.unit_no}" for i in due[7]],
        "day14": [f"{i.booking.unit.project.name} {i.booking.unit.unit_no}" for i in due[14]],
        "error": error,
    }


STATUS_TEXT = {
    "not_started": "未開始",
    "in_progress": "驗屋中",
    "signed": "已簽名",
    "approved": "已確認未寄出",
    "sent": "已寄出",
}
