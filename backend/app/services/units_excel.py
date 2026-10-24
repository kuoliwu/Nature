"""住戶資料 Excel（.xlsx）/ CSV 匯出與匯入。

匯入規則：
  - 以「戶別」比對：已存在的更新、不存在的新增；Excel 裡沒有的戶別不會被刪除
  - 檔案中出現的欄位才會更新；儲存格空白代表清空該欄
  - 先檢查每一列，只要有任何錯誤就整份不寫入，並回報哪一列、什麼問題
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.models import Unit

# (欄位, 表頭, 欄寬)；表頭的 * 代表必填
COLUMNS: list[tuple[str, str, int]] = [
    ("unit_no", "戶別*", 14),
    ("building", "棟別", 8),
    ("floor", "樓層", 8),
    ("address", "住家地址", 36),
    ("area_ping", "坪數", 8),
    ("handover_date", "交屋日期", 13),
    ("owner_name", "屋主姓名", 12),
    ("owner_phone", "屋主電話", 14),
    ("owner_email", "屋主Email", 28),
    ("note", "備註", 30),
]
HEADER_TO_KEY = {header.rstrip("*"): key for key, header, _ in COLUMNS}
MAX_LENGTHS = {"unit_no": 30, "building": 20, "floor": 10, "address": 255, "owner_name": 50, "owner_phone": 20}
MAX_ROWS = 5000

_email = TypeAdapter(EmailStr)

INSTRUCTIONS = [
    "填寫說明",
    "",
    "1. 請在「住戶」工作表填寫，第一列表頭請勿修改；「戶別」為必填。",
    "2. 匯入時以「戶別」比對：已存在的戶別會更新資料，不存在的會新增。",
    "3. 檔案中沒有的戶別不會被刪除；要刪除請在 APP 中操作。",
    "4. 儲存格留白代表清空該欄資料。",
    "5. 交屋日期格式：2026-12-31（也可用 2026/12/31 或 Excel 日期格式）。",
    "6. 坪數請填數字，例如 35.5。",
    "7. 電話若被 Excel 吃掉開頭的 0（例如 912345678），匯入時會自動補回。",
    "8. 匯入前系統會先檢查每一列，有錯誤時整份不會寫入，並列出錯誤的列號。",
    "9. 也可以匯入 CSV（逗號分隔的純文字檔，UTF-8 或 Big5 編碼），第一列同樣是表頭。",
]


# ---------------------------------------------------------------------------
# 匯出
# ---------------------------------------------------------------------------
def export_units(units: list[Unit]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "住戶"
    header_fill = PatternFill("solid", fgColor="DBEAFE")
    for col, (key, header, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"

    for row, unit in enumerate(units, start=2):
        for col, (key, _, _) in enumerate(COLUMNS, start=1):
            value = getattr(unit, key)
            cell = ws.cell(row=row, column=col, value=value)
            if key == "handover_date" and value:
                cell.number_format = "yyyy-mm-dd"
            elif key in ("owner_phone", "unit_no"):
                cell.number_format = "@"  # 文字格式，保留開頭的 0

    # 空白列也預先設成文字格式，使用者新增時電話不會被吃掉 0
    for row in range(len(units) + 2, len(units) + 202):
        for key in ("unit_no", "owner_phone"):
            ws.cell(row=row, column=[k for k, _, _ in COLUMNS].index(key) + 1).number_format = "@"

    help_ws = wb.create_sheet("說明")
    help_ws.column_dimensions["A"].width = 90
    for i, line in enumerate(INSTRUCTIONS, start=1):
        help_ws.cell(row=i, column=1, value=line).font = Font(bold=(i == 1), size=14 if i == 1 else 11)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_units_csv(units: list[Unit]) -> bytes:
    """UTF-8 加 BOM，Excel 直接開啟時中文不會變亂碼"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([header for _, header, _ in COLUMNS])
    for unit in units:
        row = []
        for key, _, _ in COLUMNS:
            value = getattr(unit, key)
            row.append("" if value is None else value.isoformat() if isinstance(value, date) else value)
        writer.writerow(row)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# 匯入
# ---------------------------------------------------------------------------
class ExcelFormatError(ValueError):
    """整份檔案無法讀取（不是 xlsx、找不到表頭等）"""


