"""短效下載連結（不需登入 header，憑連結中的 token）。只掛在管理用的 8000，不經過對外通道。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.routers.projects import units_export_response
from app.services.auth import read_download_token

router = APIRouter(tags=["下載"])


@router.get("/downloads/{token}", include_in_schema=False)
def download(token: str, db: Session = Depends(get_db)):
    payload = read_download_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_410_GONE, "下載連結已過期，請回到 APP 重新匯出")
    if payload.get("kind") == "units":
        project = db.get(Project, payload["project_id"])
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
        return units_export_response(db, project, payload["fmt"])
    raise HTTPException(status.HTTP_404_NOT_FOUND, "連結無效")
