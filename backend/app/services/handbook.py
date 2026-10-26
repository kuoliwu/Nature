"""住屋手冊（售服步驟 5：生產履歷＋住屋手冊）

每個建案一份「手冊範本」（分類 → 欄位，欄位可設建案共用的預設值），每戶填自己的值；
必填欄位都有內容（自己的值或共用預設值）＝ 完整，才能 Review OK。
PDF ＝ 系統產生的手冊頁 → 建案共用的外部 PDF → 該戶的外部 PDF，依序合併成一份。
"""

import io
from dataclasses import dataclass
from datetime import datetime

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    HandbookAttachment,
    HandbookEntry,
    HandbookField,
    HandbookSection,
    HandbookStatus,
    HandbookValue,
    Project,
    Unit,
    UnitHandbook,
)
from app.services.pdf import contract_font
from app.services.report_pdf import ReportPhoto, _p, _photo_block, _styles

TITLE = "生產履歷暨住屋手冊"
MAX_EMAIL_BYTES = 20 * 1024 * 1024  # Gmail 附件上限 25MB，編碼後會變大，保守取 20MB

# (分類, [(欄位, 共用預設值, 必填)])；建案第一次使用手冊時複製一份，之後可在 APP 修改
# 生產履歷改用逐戶的「生產履歷紀錄」（日期＋照片＋文字），範本只留住屋手冊的保固與聯絡資訊，都是選填
DEFAULT_TEMPLATE: list[tuple[str, list[tuple[str, str | None, bool]]]] = [
    ("住屋手冊：保固", [
        ("保固起算日", None, False),
        ("結構體保固", "15 年", False),
        ("防水保固", "1 年", False),
        ("設備保固", "1 年（依原廠保固條款）", False),
    ]),
    ("住屋手冊：聯絡資訊", [
        ("售服專線", None, False),
        ("管委會／物業聯絡方式", None, False),
    ]),
]
TEMPLATE_VERSION = 2
# 第 1 版預設範本有、第 2 版拿掉的分類
_V1_REMOVED = ("生產履歷：建築概要", "生產履歷：主要建材與設備", "生產履歷：廠商通訊錄", "住屋手冊：使用與保養")
_V1_OPTIONAL = ("住屋手冊：保固", "住屋手冊：聯絡資訊")


def ensure_template(db: Session, project: Project) -> None:
    """建案還沒有手冊範本時複製預設範本（只在完全沒有分類時）"""
    if db.scalar(select(func.count(HandbookSection.id)).where(HandbookSection.project_id == project.id)):
        return
    project.handbook_template_version = TEMPLATE_VERSION
    for i, (name, fields) in enumerate(DEFAULT_TEMPLATE):
        section = HandbookSection(project_id=project.id, name=name, sort_order=i)
        section.fields = [
            HandbookField(label=label, default_value=default, required=required, sort_order=j)
            for j, (label, default, required) in enumerate(fields)
        ]
        db.add(section)
    db.flush()


def migrate_template(db: Session) -> int:
    """
    已建立第 1 版範本的建案升到第 2 版（每個建案只做一次）：
    拿掉的分類沒人填過就刪除、有填過就停用；保固與聯絡資訊改為選填。回傳升級的建案數。
    """
    projects = list(db.scalars(select(Project).where(
        (Project.handbook_template_version.is_(None)) | (Project.handbook_template_version < TEMPLATE_VERSION)
    )))
    upgraded = 0
    for project in projects:
        project_sections = sections(db, project.id)
        project.handbook_template_version = TEMPLATE_VERSION
        if not project_sections:
            continue  # 還沒建立範本：之後 ensure_template 直接用第 2 版
        upgraded += 1
        for section in project_sections:
            if section.name in _V1_REMOVED:
                field_ids = [f.id for f in section.fields]
                used = field_ids and db.scalar(select(func.count(HandbookValue.id)).where(HandbookValue.field_id.in_(field_ids)))
                if used:
                    section.is_active = False
                else:
                    db.delete(section)
            elif section.name in _V1_OPTIONAL:
                for field in section.fields:
                    field.required = False
        # 留下的分類排前面，停用的舊分類排最後
        kept = [sec for sec in project_sections if sec.name not in _V1_REMOVED]
        retired = [sec for sec in project_sections if sec.name in _V1_REMOVED and not sec.is_active]
        for i, section in enumerate(kept + retired):
            section.sort_order = i
    db.commit()
    return upgraded


