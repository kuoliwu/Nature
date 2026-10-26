"""產生 APP 圖示：暖淺灰底 + 深炭灰「H」（依使用者提供的色樣）。用法：../backend/.venv/bin/python scripts/make_icons.py

H 用幾何矩形繪製（不依賴字型），各尺寸都清晰。
"""

from pathlib import Path

from PIL import Image, ImageDraw

BG = (212, 209, 207, 255)  # #d4d1cf 暖淺灰
INK = (75, 75, 82, 255)  # #4b4b52 深炭灰（與底色對比 5.7:1）
ROOT = Path(__file__).resolve().parent.parent


def draw_h(img: Image.Image, scale: float, color=INK) -> None:
    """在圖片中央畫 H；scale 為 H 高度占圖片邊長的比例"""
    size = img.width
    h = size * scale
    w = h * 0.82
    bar = h * 0.22
    x0, y0 = (size - w) / 2, (size - h) / 2
    d = ImageDraw.Draw(img)
    r = bar * 0.18  # 微圓角
    d.rounded_rectangle((x0, y0, x0 + bar, y0 + h), r, fill=color)
    d.rounded_rectangle((x0 + w - bar, y0, x0 + w, y0 + h), r, fill=color)
    d.rectangle((x0 + bar * 0.5, y0 + h / 2 - bar / 2, x0 + w - bar * 0.5, y0 + h / 2 + bar / 2), fill=color)


def square(size: int, scale: float, rounded: bool = False) -> Image.Image:
    """淺灰底方形；rounded=True 時為圓角（網頁 favicon 用）"""
    big = size * 4  # 先放大畫再縮小，邊緣平滑
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if rounded:
        ImageDraw.Draw(img).rounded_rectangle((0, 0, big - 1, big - 1), big * 0.22, fill=BG)
    else:
        img.paste(BG, (0, 0, big, big))
    draw_h(img, scale)
    return img.resize((size, size), Image.LANCZOS)


def transparent(size: int, scale: float, color=INK) -> Image.Image:
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw_h(img, scale, color)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    assets, public = ROOT / "assets", ROOT / "public" / "icons"
    public.mkdir(parents=True, exist_ok=True)
    square(1024, 0.5).convert("RGB").save(assets / "icon.png")  # iOS / 通用（系統自己裁圓角）
    square(1024, 0.5, rounded=True).save(assets / "splash-icon.png")
    square(48, 0.56, rounded=True).save(assets / "favicon.png")
    # Android adaptive icon：前景只放 H（安全區約中間 66%）、背景純淺灰
    transparent(512, 0.34).save(assets / "android-icon-foreground.png")
    Image.new("RGBA", (512, 512), BG).save(assets / "android-icon-background.png")
    transparent(432, 0.34).save(assets / "android-icon-monochrome.png")
    # 網頁版（加入主畫面）
    square(180, 0.5).convert("RGB").save(public / "apple-touch-icon.png")  # iOS 不支援透明
    square(192, 0.5, rounded=True).save(public / "icon-192.png")
    square(512, 0.5, rounded=True).save(public / "icon-512.png")
    square(512, 0.4).save(public / "icon-maskable-512.png")  # maskable：系統會裁形狀，H 縮小留安全區
    print("icons generated")


if __name__ == "__main__":
    main()
