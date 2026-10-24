"""檢查項目：公司範本（project_id 為 NULL）與「新建案複製範本」。可重複執行，不會重複建立。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InspectionCategory, InspectionCheckPoint, InspectionItem, Project

WINDOW_CHECKS = ["膠條", "密合度", "五金"]
PLUMBING_AREAS = ["浴室", "陽台", "廚房"]

DEFAULT_CHECKLIST: list[dict] = [
    {
        "code": "windows",
        "name": "窗戶",
        "items": {
            "陽台窗": WINDOW_CHECKS,
            "房間窗": WINDOW_CHECKS,
            "工作陽台門": WINDOW_CHECKS,
            "其他": WINDOW_CHECKS,
        },
    },
    {
        "code": "plumbing",
        "name": "水電",
        "items": {
            "給水": PLUMBING_AREAS,
            "排水": PLUMBING_AREAS,
        },
    },
    {
        "code": "other",
        "name": "其他",
        "items": {
            "其他": ["狀況說明"],
        },
    },
]


# 早期版本的範本類別名稱，補齊範本時改成目前的名稱
LEGACY_NAMES = {"窗類", "水電類"}


def seed_inspection_checklist(db: Session) -> dict[str, int]:
    """建立或補齊公司範本"""
    added = {"categories": 0, "items": 0, "check_points": 0}

    for cat_order, cat_data in enumerate(DEFAULT_CHECKLIST):
        category = db.scalar(
            select(InspectionCategory).where(
                InspectionCategory.code == cat_data["code"], InspectionCategory.project_id.is_(None)
            )
        )
        if category is None:
            category = InspectionCategory(code=cat_data["code"], name=cat_data["name"], sort_order=cat_order)
            db.add(category)
            added["categories"] += 1
        elif category.name in LEGACY_NAMES:
            category.name = cat_data["name"]

        existing_items = {item.name: item for item in category.items}
        for item_order, (item_name, points) in enumerate(cat_data["items"].items()):
            item = existing_items.get(item_name)
            if item is None:
                item = InspectionItem(name=item_name, sort_order=item_order)
                category.items.append(item)
                added["items"] += 1

            existing_points = {cp.name for cp in item.check_points}
            for cp_order, cp_name in enumerate(points):
                if cp_name not in existing_points:
                    item.check_points.append(InspectionCheckPoint(name=cp_name, sort_order=cp_order))
                    added["check_points"] += 1

    db.commit()
    return added


def template_categories(db: Session) -> list[InspectionCategory]:
    return list(
        db.scalars(
            select(InspectionCategory)
            .where(InspectionCategory.project_id.is_(None), InspectionCategory.is_active.is_(True))
            .order_by(InspectionCategory.sort_order)
        )
    )


def copy_template_to_project(db: Session, project: Project) -> None:
    """把公司範本（只複製啟用中的）複製成此建案自己的清單。呼叫端負責 commit。"""
    if not template_categories(db):
        seed_inspection_checklist(db)
    for cat in template_categories(db):
        copy = InspectionCategory(
            code=f"p{project.id}-{cat.code}", name=cat.name, sort_order=cat.sort_order, project_id=project.id
        )
        for item in cat.items:
            if not item.is_active:
                continue
            new_item = InspectionItem(name=item.name, sort_order=item.sort_order)
            new_item.check_points = [
                InspectionCheckPoint(name=cp.name, sort_order=cp.sort_order) for cp in item.check_points if cp.is_active
            ]
            copy.items.append(new_item)
        db.add(copy)
    db.flush()


def ensure_project_checklist(db: Session, project: Project) -> None:
    """舊建案（此功能上線前建立的）第一次讀取清單時補複製"""
    if not project.checklist:
        copy_template_to_project(db, project)
        db.commit()
        db.refresh(project)
