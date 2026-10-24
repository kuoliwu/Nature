from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, inspect, select

from app import models  # noqa: F401  確保所有 Model 已註冊到 Base.metadata
from app.config import settings
from app.database import Base, SessionLocal, engine, is_db_initialized
from app.models import User
from app.schemas import DBStatusOut, HealthOut, InitDBIn, InitDBOut, TableCount
from app.seed import seed_inspection_checklist
from app.services.security import require_admin_key

router = APIRouter(tags=["系統"])


@router.get("/health", response_model=HealthOut, summary="連線測試（不需金鑰）")
def health():
    initialized = is_db_initialized()
    needs_setup = False
    if initialized:
        with SessionLocal() as db:
            needs_setup = not db.scalar(select(func.count(User.id)))
    return HealthOut(
        status="ok",
        app=settings.app_name,
        db_initialized=initialized,
        needs_setup=needs_setup,
        server_time=datetime.now(),
    )


@router.post(
    "/init-db",
    response_model=InitDBOut,
    dependencies=[Depends(require_admin_key)],
    summary="建立 / 重建本地資料庫",
)
def init_db(body: InitDBIn | None = None):
    body = body or InitDBIn()
    was_initialized = is_db_initialized()

    if body.reset:
        if body.confirm != "RESET":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'reset=true 時 confirm 必須為 "RESET"')
        Base.metadata.drop_all(engine)

    # create_all 只會建立尚不存在的資料表，重複呼叫是安全的
    Base.metadata.create_all(engine)

    seeded = None
    if body.seed_checklist:
        with SessionLocal() as db:
            seeded = seed_inspection_checklist(db)

    if body.reset:
        message = "資料庫已清空並重新建立"
    elif was_initialized:
        message = "資料庫已存在，已補齊缺少的資料表"
    else:
        message = "資料庫建立完成"

    return InitDBOut(
        message=message,
        was_initialized=was_initialized,
        tables=sorted(Base.metadata.tables.keys()),
        seeded=seeded,
    )


@router.get(
    "/db/status",
    response_model=DBStatusOut,
    dependencies=[Depends(require_admin_key)],
    summary="各資料表筆數",
)
def db_status():
    existing = set(inspect(engine).get_table_names())
    counts: list[TableCount] = []
    with SessionLocal() as db:
        for name, table in sorted(Base.metadata.tables.items()):
            if name in existing:
                counts.append(TableCount(table=name, rows=db.scalar(select(func.count()).select_from(table))))
    return DBStatusOut(
        db_initialized=is_db_initialized(),
        database=engine.url.render_as_string(hide_password=True),
        tables=counts,
    )
