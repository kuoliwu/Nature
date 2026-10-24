"""線上授權（委託代驗）

流程：
  0. 管理員：POST /bookings/{booking_id}/authorization-link 取得屋主專屬連結，傳給屋主
  1. 屋主：GET /authorize/{token} 填受託人資料並簽名 → POST /api/public/authorize/{token}
  2. 系統：寄「簽署邀請」Email 給受託人，內含 /sign/{token} 連結
  3. 受託人：GET /sign/{token} 簽名 → POST /api/public/sign/{token}
  4. 系統：簽名疊加到合約範本產生 PDF，Email 給屋主與受託人
"""

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AccessLink, Authorization, AuthorizationStatus, Booking, BookingStatus, LinkPurpose
from app.schemas import (
    AuthorizationOut,
    BookingSummary,
    OwnerAuthorizationIn,
    OwnerLinkOut,
    SignInviteInfo,
    TrusteeSignIn,
)
from app.services.links import get_or_create_owner_link, public_base_url
from app.services.mailer import Attachment, send_email_safely
from app.services.pdf import (
    CLAUSES,
    AuthorizationPdfData,
    generate_authorization_pdf,
    save_authorization_pdf,
)
from app.services.auth import require_permission
from app.services.security import hash_id_number
from app.services.signature import SignatureError, decode_signature, save_signature

public = APIRouter(tags=["線上授權（公開）"])
admin = APIRouter(tags=["線上授權（管理）"])
can_view = [Depends(require_permission("booking.view"))]
can_manage = [Depends(require_permission("booking.manage"))]

SIGN_PAGE = (Path(__file__).resolve().parent.parent / "templates" / "sign.html").read_text("utf-8")
OPEN_STATUSES = (AuthorizationStatus.PENDING_TRUSTEE, AuthorizationStatus.COMPLETED)


# ---------------------------------------------------------------------------
# 共用
# ---------------------------------------------------------------------------
def _render_sign_page(config: dict) -> HTMLResponse:
    # json.dumps 後把 < 轉義，避免資料中出現 </script> 跳出 script 區塊
    payload = json.dumps(config, ensure_ascii=False).replace("<", "\\u003c")
    return HTMLResponse(SIGN_PAGE.replace("__CONFIG__", payload))


def _booking_date(booking: Booking) -> str:
    slot = booking.slot
    return f"{slot.slot_date:%Y-%m-%d} {slot.start_time:%H:%M}-{slot.end_time:%H:%M}"


def _public_base_url(request: Request) -> str:
    # 有對外網址就用對外網址，受託人才能從外網開啟；否則沿用目前請求的位址
    return public_base_url() or str(request.base_url).rstrip("/")


def _get_owner_booking(db: Session, token: str) -> Booking:
    link = db.scalar(
        select(AccessLink).where(
            AccessLink.token == token, AccessLink.purpose == LinkPurpose.OWNER_AUTHORIZATION
        )
    )
    if link is None or link.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "連結無效")
    if link.expires_at < datetime.now():
        raise HTTPException(status.HTTP_410_GONE, "連結已過期，請聯絡管理單位重新取得")
    if link.booking.status != BookingStatus.BOOKED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "此預約已取消或已結束")
    return link.booking


def _get_by_token(db: Session, token: str) -> Authorization:
    auth = db.scalar(select(Authorization).where(Authorization.invite_token == token))
    if auth is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "簽署連結無效")
    if auth.status == AuthorizationStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "此授權書已完成簽署")
    if auth.status == AuthorizationStatus.CANCELLED:
        raise HTTPException(status.HTTP_410_GONE, "此簽署邀請已由屋主更新或取消，請使用最新收到的邀請信")
    if auth.status != AuthorizationStatus.PENDING_TRUSTEE:
        raise HTTPException(status.HTTP_410_GONE, "此簽署邀請已失效")
    if auth.invite_expires_at and auth.invite_expires_at < datetime.now():
        auth.status = AuthorizationStatus.EXPIRED
        db.commit()
        raise HTTPException(status.HTTP_410_GONE, "簽署連結已過期，請聯絡屋主重新發送")
    return auth


def _issue_invite(auth: Authorization) -> None:
    auth.invite_token = secrets.token_urlsafe(32)
    auth.invite_sent_at = datetime.now()
    auth.invite_expires_at = datetime.now() + timedelta(days=settings.invite_expire_days)


def _queue_invite_email(tasks: BackgroundTasks, auth: Authorization, base_url: str) -> None:
    booking = auth.booking
    link = f"{base_url}/sign/{auth.invite_token}"
    body = (
        f"{auth.trustee_name} 您好：\n\n"
        f"屋主 {auth.owner_name} 委託您代為辦理以下房屋的驗屋事宜，並已完成簽名：\n\n"
        f"  建案：{booking.unit.project.name}\n"
        f"  戶別：{booking.unit.unit_no}\n"
        f"  驗屋時間：{_booking_date(booking)}\n\n"
        f"請點選以下連結，確認內容並完成您的數位簽名：\n{link}\n\n"
        f"此連結將於 {auth.invite_expires_at:%Y-%m-%d %H:%M} 失效。\n"
        f"如果您不認識這位屋主，請忽略此信。\n"
    )
    tasks.add_task(send_email_safely, [auth.trustee_email], "【驗屋授權】簽署邀請", body)


