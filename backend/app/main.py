from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app import models  # noqa: F401  確保所有 Model 已註冊
from app.config import BASE_DIR, settings
from app.database import Base, SessionLocal, add_missing_columns, engine, is_db_initialized
from app.routers import (
    auth,
    authorizations,
    batches,
    booking,
    checklist,
    downloads,
    handbook,
    inspections,
    projects,
    reports,
    sheets,
    system,
    users,
)
from app.seed import migrate_checklist_services
from app.services.handbook import migrate_template as migrate_handbook_template
from app.services.network import is_external, is_local_only_path
from app.services.scheduler import start_scheduler, stop_scheduler

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
        with SessionLocal() as db:
            if migrate_checklist_services(db):
                print("  資料庫升級：既有建案的檢查清單設為「驗屋」清單")
            if migrate_handbook_template(db):
                print("  資料庫升級：住屋手冊範本改為第 2 版（只留保固、聯絡資訊，皆選填）")
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)



@app.middleware("http")
async def hide_local_only_from_internet(request: Request, call_next):
    """經通道從外網連進來時，API 文件與系統金鑰功能（初始化、建立第一位管理者）一律當作不存在"""
    if is_local_only_path(request.url.path) and is_external(request):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    response = await call_next(request)
    if is_external(request):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")  # 下載連結含 token，不外流到其他網站
    return response


# Expo Web 預覽時瀏覽器需要 CORS（登入用 Authorization 標頭、不用 cookie，允許任何來源沒有 CSRF 問題）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBAPP_DIR = BASE_DIR / "webapp"  # mobile 執行 npm run build:web 產生


@app.get("/", include_in_schema=False)
def root():
    # 有電腦版網頁時打開 APP，否則到 API 文件
    return RedirectResponse("/app/" if WEBAPP_DIR.is_dir() else "/docs")


@app.get("/app", include_in_schema=False)
@app.get("/app/{path:path}", include_in_schema=False)
def webapp(path: str = ""):
    """電腦版（網頁版 APP）。實體檔案直接回傳；其他路徑（APP 內的頁面）回傳 index.html"""
    if not WEBAPP_DIR.is_dir():
        raise HTTPException(404, "尚未建置網頁版：請在 mobile 資料夾執行 npm run build:web")
    target = (WEBAPP_DIR / path).resolve()
    if path and target.is_file() and WEBAPP_DIR.resolve() in target.parents and target.name != "index.html":
        return FileResponse(target)
    # index.html 不快取：重新建置後手機一重新整理就是新版（JS 檔名含雜湊，可以快取）
    return FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})


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
app.include_router(reports.router)
app.include_router(handbook.router)
app.include_router(sheets.router)
app.include_router(authorizations.public)
app.include_router(authorizations.admin)