def sections(db: Session, project_id: int, active_only: bool = False) -> list[HandbookSection]:
    q = select(HandbookSection).where(HandbookSection.project_id == project_id)
    if active_only:
        q = q.where(HandbookSection.is_active.is_(True))
    return list(db.scalars(q.order_by(HandbookSection.sort_order, HandbookSection.id)))


def active_fields(db: Session, project_id: int) -> list[tuple[HandbookSection, list[HandbookField]]]:
    return [(s, [f for f in s.fields if f.is_active]) for s in sections(db, project_id, active_only=True)]


def unit_values(db: Session, unit_id: int) -> dict[int, str]:
    return {v.field_id: v.value for v in db.scalars(select(HandbookValue).where(HandbookValue.unit_id == unit_id))}


def get_handbook(db: Session, unit: Unit) -> UnitHandbook:
    handbook = db.scalar(select(UnitHandbook).where(UnitHandbook.unit_id == unit.id))
    if handbook is None:
        handbook = UnitHandbook(unit_id=unit.id, status=HandbookStatus.DRAFT)
        db.add(handbook)
        db.flush()
    return handbook


def missing_fields(groups: list[tuple[HandbookSection, list[HandbookField]]], values: dict[int, str]) -> list[str]:
    """必填但沒有內容（自己的值與共用預設值都空白）的欄位"""
    return [
        f"{s.name}／{f.label}"
        for s, fields in groups for f in fields
        if f.required and not (values.get(f.id) or f.default_value or "").strip()
    ]


def attachments(db: Session, unit: Unit) -> list[HandbookAttachment]:
    """依合併順序：建案共用 → 該戶專屬"""
    shared = db.scalars(
        select(HandbookAttachment)
        .where(HandbookAttachment.project_id == unit.project_id, HandbookAttachment.unit_id.is_(None))
        .order_by(HandbookAttachment.sort_order, HandbookAttachment.id)
    )
    own = db.scalars(
        select(HandbookAttachment)
        .where(HandbookAttachment.unit_id == unit.id)
        .order_by(HandbookAttachment.sort_order, HandbookAttachment.id)
    )
    return [*shared, *own]


def entries(db: Session, unit_id: int) -> list[HandbookEntry]:
    """生產履歷紀錄，依日期由舊到新"""
    return list(db.scalars(
        select(HandbookEntry).where(HandbookEntry.unit_id == unit_id).order_by(HandbookEntry.entry_date, HandbookEntry.id)
    ))


def filename(unit: Unit) -> str:
    name = f"{TITLE}_{unit.project.name}_{unit.unit_no}.pdf"
    return "".join(ch for ch in name if ch not in '\\/:*?"<>|')


@dataclass
class _Row:
    label: str
    value: str


