"""Render the PWA PNG icons (web/icons/) with Pillow. Run once after changing the logo:

    python scripts/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
BG, MARK = (20, 28, 46), (255, 225, 74)  # ink square, highlighter tick (same as web/icons/icon.svg)


def icon(size: int, maskable: bool = False) -> Image.Image:
    ss = 4  # supersample for smooth lines
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=0 if maskable else int(S * 0.22), fill=BG)
    k = (0.75 if maskable else 1.0) * S / 512   # maskable icons keep the art inside the safe zone
    o = (S - 512 * k) / 2
    p = lambda x, y: (o + x * k, o + y * k)  # noqa: E731
    w = max(2, int(52 * k))
    tick = [p(384, 168), p(208, 344), p(128, 264)]
    d.line(tick, fill=MARK, width=w, joint="curve")
    for cx, cy in tick:  # round caps
        d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=MARK)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192).save(OUT / "icon-192.png")
    icon(512).save(OUT / "icon-512.png")
    icon(512, maskable=True).save(OUT / "icon-512-maskable.png")
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