def _queue_voided_email(tasks: BackgroundTasks, old: Authorization) -> None:
    booking = old.booking
    body = (
        f"{old.trustee_name} 您好：\n\n"
        f"屋主 {old.owner_name} 已更新以下房屋的驗屋代理授權，"
        f"先前寄給您的簽署邀請{'與已簽署的授權書' if old.status == AuthorizationStatus.COMPLETED else ''}已作廢：\n\n"
        f"  建案：{booking.unit.project.name}\n"
        f"  戶別：{booking.unit.unit_no}\n\n"
        f"您不需要再進行任何操作。如有疑問請與屋主聯絡。\n"
    )
    tasks.add_task(send_email_safely, [old.trustee_email], "【驗屋授權】授權已更新，先前邀請作廢", body)


# ---------------------------------------------------------------------------
# 屋主
# ---------------------------------------------------------------------------
@public.get("/authorize/{token}", response_class=HTMLResponse, include_in_schema=False)
def owner_page(token: str):
    return _render_sign_page({"mode": "owner", "token": token, "clauses": CLAUSES})


@public.get("/api/public/authorize/{token}", response_model=BookingSummary)
def booking_summary(token: str, db: Session = Depends(get_db)):
    booking = _get_owner_booking(db, token)
    unit = booking.unit
    return BookingSummary(
        project_name=unit.project.name,
        unit_no=unit.unit_no,
        inspection_date=_booking_date(booking),
        require_id_verification=bool(booking.slot.batch.require_id_verification and unit.owner_id_hash),
    )


@public.post("/api/public/authorize/{token}", response_model=AuthorizationOut, status_code=201)
def owner_sign(
    token: str,
    body: OwnerAuthorizationIn,
    request: Request,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    booking = _get_owner_booking(db, token)
    unit = booking.unit

    # 強制身分證驗證：防止選錯戶別或冒名
    if booking.slot.batch.require_id_verification and unit.owner_id_hash:
        if not body.owner_id_number or hash_id_number(body.owner_id_number) != unit.owner_id_hash:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "身分證字號與此戶別登記資料不符")

    try:
        owner_png = decode_signature(body.owner_signature)
    except SignatureError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    # 以最後一次送出為準：先前的授權（不論是否已完成）一律作廢，舊的受託人連結隨之失效。
    # 作廢的紀錄與 PDF 仍保留，管理端可查詢。
    previous = db.scalars(
        select(Authorization).where(
            Authorization.booking_id == booking.id, Authorization.status.in_(OPEN_STATUSES)
        )
    ).all()
    for old in previous:
        if old.trustee_email.lower() != body.trustee_email.lower():
            _queue_voided_email(tasks, old)  # 先排入（讀取作廢前的狀態），回應後才寄出
        old.status = AuthorizationStatus.CANCELLED

    auth = Authorization(
        booking_id=booking.id,
        owner_name=body.owner_name,
        owner_email=body.owner_email,
        trustee_name=body.trustee_name,
        trustee_email=body.trustee_email,
        owner_signed_at=datetime.now(),
        status=AuthorizationStatus.PENDING_TRUSTEE,
    )
    _issue_invite(auth)
    booking.is_delegated = True
    db.add(auth)
    db.flush()  # 取得 auth.id 作為檔名
    auth.owner_signature_path = save_signature(owner_png, f"auth{auth.id}_owner")
    db.commit()

    _queue_invite_email(tasks, auth, _public_base_url(request))
    return auth


# ---------------------------------------------------------------------------
# 受託人
# ---------------------------------------------------------------------------
@public.get("/sign/{token}", response_class=HTMLResponse, include_in_schema=False)
def trustee_page(token: str):
    return _render_sign_page({"mode": "trustee", "token": token, "clauses": CLAUSES})


@public.get("/api/public/sign/{token}", response_model=SignInviteInfo)
def invite_info(token: str, db: Session = Depends(get_db)):
    auth = _get_by_token(db, token)
    booking = auth.booking
    return SignInviteInfo(
        status=auth.status.value,
        owner_name=auth.owner_name,
        trustee_name=auth.trustee_name or "",
        trustee_email=auth.trustee_email,
        project_name=booking.unit.project.name,
        unit_no=booking.unit.unit_no,
        inspection_date=_booking_date(booking),
        expires_at=auth.invite_expires_at,
    )


