"""產生（或沿用）某筆預約的屋主授權頁連結，複製後傳給屋主（LINE / 簡訊 / Email）。

用法（在 backend/ 目錄下）：
    python -m scripts.owner_link 3
"""

import argparse
import sys

from app.database import SessionLocal
from app.models import Booking, BookingStatus
from app.services.links import get_or_create_owner_link, public_base_url

LAN_HOST = "192.168.68.109:8000"


def print_owner_link(db, booking: Booking) -> None:
    link = get_or_create_owner_link(db, booking)
    path = f"/authorize/{link.token}"
    public = public_base_url()
    unit = booking.unit
    print(f"\n預約 #{booking.id}：{unit.project.name} {unit.unit_no}（連結有效至 {link.expires_at:%Y-%m-%d}）")
    if public:
        print(f"  外網連結（傳給屋主）：{public}{path}")
    else:
        print("  外網連結：通道未啟動，請改用 python run.py --tunnel 啟動後端後再執行一次")
    print(f"  區網連結（測試用）  ：http://{LAN_HOST}{path}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("booking_id", type=int)
    args = parser.parse_args()

    with SessionLocal() as db:
        booking = db.get(Booking, args.booking_id)
        if booking is None or booking.status != BookingStatus.BOOKED:
            sys.exit(f"找不到有效的預約 #{args.booking_id}")
        print_owner_link(db, booking)


if __name__ == "__main__":
    main()
