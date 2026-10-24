from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import ChangePasswordIn, LoginIn, LoginOut, SetupIn, UserOut
from app.services.auth import (
    check_login_allowed,
    clear_login_failures,
    create_access_token,
    get_current_user,
    hash_password,
    normalize_phone,
    record_login_failure,
    user_permissions,
    verify_password,
)
from app.services.security import require_admin_key

router = APIRouter(prefix="/auth", tags=["登入"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        phone=user.phone,
        role=user.role.value,
        is_active=user.is_active,
        permissions=sorted(user_permissions(user)),
        created_at=user.created_at,
    )


def login_response(user: User) -> LoginOut:
    token, expires = create_access_token(user)
    return LoginOut(access_token=token, expires_at=expires, user=user_out(user))


@router.post(
    "/setup",
    response_model=LoginOut,
    status_code=201,
    dependencies=[Depends(require_admin_key)],
    summary="建立第一位管理者（只有在還沒有任何帳號時可用）",
)
def setup(body: SetupIn, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(status.HTTP_409_CONFLICT, "已經有管理者帳號，請直接登入")
    user = User(
        name=body.name,
        phone=normalize_phone(body.phone),
        password_hash=hash_password(body.password),
        role=UserRole.SUPER_ADMIN,
    )
    db.add(user)
    db.commit()
    return login_response(user)


@router.post("/login", response_model=LoginOut, summary="手機號碼 + 密碼登入")
def login(body: LoginIn, db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    check_login_allowed(phone)
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None or not verify_password(body.password, user.password_hash):
        record_login_failure(phone)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "手機號碼或密碼錯誤")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "此帳號已停用，請聯絡管理者")
    clear_login_failures(phone)
    return login_response(user)


@router.get("/me", response_model=UserOut, summary="目前登入的帳號")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/change-password", response_model=LoginOut, summary="修改自己的密碼（回傳新的登入憑證）")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目前的密碼不正確")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return login_response(user)
