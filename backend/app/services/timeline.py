"""售服時間軸：每個建案的七個步驟走到哪裡（建案列表、建案頁共用）

  1 新建案 → 2 預約參觀 → 3 預約驗屋 → 4 驗屋 → 5 生產履歷＋住屋手冊 → 6 預約健檢 → 7 健檢

每步驟的狀態：done 完成 / active 進行中 / todo 未開始。
完成的判斷：全部住戶都完成；或日期區間已過且沒有「已預約未完成」的住戶（沒來的不再等）。
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Project
from app.services import handbook
from app.services.dashboard import collect_phases

STEPS = (
    ("created", "新建案"),
    ("visit", "預約參觀"),
    ("inspection_booking", "預約驗屋"),
    ("inspection", "驗屋"),
    ("handbook", "履歷手冊"),
    ("health_check_booking", "預約健檢"),
    ("health_check", "健檢"),
)


def _step(key: str, label: str, *, done: int, total: int, finished: bool, started: bool,
          date_from: str | None = None, date_to: str | None = None, note: str = "") -> dict:
    status = "done" if finished else "active" if started else "todo"
    return {"key": key, "label": label, "status": status, "done": done, "total": total,
            "date_from": date_from, "date_to": date_to, "note": note}


def build_timeline(db: Session, project: Project, today: date | None = None) -> dict:
    today = today or date.today()
    collected = collect_phases(db, project)
    total = len(collected["units"])
    phases = {p["service"]: p for p in collected["phases"]}
    labels = dict(STEPS)

    def ended(p: dict) -> bool:
        return bool(p["date_to"]) and date.fromisoformat(p["date_to"]) < today

    def begun(p: dict) -> bool:
        return bool(p["date_from"]) and date.fromisoformat(p["date_from"]) <= today

    steps = [_step("created", labels["created"], done=total, total=total, finished=True, started=True,
                   date_from=project.created_at.date().isoformat())]

    visit = phases["visit"]
    checked_in = visit["stages"]["completed"]
    steps.append(_step(
        "visit", labels["visit"], done=checked_in, total=total,
        finished=bool(total) and checked_in >= total or ended(visit),
        started=visit["batches"] > 0, date_from=visit["date_from"], date_to=visit["date_to"],
        note=f"已報到 {checked_in}/{total}",
    ))

    for service, booking_key, step_key in (
        ("inspection", "inspection_booking", "inspection"),
        ("health_check", "health_check_booking", "health_check"),
    ):
        p = phases[service]
        completed, pending = p["stages"]["completed"], p["stages"]["booked"]
        booked = completed + pending
        steps.append(_step(
            booking_key, labels[booking_key], done=booked, total=total,
            finished=bool(total) and booked >= total or ended(p),
            started=p["batches"] > 0, date_from=p["date_from"], date_to=p["date_to"],
            note=f"已預約 {booked}/{total}",
        ))
        steps.append(_step(
            step_key, labels[step_key], done=completed, total=total,
            finished=bool(total) and completed >= total or (ended(p) and booked > 0 and pending == 0),
            started=booked > 0 or begun(p), date_from=p["date_from"], date_to=p["date_to"],
            note=f"完成 {completed}/{total}・報告已寄 {p['reports_sent']}",
        ))
        if service == "inspection":  # 第 5 步夾在驗屋與預約健檢之間：住屋手冊全部寄出＝完成
            sent = handbook.sent_count(db, project.id)
            steps.append(_step("handbook", labels["handbook"], done=sent, total=total,
                               finished=bool(total) and sent >= total, started=sent > 0 or handbook.started(db, project.id),
                               note=f"已寄送 {sent}/{total}"))

    current = next((i for i, s in enumerate(steps) if s["status"] != "done"), len(steps) - 1)
    return {
        "project": {"id": project.id, "name": project.name,
                    "address": project.address or project.community_address or "", "unit_count": total},
        "current": current,
        "steps": steps,
    }
