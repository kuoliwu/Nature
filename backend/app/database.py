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


def add_missing_columns() -> list[str]:
    """
    輕量的資料庫升級：Model 新增欄位時，對既有資料表執行 ALTER TABLE ADD COLUMN，
    已有的資料都會保留。新增的欄位必須可為 NULL，或在 Model 上設定 server_default。
    回傳新增的欄位清單（「表.欄位」）。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # 整張表不存在的交給 create_all
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                if not col.nullable and col.server_default is None:
                    raise RuntimeError(f"{table.name}.{col.name} 不可為 NULL 又沒有 server_default，無法自動新增")
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'
                if col.server_default is not None:
                    ddl += f" DEFAULT {col.server_default.arg.text}"
                if not col.nullable:
                    ddl += " NOT NULL"
                fk = next(iter(col.foreign_keys), None)
                if fk is not None:
                    ddl += f' REFERENCES "{fk.column.table.name}"("{fk.column.name}")'
                    if fk.ondelete:
                        ddl += f" ON DELETE {fk.ondelete}"
                conn.exec_driver_sql(ddl)
                added.append(f"{table.name}.{col.name}")
    return added
