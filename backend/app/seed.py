"""預設檢查項目表。可重複執行：已存在的類別 / 項目 / 檢查點不會重複建立。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InspectionCategory, InspectionCheckPoint, InspectionItem

WINDOW_CHECKS = ["膠條", "密合度", "五金"]
PLUMBING_AREAS = ["浴室", "陽台", "廚房"]

DEFAULT_CHECKLIST: list[dict] = [
    {
        "code": "windows",
        "name": "窗類",
        "items": {
            "陽台窗": WINDOW_CHECKS,
            "房間窗": WINDOW_CHECKS,
            "工作陽台門": WINDOW_CHECKS,
        },
    },
    {
        "code": "plumbing",
        "name": "水電類",
        "items": {
            "給水": PLUMBING_AREAS,
            "排水": PLUMBING_AREAS,
        },
    },
]


def seed_inspection_checklist(db: Session) -> dict[str, int]:
    added = {"categories": 0, "items": 0, "check_points": 0}

    for cat_order, cat_data in enumerate(DEFAULT_CHECKLIST):
        category = db.scalar(
            select(InspectionCategory).where(InspectionCategory.code == cat_data["code"])
        )
        if category is None:
            category = InspectionCategory(
                code=cat_data["code"], name=cat_data["name"], sort_order=cat_order
            )
            db.add(category)
            added["categories"] += 1

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
