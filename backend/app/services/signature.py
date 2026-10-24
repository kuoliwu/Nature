"""前端傳來的 Base64 簽名圖檔 → 驗證、裁切空白 → 存成 PNG"""

import base64
import binascii
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import settings

MAX_SIGNATURE_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 3000


class SignatureError(ValueError):
    pass


def decode_signature(data: str) -> bytes:
    """
    接受 "data:image/png;base64,iVBOR..." 或純 Base64 字串。
    回傳裁掉四周空白、轉成透明背景的 PNG bytes。
    """
    if "," in data and data.lstrip().startswith("data:"):
        header, data = data.split(",", 1)
        if not header.startswith(("data:image/png", "data:image/jpeg")):
            raise SignatureError("簽名必須是 PNG 或 JPEG 圖檔")

    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise SignatureError("簽名資料不是有效的 Base64")
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise SignatureError("簽名圖檔過大（上限 2MB）")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise SignatureError("無法辨識簽名圖檔")
    if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
        raise SignatureError("簽名圖檔尺寸過大")

    img = _to_transparent(img.convert("RGBA"))
    bbox = img.getbbox()  # 以 alpha 判斷實際筆跡範圍
    if bbox is None:
        raise SignatureError("簽名是空白的")
    img = img.crop(bbox)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _to_transparent(img: Image.Image) -> Image.Image:
    """白色 / 近白色背景改為透明，疊到 PDF 上才不會蓋住底下的線條"""
    pixels = [
        (r, g, b, 0) if r > 235 and g > 235 and b > 235 else (r, g, b, a)
        for r, g, b, a in img.getdata()
    ]
    img.putdata(pixels)
    return img


def save_signature(png: bytes, name: str) -> str:
    """存到 storage/signatures/，回傳相對於 storage_dir 的路徑（存進 DB）"""
    rel = Path("signatures") / f"{name}.png"
    (settings.storage_dir / rel).write_bytes(png)
    return rel.as_posix()
