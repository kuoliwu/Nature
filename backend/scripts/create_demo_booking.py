"""建立一筆示範預約，並印出屋主授權頁連結，用來在手機上測試簽名流程。

用法（在 backend/ 目錄下）：
    python -m scripts.create_demo_booking
    python -m scripts.create_demo_booking --id-number A123456789   # 測試身分證驗證

正式的預約流程完成後，這個腳本只是開發工具。
"""

import argparse
from datetime import date, time, timedelta

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Booking, BookingBatch, Project, ServiceType, Unit
from app.seed import seed_inspection_checklist
from app.services.security import hash_id_number
from app.services.slots import generate_slots
from scripts.owner_link import print_owner_link

DEMO_PROJECT = "示範建案（測試用）"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id-number", help="設定屋主身分證字號，授權頁會要求輸入")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_inspection_checklist(db)

        project = db.scalar(select(Project).where(Project.name == DEMO_PROJECT))
        if project is None:
            project = Project(
                name=DEMO_PROJECT, phone="02-2345-6789",
                community_address="台北市信義區示範路 1 號", community_manager="王經理",
            )
            db.add(project)
            db.flush()

        n = db.query(Unit).filter_by(project_id=project.id).count() + 1
        unit = Unit(
            project_id=project.id, unit_no=f"A-{n}F-1", address=f"台北市信義區示範路 1 號 {n} 樓",
            owner_name="王小明",
            owner_id_hash=hash_id_number(args.id_number) if args.id_number else None,
        )
        batch = BookingBatch(
            project_id=project.id, name=f"示範驗屋批次 {n}", service_type=ServiceType.INSPECTION,
            require_id_verification=bool(args.id_number),
        )
        db.add_all([unit, batch])
        db.flush()

        slot = generate_slots(db, batch, date.today() + timedelta(days=3), time(10, 0), time(10, 30))[0]
        booking = Booking(
            batch_id=batch.id, slot_id=slot.id, unit_id=unit.id,
            contact_name="王小明", contact_phone="0912345678", is_delegated=True,
        )
        db.add(booking)
        db.commit()

        print(f"\n已建立預約 #{booking.id}，驗屋時間 {slot.slot_date} {slot.start_time:%H:%M}")
        print_owner_link(db, booking)


if __name__ == "__main__":
    main()