@public.post("/api/public/sign/{token}", response_model=AuthorizationOut)
def trustee_sign(token: str, body: TrusteeSignIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    auth = _get_by_token(db, token)
    try:
        trustee_png = decode_signature(body.trustee_signature)
    except SignatureError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    auth.trustee_signature_path = save_signature(trustee_png, f"auth{auth.id}_trustee")
    auth.trustee_signed_at = datetime.now()

    booking, unit = auth.booking, auth.booking.unit
    pdf = generate_authorization_pdf(
        AuthorizationPdfData(
            authorization_id=auth.id,
            project_name=unit.project.name,
            unit_no=unit.unit_no,
            unit_address=unit.address or "",
            inspection_date=_booking_date(booking),
            owner_name=auth.owner_name,
            trustee_name=auth.trustee_name or "",
            trustee_email=auth.trustee_email,
            owner_signature=settings.storage_dir / auth.owner_signature_path,
            trustee_signature=settings.storage_dir / auth.trustee_signature_path,
            owner_signed_at=auth.owner_signed_at,
            trustee_signed_at=auth.trustee_signed_at,
        )
    )
    auth.pdf_path = save_authorization_pdf(pdf, auth.id)
    auth.status = AuthorizationStatus.COMPLETED
    auth.completed_at = datetime.now()
    db.commit()

    filename = Path(auth.pdf_path).name
    body_text = (
        f"您好：\n\n{unit.project.name} {unit.unit_no} 的驗屋代理授權書已由雙方完成簽署，"
        f"授權書 PDF 請見附件。\n\n"
        f"  委託人（屋主）：{auth.owner_name}\n"
        f"  受託人：{auth.trustee_name}\n"
        f"  驗屋時間：{_booking_date(booking)}\n"
    )
    tasks.add_task(
        send_email_safely,
        [auth.owner_email, auth.trustee_email],
        "【驗屋授權】授權書簽署完成",
        body_text,
        [Attachment(filename, pdf)],
    )
    return auth


# ---------------------------------------------------------------------------
# 管理端
# ---------------------------------------------------------------------------
@admin.post("/bookings/{booking_id}/authorization-link", response_model=OwnerLinkOut, dependencies=can_manage)
def create_owner_link(booking_id: int, request: Request, db: Session = Depends(get_db)):
    """產生（或沿用）屋主授權頁連結。public_url 只有在設定對外網址或啟動通道時才會有值。"""
    booking = db.get(Booking, booking_id)
    if booking is None or booking.status != BookingStatus.BOOKED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到有效的預約")
    link = get_or_create_owner_link(db, booking)
    path = f"/authorize/{link.token}"
    public = public_base_url()
    return OwnerLinkOut(
        token=link.token,
        expires_at=link.expires_at,
        public_url=f"{public}{path}" if public else None,
        lan_url=f"{str(request.base_url).rstrip('/')}{path}",
    )


@admin.get("/authorizations", response_model=list[AuthorizationOut], dependencies=can_view)
def list_authorizations(
    booking_id: int | None = None,
    status_: AuthorizationStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    query = select(Authorization).order_by(Authorization.id.desc())
    if booking_id is not None:
        query = query.where(Authorization.booking_id == booking_id)
    if status_ is not None:
        query = query.where(Authorization.status == status_)
    return db.scalars(query).all()


def _get_auth(db: Session, authorization_id: int) -> Authorization:
    auth = db.get(Authorization, authorization_id)
    if auth is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到授權書")
    return auth


@admin.get("/authorizations/{authorization_id}/pdf", response_class=FileResponse, dependencies=can_view)
def download_pdf(authorization_id: int, db: Session = Depends(get_db)):
    auth = _get_auth(db, authorization_id)
    if not auth.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授權書尚未完成簽署")
    path = settings.storage_dir / auth.pdf_path
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@admin.post("/authorizations/{authorization_id}/resend-invite", response_model=AuthorizationOut, dependencies=can_manage)
def resend_invite(
    authorization_id: int, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """重新產生連結（舊連結立即失效）並再寄一次；過期的邀請也可以用這個重新啟用"""
    auth = _get_auth(db, authorization_id)
    if auth.status not in (AuthorizationStatus.PENDING_TRUSTEE, AuthorizationStatus.EXPIRED):
        raise HTTPException(status.HTTP_409_CONFLICT, "只有等待受託人簽名或已過期的授權書可以重寄")
    auth.status = AuthorizationStatus.PENDING_TRUSTEE
    _issue_invite(auth)
    db.commit()
    _queue_invite_email(tasks, auth, _public_base_url(request))
    return auth


@admin.post("/authorizations/{authorization_id}/cancel", response_model=AuthorizationOut, dependencies=can_manage)
def cancel_authorization(authorization_id: int, db: Session = Depends(get_db)):
    auth = _get_auth(db, authorization_id)
    if auth.status == AuthorizationStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "已完成的授權書不能取消")
    auth.status = AuthorizationStatus.CANCELLED
    db.commit()
    return auth
