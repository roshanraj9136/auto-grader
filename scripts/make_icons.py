"""Render the PWA PNG icons (web/icons/) with Pillow. Run once after changing the logo:

    python scripts/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
A, B, INK = (124, 131, 255), (34, 211, 238), (11, 16, 32)


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def icon(size: int, maskable: bool = False) -> Image.Image:
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(int(A[i] + (B[i] - A[i]) * t) for i in range(3))
    mask = Image.new("L", (size, size), 0)
    radius = 0 if maskable else int(size * 0.22)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    scale = 0.72 if maskable else 1.0  # maskable icons keep content inside the 80% safe zone
    f = _font(int(size * 0.41 * scale))
    d.text((size / 2, size * 0.55), "AG", font=f, fill=INK, anchor="mm")
    d.text((size / 2 + size * 0.29 * scale, size / 2 - size * 0.18 * scale), "+", font=_font(int(size * 0.24 * scale)),
           fill=INK, anchor="mm")
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192).save(OUT / "icon-192.png")
    icon(512).save(OUT / "icon-512.png")
    icon(512, maskable=True).save(OUT / "icon-512-maskable.png")
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
