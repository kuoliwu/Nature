"""每日備份：資料庫（SQLite 線上備份，寫入中也一致）＋ storage 檔案（只複製新增 / 變更的）

BACKUP_DIR 建議設到另一顆硬碟或雲端同步資料夾（例如 OneDrive），電腦硬碟壞掉時資料才救得回來。
"""

import logging
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)


def _db_path() -> Path | None:
    if not settings.is_sqlite:
        return None
    return Path(settings.database_url.split("sqlite:///", 1)[1])


def backup_database(now: datetime | None = None) -> Path | None:
    src = _db_path()
    if src is None or not src.is_file():
        return None
    now = now or datetime.now()
    target_dir = settings.backup_dir / "database"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"inspection-{now:%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(src) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    _prune(target_dir, now)
    return target


def _prune(folder: Path, now: datetime) -> None:
    cutoff = now - timedelta(days=settings.backup_keep_days)
    for f in folder.glob("inspection-*.db"):
        try:
            stamp = datetime.strptime(f.stem.removeprefix("inspection-"), "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if stamp < cutoff:
            f.unlink(missing_ok=True)


def mirror_storage() -> int:
    """把 storage/ 鏡像到備份資料夾；只複製新增或大小 / 時間不同的檔案。回傳複製的檔案數"""
    src_root = settings.storage_dir
    dst_root = settings.backup_dir / "storage"
    copied = 0
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        dst = dst_root / src.relative_to(src_root)
        st = src.stat()
        if dst.exists():
            dt = dst.stat()
            if dt.st_size == st.st_size and int(dt.st_mtime) >= int(st.st_mtime):
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


def run_backup() -> dict:
    db_file = backup_database()
    files = mirror_storage()
    log.info("備份完成：資料庫 %s，檔案 %d 個", db_file, files)
    return {"database": str(db_file) if db_file else None, "files_copied": files, "backup_dir": str(settings.backup_dir)}
