"""驗屋照片與屋主簽名的影像處理"""

import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from app.config import settings

MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_PHOTO_SIDE = 1600  # 報告與手機瀏覽都夠用，避免存原圖數 MB


class MediaError(ValueError):
    pass


def save_photo(data: bytes, booking_id: int) -> tuple[str, int, int]:
    return save_image(data, Path("inspections") / str(booking_id))


def save_image(data: bytes, folder: Path) -> tuple[str, int, int]:
    """依 EXIF 轉正、縮到長邊 1600、存成 JPEG 放在 storage/folder；回傳 (相對路徑, 寬, 高)"""
    if len(data) > MAX_PHOTO_BYTES:
        raise MediaError("照片超過 15MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise MediaError("無法辨識的圖片格式（請用 JPG、PNG 或 HEIC 轉 JPG）")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))

    rel = folder / f"{uuid.uuid4().hex}.jpg"
    path = settings.storage_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="JPEG", quality=82, optimize=True)
    return rel.as_posix(), img.width, img.height


def render_signature(strokes: list[list[tuple[float, float]]], width: float, height: float) -> bytes:
    """
    APP 傳來的筆畫座標（畫布像素）→ 透明背景 PNG。
    先以 3 倍尺寸繪製再縮小，線條邊緣比較平滑。
    """
    if not strokes or not any(len(s) >= 1 for s in strokes):
        raise MediaError("簽名是空白的")
    if width <= 0 or height <= 0:
        raise MediaError("簽名畫布尺寸不正確")

    out_w = 900
    out_h = max(int(out_w * height / width), 200)
    scale = 3
    sx, sy = out_w * scale / width, out_h * scale / height
    img = Image.new("RGBA", (out_w * scale, out_h * scale), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    pen = 9 * scale
    for stroke in strokes:
        pts = [(x * sx, y * sy) for x, y in stroke[:2000]]
        if len(pts) == 1:
            x, y = pts[0]
            draw.ellipse((x - pen / 2, y - pen / 2, x + pen / 2, y + pen / 2), fill=(17, 24, 39, 255))
            continue
        draw.line(pts, fill=(17, 24, 39, 255), width=pen, joint="curve")
        for x, y in (pts[0], pts[-1]):  # 圓頭
            draw.ellipse((x - pen / 2, y - pen / 2, x + pen / 2, y + pen / 2), fill=(17, 24, 39, 255))
    img = img.resize((out_w, out_h), Image.LANCZOS)

    bbox = img.getbbox()
    if bbox:
        pad = 12
        img = img.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, out_w), min(bbox[3] + pad, out_h)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_signature_png(png: bytes, booking_id: int) -> str:
    rel = Path("signatures") / f"inspection{booking_id}_{uuid.uuid4().hex[:8]}.png"
    (settings.storage_dir / rel).write_bytes(png)
    return rel.as_posix()
