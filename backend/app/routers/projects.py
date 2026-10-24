from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import InspectionCategory, InspectionItem, Project, Unit
from app.schemas import InspectionCategoryOut, ProjectIn, ProjectOut, UnitIn, UnitOut
from app.services.security import hash_id_number, require_admin_key

router = APIRouter(dependencies=[Depends(require_admin_key)])


def _get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到建案")
    return project


@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["建案"])
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    return project


@router.get("/projects", response_model=list[ProjectOut], tags=["建案"])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.id.desc())).all()


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["建案"])
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _get_project(db, project_id)


@router.post("/projects/{project_id}/units", response_model=UnitOut, status_code=201, tags=["戶別"])
def create_unit(project_id: int, body: UnitIn, db: Session = Depends(get_db)):
    _get_project(db, project_id)
    data = body.model_dump(exclude={"owner_id_number"})
    unit = Unit(project_id=project_id, **data)
    if body.owner_id_number:
        unit.owner_id_hash = hash_id_number(body.owner_id_number)
    db.add(unit)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"戶別 {body.unit_no} 已存在")
    return unit


@router.get("/projects/{project_id}/units", response_model=list[UnitOut], tags=["戶別"])
def list_units(project_id: int, db: Session = Depends(get_db)):
    _get_project(db, project_id)
    return db.scalars(select(Unit).where(Unit.project_id == project_id).order_by(Unit.unit_no)).all()


@router.get("/inspection/checklist", response_model=list[InspectionCategoryOut], tags=["檢查項目"])
def get_checklist(db: Session = Depends(get_db)):
    return db.scalars(
        select(InspectionCategory)
        .options(selectinload(InspectionCategory.items).selectinload(InspectionItem.check_points))
        .order_by(InspectionCategory.sort_order)
    ).all()