@dataclass
class ParsedImport:
    rows: list[tuple[int, dict]] = field(default_factory=list)  # (Excel 列號, 欄位值)
    columns: list[str] = field(default_factory=list)  # 檔案中出現的欄位
    errors: list[tuple[int, str]] = field(default_factory=list)


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # Excel 把 101 存成 101.0
    text = str(value).strip()
    return text or None


def _phone(value) -> str | None:
    text = _text(value)
    if text and isinstance(value, (int, float)) and re.fullmatch(r"9\d{8}", text):
        text = "0" + text  # 手機號碼被 Excel 當數字吃掉開頭的 0
    return text


def _date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"交屋日期「{text}」格式不正確，請用 2026-12-31")


def _area(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        area = float(str(value).strip())
    except ValueError:
        raise ValueError(f"坪數「{value}」不是數字")
    if area < 0 or area > 100000:
        raise ValueError(f"坪數「{value}」超出範圍")
    return area


def _xlsx_rows(data: bytes):
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise ExcelFormatError("無法讀取這個 Excel 檔，請確認檔案沒有損毀")
    ws = wb["住戶"] if "住戶" in wb.sheetnames else wb.worksheets[0]
    yield from ws.iter_rows(values_only=True)
    wb.close()


def _csv_rows(data: bytes):
    for encoding in ("utf-8-sig", "big5", "cp950"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExcelFormatError("無法辨識 CSV 的文字編碼，請另存為 UTF-8 的 CSV")
    if "\x00" in text:
        raise ExcelFormatError("請上傳 Excel（.xlsx）或 CSV 檔")
    # 支援逗號或 Tab 分隔（從 Excel 複製貼上的文字是 Tab）
    delimiter = "\t" if text.split("\n", 1)[0].count("\t") > text.split("\n", 1)[0].count(",") else ","
    yield from (tuple(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter))


def parse_units_excel(data: bytes) -> ParsedImport:
    """接受 .xlsx 或 CSV / TXT（逗號或 Tab 分隔）"""
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        raise ExcelFormatError("這是舊版 .xls，請在 Excel 另存為 .xlsx 或 CSV 後再匯入")
    rows = _xlsx_rows(data) if data.startswith(b"PK") else _csv_rows(data)
    header = next(rows, None) or ()
    col_keys: dict[int, str] = {}
    for idx, title in enumerate(header):
        key = HEADER_TO_KEY.get(str(title or "").strip().rstrip("*").replace(" ", ""))
        if key:
            col_keys[idx] = key
    if "unit_no" not in col_keys.values():
        raise ExcelFormatError("找不到「戶別」欄位，請使用匯出的範本，第一列表頭不要修改")

    result = ParsedImport(columns=list(dict.fromkeys(col_keys.values())))
    seen: dict[str, int] = {}
    for excel_row, values in enumerate(rows, start=2):
        if excel_row - 1 > MAX_ROWS:
            raise ExcelFormatError(f"一次最多匯入 {MAX_ROWS} 列")
        raw = {key: values[idx] if idx < len(values) else None for idx, key in col_keys.items()}
        if all(v is None or str(v).strip() == "" for v in raw.values()):
            continue  # 整列空白

        try:
            if not _text(raw.get("unit_no")):
                raise ValueError("戶別不能空白")
            item = {
                "unit_no": _text(raw.get("unit_no")),
                "building": _text(raw.get("building")),
                "floor": _text(raw.get("floor")),
                "address": _text(raw.get("address")),
                "owner_name": _text(raw.get("owner_name")),
                "owner_phone": _phone(raw.get("owner_phone")),
                "owner_email": _text(raw.get("owner_email")),
                "note": _text(raw.get("note")),
                "area_ping": _area(raw.get("area_ping")),
                "handover_date": _date(raw.get("handover_date")),
            }
            for key, limit in MAX_LENGTHS.items():
                if item[key] and len(item[key]) > limit:
                    raise ValueError(f"{dict((k, h) for k, h, _ in COLUMNS)[key].rstrip('*')}超過 {limit} 個字")
            if item["owner_email"]:
                try:
                    _email.validate_python(item["owner_email"])
                except ValidationError:
                    raise ValueError(f"Email「{item['owner_email']}」格式不正確")
            if item["unit_no"] in seen:
                raise ValueError(f"戶別「{item['unit_no']}」與第 {seen[item['unit_no']]} 列重複")
        except ValueError as e:
            result.errors.append((excel_row, str(e)))
            continue

        seen[item["unit_no"]] = excel_row
        result.rows.append((excel_row, {k: v for k, v in item.items() if k in result.columns}))

    return result