def _cover_pages(unit: Unit, groups: list[tuple[str, list[_Row]]], records: list[HandbookEntry],
                 files: list[HandbookAttachment], approved: str | None) -> bytes:
    font = contract_font()
    s = _styles(font)
    buf = io.BytesIO()
    margin = 16 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"{TITLE} {unit.project.name} {unit.unit_no}")
    usable = A4[0] - 2 * margin
    project = unit.project
    story: list = [_p(TITLE, s["title"]), _p(f"{project.name}　{unit.unit_no}", s["sub"]), Spacer(1, 6 * mm)]

    info = [
        ("建案", project.name), ("戶別", unit.unit_no),
        ("地址", unit.address or project.address or project.community_address or "—"), ("屋主", unit.owner_name or "—"),
        ("坪數", f"{unit.area_ping:g} 坪" if unit.area_ping else "—"), ("交屋日期", f"{unit.handover_date:%Y-%m-%d}" if unit.handover_date else "—"),
    ]
    rows = [[_p(info[i][0], s["cell"]), _p(info[i][1], s["cell"]), _p(info[i + 1][0], s["cell"]), _p(info[i + 1][1], s["cell"])]
            for i in range(0, len(info), 2)]
    t = Table(rows, colWidths=[22 * mm, usable / 2 - 22 * mm] * 2)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t)

    if records:
        story += [_p("生產履歷紀錄", s["h2"])]
        for e in records:
            caption = f"{e.entry_date:%Y-%m-%d}" + (f"　{e.note}" if e.note else "")
            photos = [ReportPhoto(path=settings.storage_dir / p.file_path, width=p.width, height=p.height, caption=None) for p in e.photos]
            story += _photo_block(caption, photos, s, usable) if photos else [_p(caption, s["body"]), Spacer(1, 3 * mm)]

    for name, items in groups:
        table = Table([[_p(r.label, s["cell"]), _p(r.value or "—", s["cell"])] for r in items], colWidths=[48 * mm, usable - 48 * mm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ecf5f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        # 分類標題不和表格拆到不同頁（表格太長時才允許跨頁）
        story.append(KeepTogether([_p(name, s["h2"]), table]) if len(items) <= 12 else _p(name, s["h2"]))
        if len(items) > 12:
            story.append(table)

    if files:
        story += [_p("附件（接在本頁之後）", s["h2"])]
        story += [_p(f"{i}. {f.title}（{f.page_count} 頁）", s["body"]) for i, f in enumerate(files, 1)]

    story += [Spacer(1, 8 * mm), _p(f"產生時間：{datetime.now():%Y-%m-%d %H:%M}" + (f"　確認：{approved}" if approved else "　（草稿，尚未確認）"), s["small"])]
    doc.build(story)
    return buf.getvalue()


def build_pdf(db: Session, unit: Unit) -> bytes:
    """完整手冊：系統產生的頁面 + 建案共用 PDF + 該戶 PDF"""
    handbook = get_handbook(db, unit)
    values = unit_values(db, unit.id)
    groups = [
        (section.name, [_Row(f.label, (values.get(f.id) or f.default_value or "").strip()) for f in fields])
        for section, fields in active_fields(db, unit.project_id)
        if fields
    ]
    files = attachments(db, unit)
    approved = None
    if handbook.approved_at:
        who = handbook.approver.name if handbook.approver else ""
        approved = f"{who} {handbook.approved_at:%Y-%m-%d %H:%M}".strip()

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(_cover_pages(unit, groups, entries(db, unit.id), files, approved))))
    for f in files:
        writer.append(PdfReader(settings.storage_dir / f.file_path))
    writer.add_metadata({"/Title": f"{TITLE} {unit.project.name} {unit.unit_no}"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def sent_count(db: Session, project_id: int) -> int:
    return db.scalar(
        select(func.count(UnitHandbook.id))
        .join(Unit, Unit.id == UnitHandbook.unit_id)
        .where(Unit.project_id == project_id, UnitHandbook.status == HandbookStatus.SENT)
    ) or 0


def started(db: Session, project_id: int) -> bool:
    """有任何一戶填過值或已確認，就算步驟 5 已開始"""
    has_value = db.scalar(
        select(func.count(HandbookValue.id)).join(Unit, Unit.id == HandbookValue.unit_id).where(Unit.project_id == project_id)
    )
    has_status = db.scalar(
        select(func.count(UnitHandbook.id)).join(Unit, Unit.id == UnitHandbook.unit_id)
        .where(Unit.project_id == project_id, UnitHandbook.status != HandbookStatus.DRAFT)
    )
    return bool(has_value or has_status)
