from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import settings
from app.routers import auth, authorizations, projects, system, users

STORAGE_SUBDIRS = [
    "signatures", "authorizations", "reports", "attachments", "form_uploads", "outbox", "templates",
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for sub in STORAGE_SUBDIRS:
        (settings.storage_dir / sub).mkdir(parents=True, exist_ok=True)
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
app.include_router(authorizations.public)
app.include_router(authorizations.admin)
