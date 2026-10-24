"""每日排程：報告未完成提醒、備份。run.py 同一個程序裡跑兩個伺服器，用旗標確保只啟動一次。"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal, is_db_initialized
from app.services.backup import run_backup
from app.services.reports import run_reminders

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def reminder_job() -> None:
    if not is_db_initialized():
        return
    with SessionLocal() as db:
        result = run_reminders(db)
    if result["sent"]:
        log.info("已寄出報告提醒：7 天 %d 戶、14 天 %d 戶", len(result["day7"]), len(result["day14"]))


def backup_job() -> None:
    if is_db_initialized():
        run_backup()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None or not settings.scheduler_enabled:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    # misfire_grace_time：電腦睡眠錯過時間，醒來 6 小時內仍會補跑；coalesce 避免一次補跑多次
    common = {"misfire_grace_time": 6 * 3600, "coalesce": True, "max_instances": 1}
    _scheduler.add_job(reminder_job, CronTrigger(hour=settings.reminder_hour, minute=0), id="report_reminders", **common)
    _scheduler.add_job(backup_job, CronTrigger(hour=settings.backup_hour, minute=30), id="backup", **common)
    _scheduler.start()
    print(f"  每日排程：{settings.reminder_hour:02d}:00 報告未完成提醒、{settings.backup_hour:02d}:30 備份到 {settings.backup_dir}")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
