"""各建案的檢查項目清單：類別 → 項目 → 檢查點。
已有檢查紀錄的不能刪除（會遺失歷史），只能停用；停用後新的驗屋不會出現，舊紀錄保留。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InspectionCategory, InspectionCheckPoint, InspectionItem, InspectionResult
from app.routers.projects import get_project_or_404
from app.schemas import ChecklistCategoryOut, ChecklistItemIn, ChecklistUpdate, NameIn
from app.seed import ensure_project_checklist
from app.services.auth import get_current_user, require_permission

router = APIRouter(tags=["檢查項目清單"], dependencies=[Depends(get_current_user)])
manage = [Depends(require_permission("project.manage"))]


def _get(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    # 公司範本（project_id 為 NULL）不能從這裡修改
    category = obj if isinstance(obj, InspectionCategory) else (
        obj.category if isinstance(obj, InspectionItem) else obj.item.category if obj else None
    )
    if obj is None or category.project_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"找不到此{label}")
    return obj


def _result_count(db: Session, point_ids: list[int]) -> int:
    if not point_ids:
        return 0
    return db.scalar(select(func.count(InspectionResult.id)).where(InspectionResult.check_point_id.in_(point_ids)))


def _apply(obj, body: ChecklistUpdate) -> None:
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(obj, key, value)


def _next_order(objs) -> int:
    return max((o.sort_order for o in objs), default=-1) + 1


@router.get("/projects/{project_id}/checklist", response_model=list[ChecklistCategoryOut])
def get_checklist(project_id: int, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    ensure_project_checklist(db, project)
    return project.checklist


@router.post("/projects/{project_id}/checklist/categories", response_model=ChecklistCategoryOut, status_code=201, dependencies=manage)
def add_category(project_id: int, body: NameIn, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    ensure_project_checklist(db, project)
    category = InspectionCategory(
        code=f"p{project.id}-{uuid.uuid4().hex[:8]}",
        name=body.name,
        project_id=project.id,
        sort_order=_next_order(project.checklist),
    )
    db.add(category)
    db.commit()
    return category


@router.patch("/checklist/categories/{category_id}", response_model=ChecklistCategoryOut, dependencies=manage)
def update_category(category_id: int, body: ChecklistUpdate, db: Session = Depends(get_db)):
    category = _get(db, InspectionCategory, category_id, "類別")
    _apply(category, body)
    db.commit()
    return category


@router.delete("/checklist/categories/{category_id}", status_code=204, dependencies=manage)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = _get(db, InspectionCategory, category_id, "類別")
    point_ids = [cp.id for item in category.items for cp in item.check_points]
    if _result_count(db, point_ids):
        raise HTTPException(status.HTTP_409_CONFLICT, "此類別已有檢查紀錄，不能刪除，請改為停用")
    db.delete(category)
    db.commit()


@router.post("/checklist/categories/{category_id}/items", response_model=ChecklistCategoryOut, status_code=201, dependencies=manage)
def add_item(category_id: int, body: ChecklistItemIn, db: Session = Depends(get_db)):
    category = _get(db, InspectionCategory, category_id, "類別")
    if any(i.name == body.name for i in category.items):
        raise HTTPException(status.HTTP_409_CONFLICT, f"「{body.name}」已存在")
    names = body.check_points
    if names is None:
        # 沿用同類別第一個項目的檢查點，例如新增「浴室窗」自動帶入膠條 / 密合度 / 五金
        first = next((i for i in category.items if i.is_active), None)
        names = [cp.name for cp in first.check_points if cp.is_active] if first else []
    item = InspectionItem(name=body.name, sort_order=_next_order(category.items))
    item.check_points = [InspectionCheckPoint(name=n, sort_order=i) for i, n in enumerate(dict.fromkeys(names)) if n.strip()]
    category.items.append(item)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/checklist/items/{item_id}", response_model=ChecklistCategoryOut, dependencies=manage)
def update_item(item_id: int, body: ChecklistUpdate, db: Session = Depends(get_db)):
    item = _get(db, InspectionItem, item_id, "項目")
    if body.name and any(i.name == body.name and i.id != item.id for i in item.category.items):
        raise HTTPException(status.HTTP_409_CONFLICT, f"「{body.name}」已存在")
    _apply(item, body)
    db.commit()
    return item.category


@router.delete("/checklist/items/{item_id}", response_model=ChecklistCategoryOut, dependencies=manage)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = _get(db, InspectionItem, item_id, "項目")
    if _result_count(db, [cp.id for cp in item.check_points]):
        raise HTTPException(status.HTTP_409_CONFLICT, "此項目已有檢查紀錄，不能刪除，請改為停用")
    category = item.category
    category.items.remove(item)
    db.commit()
    return category


@router.post("/checklist/items/{item_id}/points", response_model=ChecklistCategoryOut, status_code=201, dependencies=manage)
def add_point(item_id: int, body: NameIn, db: Session = Depends(get_db)):
    item = _get(db, InspectionItem, item_id, "項目")
    if any(cp.name == body.name for cp in item.check_points):
        raise HTTPException(status.HTTP_409_CONFLICT, f"「{body.name}」已存在")
    item.check_points.append(InspectionCheckPoint(name=body.name, sort_order=_next_order(item.check_points)))
    db.commit()
    return item.category


@router.patch("/checklist/points/{point_id}", response_model=ChecklistCategoryOut, dependencies=manage)
def update_point(point_id: int, body: ChecklistUpdate, db: Session = Depends(get_db)):
    point = _get(db, InspectionCheckPoint, point_id, "檢查點")
    if body.name and any(cp.name == body.name and cp.id != point.id for cp in point.item.check_points):
        raise HTTPException(status.HTTP_409_CONFLICT, f"「{body.name}」已存在")
    _apply(point, body)
    db.commit()
    return point.item.category


@router.delete("/checklist/points/{point_id}", response_model=ChecklistCategoryOut, dependencies=manage)
def delete_point(point_id: int, db: Session = Depends(get_db)):
    point = _get(db, InspectionCheckPoint, point_id, "檢查點")
    if _result_count(db, [point.id]):
        raise HTTPException(status.HTTP_409_CONFLICT, "此檢查點已有檢查紀錄，不能刪除，請改為停用")
    item = point.item
    item.check_points.remove(point)
    db.commit()
    return item.category
