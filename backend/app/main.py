from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import models  # noqa: F401  確保所有 Model 已註冊
from app.config import settings
from app.database import Base, add_missing_columns, engine, is_db_initialized
from app.routers import (
    auth,
    authorizations,
    batches,
    booking,
    checklist,
    downloads,
    inspections,
    projects,
    system,
    users,
)

STORAGE_SUBDIRS = [
    "signatures", "authorizations", "reports", "attachments", "form_uploads", "outbox", "templates", "inspections",
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for sub in STORAGE_SUBDIRS:
        (settings.storage_dir / sub).mkdir(parents=True, exist_ok=True)
    # 已建立過的資料庫：自動補上新版本新增的資料表與欄位，既有資料保留
    if is_db_initialized():
        Base.metadata.create_all(engine)
        for col in add_missing_columns():
            print(f"  資料庫升級：新增欄位 {col}")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# 區網內使用；Expo Web 預覽時瀏覽器需要 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


app.include_router(system.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(batches.router)
app.include_router(checklist.router)
app.include_router(downloads.router)
app.include_router(booking.admin)
app.include_router(booking.public)
app.include_router(inspections.router)
app.include_router(authorizations.public)
app.include_router(authorizations.admin)
