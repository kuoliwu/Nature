"""對外連結：屋主授權頁的 token 連結，以及對外網址的判斷"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AccessLink, Booking, LinkPurpose


def public_base_url() -> str | None:
    """對外網址：優先用 .env 的 PUBLIC_BASE_URL，其次用 run.py --tunnel 寫入的快速通道網址"""
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    if settings.public_url_file.is_file():
        url = settings.public_url_file.read_text("utf-8").strip()
        return url.rstrip("/") or None
    return None


def get_or_create_owner_link(db: Session, booking: Booking) -> AccessLink:
    """同一筆預約重複產生時沿用尚未過期的連結，避免先前傳出去的連結失效"""
    link = db.scalar(
        select(AccessLink)
        .where(
            AccessLink.booking_id == booking.id,
            AccessLink.purpose == LinkPurpose.OWNER_AUTHORIZATION,
            AccessLink.revoked_at.is_(None),
            AccessLink.expires_at > datetime.now(),
        )
        .order_by(AccessLink.id.desc())
    )
    if link is None:
        link = AccessLink(
            token=secrets.token_urlsafe(24),
            purpose=LinkPurpose.OWNER_AUTHORIZATION,
            booking_id=booking.id,
            expires_at=datetime.now() + timedelta(days=settings.owner_link_expire_days),
        )
        db.add(link)
        db.commit()
    return link
