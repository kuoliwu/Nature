"""驗屋授權書 PDF：合約範本 + 疊加層（文字欄位與簽名圖檔）

做法：
  1. 範本：若有 storage/templates/authorization_template.pdf 就用它，否則用 ReportLab 畫出預設範本
  2. 疊加層：用 ReportLab 在同尺寸的透明頁面上，依 LAYOUT 座標寫入資料與簽名 PNG
  3. 用 pypdf 把疊加層 merge 到範本第一頁

改用自己的範本時，只要調整 LAYOUT 的座標即可（單位 pt，原點在左下角，A4 = 595 x 842）。
"""

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.config import BASE_DIR, settings

log = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
TEMPLATE_PATH = settings.storage_dir / "templates" / "authorization_template.pdf"

# 欄位座標：(x, y)；簽名框：(x, y, 寬, 高)
LAYOUT = {
    "fields": {
        "project_name": (170, 640),
        "unit_no": (170, 612),
        "unit_address": (170, 584),
        "inspection_date": (170, 556),
        "trustee_name": (170, 528),
        "trustee_email": (170, 500),
    },
    "owner_signature": (70, 150, 210, 90),
    "trustee_signature": (315, 150, 210, 90),
    "owner_name": (110, 130),
    "trustee_name_below": (355, 130),
    "owner_signed_at": (110, 112),
    "trustee_signed_at": (355, 112),
    "footer": (70, 60),
}

FIELD_LABELS = {
    "project_name": "建案名稱",
    "unit_no": "戶　　別",
    "unit_address": "房屋地址",
    "inspection_date": "驗屋日期",
    "trustee_name": "受 託 人",
    "trustee_email": "受託人 Email",
}

CLAUSES = [
    "一、代理委託人於上述驗屋日期進行現場驗屋、檢查與紀錄。",
    "二、代理確認驗屋缺失紀錄，並簽收驗屋報告及相關文件。",
    "三、本授權僅限上述房屋之驗屋相關事宜，不包含產權移轉、價金給付或其他法律行為。",
    "四、本授權書以電子簽名方式簽署，雙方同意其效力與親筆簽名相同。",
]


@dataclass
class AuthorizationPdfData:
    authorization_id: int
    project_name: str
    unit_no: str
    unit_address: str
    inspection_date: str
    owner_name: str
    trustee_name: str
    trustee_email: str
    owner_signature: Path
    trustee_signature: Path
    owner_signed_at: datetime
    trustee_signed_at: datetime


@lru_cache
def contract_font() -> str:
    """註冊並回傳字型名稱。優先使用可嵌入的 TTF，找不到時退回 ReportLab 內建的繁中 CID 字型。"""
    candidates = [
        settings.pdf_font_path,
        *sorted((BASE_DIR / "fonts").glob("*.ttf")),
        Path("/mnt/c/Windows/Fonts/kaiu.ttf"),  # WSL 下的 Windows 標楷體
        Path("C:/Windows/Fonts/kaiu.ttf"),
    ]
    for path in candidates:
        if path and Path(path).is_file():
            pdfmetrics.registerFont(TTFont("ContractFont", str(path)))
            return "ContractFont"

    log.warning("找不到繁中 TTF 字型，改用內建 MSung-Light（未嵌入，部分閱讀器可能無法顯示）")
    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    return "MSung-Light"


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    lines, current = [], ""
    for ch in text:
        if pdfmetrics.stringWidth(current + ch, font, size) > max_width:
            lines.append(current)
            current = ch
        else:
            current += ch
    return [*lines, current] if current else lines


def build_default_template() -> bytes:
    font = contract_font()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    c.setFont(font, 22)
    c.drawCentredString(PAGE_W / 2, 770, "驗屋代理授權書")

    c.setFont(font, 12)
    intro = "立授權書人（以下稱「委託人」）茲授權下列受託人，代理委託人辦理下列房屋之驗屋事宜，授權內容如下："
    y = 725
    for line in _wrap(intro, font, 12, PAGE_W - 140):
        c.drawString(70, y, line)
        y -= 18

    c.setFont(font, 12)
    for key, (x, fy) in LAYOUT["fields"].items():
        c.drawString(70, fy, f"{FIELD_LABELS[key]}：")
        c.line(x - 5, fy - 4, PAGE_W - 70, fy - 4)

    c.setFont(font, 13)
    c.drawString(70, 455, "授權範圍")
    c.setFont(font, 11.5)
    y = 432
    for clause in CLAUSES:
        for i, line in enumerate(_wrap(clause, font, 11.5, PAGE_W - 160)):
            c.drawString(80 if i == 0 else 104, y, line)
            y -= 18
        y -= 4

    for key, label in (("owner_signature", "委託人（屋主）簽名"), ("trustee_signature", "受託人簽名")):
        x, sy, w, h = LAYOUT[key]
        c.setFont(font, 12)
        c.drawString(x, sy + h + 10, label)
        c.setDash(3, 3)
        c.rect(x, sy, w, h)
        c.setDash()
        c.setFont(font, 10)
        c.drawString(x, sy - 20, "姓名：")
        c.drawString(x, sy - 38, "時間：")

    c.showPage()
    c.save()
    return buf.getvalue()


def build_overlay(d: AuthorizationPdfData) -> bytes:
    font = contract_font()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    values = {
        "project_name": d.project_name,
        "unit_no": d.unit_no,
        "unit_address": d.unit_address,
        "inspection_date": d.inspection_date,
        "trustee_name": d.trustee_name,
        "trustee_email": d.trustee_email,
    }
    c.setFont(font, 12)
    for key, (x, y) in LAYOUT["fields"].items():
        c.drawString(x, y, values[key])

    for key, path in (("owner_signature", d.owner_signature), ("trustee_signature", d.trustee_signature)):
        x, y, w, h = LAYOUT[key]
        pad = 6
        c.drawImage(
            ImageReader(str(path)), x + pad, y + pad, w - pad * 2, h - pad * 2,
            preserveAspectRatio=True, anchor="c", mask="auto",
        )

    c.setFont(font, 10)
    fmt = "%Y-%m-%d %H:%M"
    c.drawString(*LAYOUT["owner_name"], d.owner_name)
    c.drawString(*LAYOUT["trustee_name_below"], d.trustee_name)
    c.drawString(*LAYOUT["owner_signed_at"], d.owner_signed_at.strftime(fmt))
    c.drawString(*LAYOUT["trustee_signed_at"], d.trustee_signed_at.strftime(fmt))

    c.setFont(font, 9)
    c.drawString(
        *LAYOUT["footer"],
        f"授權書編號 AUTH-{d.authorization_id:06d}　產生時間 {datetime.now().strftime(fmt)}",
    )

    c.showPage()
    c.save()
    return buf.getvalue()


def generate_authorization_pdf(d: AuthorizationPdfData) -> bytes:
    template = TEMPLATE_PATH.read_bytes() if TEMPLATE_PATH.is_file() else build_default_template()

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(template)))
    overlay_page = PdfReader(io.BytesIO(build_overlay(d))).pages[0]
    writer.pages[0].merge_page(overlay_page)
    writer.add_metadata({"/Title": f"驗屋代理授權書 AUTH-{d.authorization_id:06d}"})

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def save_authorization_pdf(pdf: bytes, authorization_id: int) -> str:
    rel = Path("authorizations") / f"AUTH-{authorization_id:06d}.pdf"
    (settings.storage_dir / rel).write_bytes(pdf)
    return rel.as_posix()
