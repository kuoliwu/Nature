"""驗屋 / 健檢報告 PDF：基本資料、結果統計、不合格項目、完整檢查表、照片、屋主簽名"""

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.pdf import contract_font

RESULT_TEXT = {"pass": "合格", "fail": "不合格", "na": "不適用", "pending": "未檢查"}
RESULT_COLOR = {"pass": "#166534", "fail": "#b91c1c", "na": "#6b7280", "pending": "#6b7280"}


@dataclass
class ReportPhoto:
    path: Path
    width: int
    height: int
    caption: str | None = None


@dataclass
class ReportPoint:
    category: str
    item: str
    name: str
    result: str
    note: str | None
    photos: list[ReportPhoto] = field(default_factory=list)


@dataclass
class ReportData:
    title: str  # 例如「健檢報告」
    project_name: str
    unit_no: str
    place: str
    when: str  # 驗屋日期時間
    contact: str
    inspector: str
    points: list[ReportPoint]
    general_note: str | None
    general_photos: list[ReportPhoto]
    signer_name: str | None
    signed_at: datetime | None
    signature_path: Path | None
    approved: str | None  # 例如「王經理 2026-12-01 15:00」


def _styles(font: str) -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=font, fontSize=10.5, leading=15, wordWrap="CJK")
    return {
        "title": ParagraphStyle("title", parent=base, fontSize=20, leading=26, alignment=TA_CENTER, spaceAfter=4),
        "sub": ParagraphStyle("sub", parent=base, fontSize=11, alignment=TA_CENTER, textColor=colors.HexColor("#6b7280")),
        "h2": ParagraphStyle("h2", parent=base, fontSize=13.5, leading=20, spaceBefore=10, spaceAfter=6),
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=9, leading=12, textColor=colors.HexColor("#374151")),
        "cell": ParagraphStyle("cell", parent=base, fontSize=9.5, leading=13),
    }


def _p(text: str | None, style: ParagraphStyle) -> Paragraph:
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    return Paragraph(safe, style)


def _result(result: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f'<font color="{RESULT_COLOR[result]}">{RESULT_TEXT[result]}</font>', style)


def _grid(headers: list[str], rows: list[list], widths: list[float], s: dict) -> Table:
    table = Table([[_p(h, s["cell"]) for h in headers], *rows], colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _photo_block(caption: str, photos: list[ReportPhoto], s: dict, usable: float) -> list:
    """一個檢查點的照片：標題 + 每列兩張"""
    cell_w = (usable - 6 * mm) / 2
    max_h = 70 * mm
    cells = []
    for ph in photos:
        ratio = min(cell_w / ph.width, max_h / ph.height)
        img = Image(str(ph.path), width=ph.width * ratio, height=ph.height * ratio)
        cells.append([img, _p(ph.caption, s["small"])] if ph.caption else img)
    rows = [cells[i : i + 2] + [""] * (2 - len(cells[i : i + 2])) for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[cell_w + 3 * mm] * 2)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [KeepTogether([_p(caption, s["body"]), Spacer(1, 2 * mm), table]), Spacer(1, 3 * mm)]


def build_report(d: ReportData) -> bytes:
    font = contract_font()
    s = _styles(font)
    buf = io.BytesIO()
    margin = 16 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"{d.title} {d.project_name} {d.unit_no}")
    usable = A4[0] - 2 * margin
    story: list = [_p(d.title, s["title"]), _p(f"{d.project_name}　{d.unit_no}", s["sub"]), Spacer(1, 6 * mm)]

    # 基本資料
    info = [
        ("建案", d.project_name), ("戶別", d.unit_no),
        ("地址", d.place or "—"), ("日期時間", d.when),
        ("屋主／聯絡人", d.contact), ("驗屋人員", d.inspector or "—"),
    ]
    rows = [[_p(info[i][0], s["cell"]), _p(info[i][1], s["cell"]), _p(info[i + 1][0], s["cell"]), _p(info[i + 1][1], s["cell"])]
            for i in range(0, len(info), 2)]
    t = Table(rows, colWidths=[27 * mm, usable / 2 - 27 * mm] * 2)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [t]

    # 結果統計
    count = {k: sum(1 for p in d.points if p.result == k) for k in ("pass", "fail", "na")}
    story += [
        _p("檢查結果統計", s["h2"]),
        # 這行要用顏色標記，不能經過 _p 的跳脫處理
        Paragraph(f'共 {len(d.points)} 個檢查點：<font color="#166534">合格 {count["pass"]}</font>　'
                  f'<font color="#b91c1c">不合格 {count["fail"]}</font>　<font color="#6b7280">不適用 {count["na"]}</font>', s["body"]),
    ]

    fails = [p for p in d.points if p.result == "fail"]
    if fails:
        story += [_p(f"不合格項目（{len(fails)}）", s["h2"]), _grid(
            ["類別", "項目", "檢查點", "說明"],
            [[_p(p.category, s["cell"]), _p(p.item, s["cell"]), _p(p.name, s["cell"]), _p(p.note or "", s["cell"])] for p in fails],
            [24 * mm, 32 * mm, 30 * mm, usable - 86 * mm], s,
        )]

    # 完整檢查表
    story.append(_p("完整檢查結果", s["h2"]))
    rows = [[_p(p.category, s["cell"]), _p(p.item, s["cell"]), _p(p.name, s["cell"]), _result(p.result, s["cell"]), _p(p.note or "", s["cell"])]
            for p in d.points]
    story.append(_grid(["類別", "項目", "檢查點", "結果", "備註"], rows, [22 * mm, 30 * mm, 28 * mm, 18 * mm, usable - 98 * mm], s))

    if d.general_note:
        story += [_p("整體備註", s["h2"]), _p(d.general_note, s["body"])]

    # 照片
    photo_points = [p for p in d.points if p.photos]
    if photo_points or d.general_photos:
        story.append(_p("照片紀錄", s["h2"]))
        for p in photo_points:
            label = f"{p.category}／{p.item}／{p.name}（{RESULT_TEXT[p.result]}）"
            story += _photo_block(label, p.photos, s, usable)
        if d.general_photos:
            story += _photo_block("整體照片", d.general_photos, s, usable)

    # 簽名
    sign_block: list = [_p("屋主確認", s["h2"]), _p("以上檢查結果經屋主（或代理人）於現場確認並簽名。", s["body"]), Spacer(1, 3 * mm)]
    if d.signature_path and d.signature_path.is_file():
        with PILImage.open(d.signature_path) as im:
            w, h = im.size
        ratio = min(70 * mm / w, 28 * mm / h)
        sign_block.append(Image(str(d.signature_path), width=w * ratio, height=h * ratio, hAlign="LEFT"))
    signed = d.signed_at.strftime("%Y-%m-%d %H:%M") if d.signed_at else "—"
    sign_block.append(_p(f"簽名人：{d.signer_name or '—'}　簽名時間：{signed}", s["body"]))
    if d.approved:
        sign_block.append(_p(f"報告確認：{d.approved}", s["small"]))
    story.append(KeepTogether(sign_block))

    footer = f"{d.title}｜{d.project_name} {d.unit_no}"

    def on_page(canvas, doc_):
        canvas.saveState()
        canvas.setFont(font, 8.5)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(margin, 10 * mm, footer)
        canvas.drawRightString(A4[0] - margin, 10 * mm, f"第 {doc_.page} 頁　產生時間 {datetime.now():%Y-%m-%d %H:%M}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
