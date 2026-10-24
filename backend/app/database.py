from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

if settings.is_sqlite:
    # sqlite:///xxx 之後的部分就是檔案路徑，先確保資料夾存在
    db_path = Path(settings.database_url.split("sqlite:///", 1)[1])
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.is_sqlite else {},
)

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")  # SQLite 預設不檢查外鍵
        cur.execute("PRAGMA journal_mode=WAL")  # 讀寫可同時進行（APP + 排程）
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_db_initialized() -> bool:
    return inspect(engine).has_table("projects")
