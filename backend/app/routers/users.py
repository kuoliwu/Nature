from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PERMISSIONS, User, UserPermission, UserRole
from app.routers.auth import user_out
from app.schemas import PermissionOut, UserCreateIn, UserOut, UserUpdateIn
from app.services.auth import get_current_user, hash_password, normalize_phone, require_permission

router = APIRouter(tags=["人員與權限"])
manage = require_permission("user.manage")


def _validate_permissions(codes: list[str]) -> list[str]:
    unknown = set(codes) - set(PERMISSIONS)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"未知的權限：{', '.join(sorted(unknown))}")
    return sorted(set(codes))


def _set_permissions(user: User, codes: list[str]) -> None:
    # 只增刪有差異的項目；整批刪除再新增會在同一次 flush 撞到唯一鍵
    wanted = set(_validate_permissions(codes))
    for p in list(user.permissions):
        if p.permission not in wanted:
            user.permissions.remove(p)
    existing = {p.permission for p in user.permissions}
    user.permissions.extend(UserPermission(permission=c) for c in sorted(wanted - existing))


def _active_super_admins(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.SUPER_ADMIN, User.is_active.is_(True))
    )


@router.get("/permissions", response_model=list[PermissionOut], summary="所有可設定的權限")
def list_permissions(_: User = Depends(get_current_user)):
    return [PermissionOut(code=c, label=label) for c, label in PERMISSIONS.items()]


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(manage)])
def list_users(db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/users", response_model=UserOut, status_code=201, dependencies=[Depends(manage)])
def create_user(body: UserCreateIn, db: Session = Depends(get_db)):
    user = User(
        name=body.name,
        phone=normalize_phone(body.phone),
        password_hash=hash_password(body.password),
        role=UserRole(body.role),
    )
    _set_permissions(user, body.permissions)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "此手機號碼已有帳號")
    return user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateIn,
    db: Session = Depends(get_db),
    current: User = Depends(manage),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到此帳號")

    demoting = body.role == "staff" and user.role == UserRole.SUPER_ADMIN
    deactivating = body.is_active is False and user.is_active
    if user.id == current.id and (demoting or deactivating):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用或降級自己的帳號")
    if (demoting or deactivating) and user.role == UserRole.SUPER_ADMIN and _active_super_admins(db) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "至少要保留一位啟用中的最高管理者")

    if body.name is not None:
        user.name = body.name
    if body.phone is not None:
        user.phone = normalize_phone(body.phone)
    if body.role is not None:
        user.role = UserRole(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.permissions is not None:
        _set_permissions(user, body.permissions)
    if body.password:
        user.password_hash = hash_password(body.password)  # 舊的登入憑證會一併失效

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "此手機號碼已有帳號")
    return user_out(user)
