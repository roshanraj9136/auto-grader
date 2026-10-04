"""Render the PWA PNG icons (web/icons/) with Pillow. Run once after changing the logo:

    python scripts/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
A, B, INK = (5, 150, 105), (13, 148, 136), (255, 255, 255)


def icon(size: int, maskable: bool = False) -> Image.Image:
    ss = 4  # supersample for smooth lines
    S = size * ss
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * (S - 1))
            px[x, y] = tuple(int(A[i] + (B[i] - A[i]) * t) for i in range(3))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=0 if maskable else int(S * 0.22), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    k = (0.62 if maskable else 0.8) * S / 512   # maskable icons keep the art inside the safe zone
    o = (S - 512 * k) / 2
    p = lambda x, y: (o + x * k, o + y * k)  # noqa: E731
    w = max(2, int(30 * k))
    cap = [p(96, 210), p(256, 130), p(416, 210), p(256, 290), p(96, 210)]
    d.line(cap, fill=INK, width=w, joint="curve")
    d.line([p(160, 242), p(160, 322)], fill=INK, width=w)
    d.line([p(352, 242), p(352, 322)], fill=INK, width=w)
    d.arc([p(160, 282)[0], p(160, 282)[1], p(352, 362)[0], p(352, 362)[1]], 0, 180, fill=INK, width=w)
    d.line([p(416, 210), p(416, 306)], fill=INK, width=w)
    for x, y in ((96, 210), (256, 130), (416, 210), (256, 290), (416, 306), (160, 322), (352, 322)):
        cx, cy = p(x, y)
        d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=INK)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192).save(OUT / "icon-192.png")
    icon(512).save(OUT / "icon-512.png")
    icon(512, maskable=True).save(OUT / "icon-512-maskable.png")
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
