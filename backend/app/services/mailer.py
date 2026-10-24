"""寄信。未設定 SMTP_HOST 時不會真的寄出，而是存成 storage/outbox/*.eml（可用 Outlook / 瀏覽器開啟檢查）"""

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime_type: str = "application/pdf"


def build_message(to: list[str], subject: str, body: str, attachments: list[Attachment] = ()) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from or settings.smtp_user or "noreply@localhost"
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    for a in attachments:
        maintype, subtype = a.mime_type.split("/", 1)
        msg.add_attachment(a.content, maintype=maintype, subtype=subtype, filename=a.filename)
    return msg


def send_email(to: list[str], subject: str, body: str, attachments: list[Attachment] = ()) -> None:
    to = [addr for addr in to if addr]
    if not to:
        return
    msg = build_message(to, subject, body, attachments)

    if not settings.smtp_host:
        outbox = settings.storage_dir / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        path = outbox / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.eml"
        path.write_bytes(msg.as_bytes())
        log.info("SMTP 未設定，信件已存到 %s", path)
        return

    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=context)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    with server:
        if settings.smtp_port != 465:
            server.starttls(context=context)
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    log.info("已寄出「%s」給 %s", subject, ", ".join(to))


def send_email_safely(*args, **kwargs) -> None:
    """給 BackgroundTasks 用：寄信失敗只記錄，不影響已完成的 API 回應"""
    try:
        send_email(*args, **kwargs)
    except Exception:
        log.exception("寄信失敗")
