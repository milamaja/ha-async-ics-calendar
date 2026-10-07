"""Renders the integration's brand images (custom_components/async_ics_calendar/brand/).

    python tools/render_icon.py                   # writes the four brand PNGs
    python tools/render_icon.py --preview out.png # also a preview on light and dark backgrounds

A calendar page with a sync badge: an ICS feed that is fetched and refreshed.
Original artwork in a 256-unit grid, transparent background, light and dark variants.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "custom_components" / "async_ics_calendar" / "brand"

RED = "#E53935"
BLUE = "#1E88E5"


def draw(size: int, dark: bool) -> Image.Image:
    ss = 4
    s = size * ss / 256  # grid unit -> pixels
    img = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1):
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    page = "#ECEFF1" if dark else "#FFFFFF"
    edge = None if dark else "#B0BEC5"
    cell = "#B0BEC5" if dark else "#CFD8DC"
    ring = "#ECEFF1" if dark else "#455A64"

    # Page with a red header band.
    d.rounded_rectangle(box(20, 36, 212, 228), radius=28 * s, fill=page,
                        outline=edge, width=round(6 * s) if edge else 0)
    d.rounded_rectangle(box(20, 36, 212, 92), radius=28 * s, fill=RED)
    d.rectangle(box(20, 70, 212, 92), fill=RED)
    # Binder rings.
    for x in (66, 166):
        d.rounded_rectangle(box(x - 9, 18, x + 9, 60), radius=9 * s, fill=ring)
    # Day grid: 3 rows of 4, one day picked out.
    for row in range(3):
        for col in range(4):
            x, y = 40 + col * 40, 108 + row * 36
            fill = BLUE if (row, col) == (1, 1) else cell
            d.rounded_rectangle(box(x, y, x + 32, y + 26), radius=6 * s, fill=fill)

    # Sync badge, bottom right: a blue disc with two arrows chasing each other.
    cx, cy, r = 196, 196, 50
    d.ellipse(box(cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8), fill=(0, 0, 0, 0))
    hole = Image.new("L", img.size, 0)  # clear a ring around the badge so it reads on the page
    ImageDraw.Draw(hole).ellipse(box(cx - r - 9, cy - r - 9, cx + r + 9, cy + r + 9), fill=255)
    img.putalpha(Image.composite(Image.new("L", img.size, 0), img.getchannel("A"), hole))
    d = ImageDraw.Draw(img)
    d.ellipse(box(cx - r, cy - r, cx + r, cy + r), fill=BLUE)
    ar, w = 27, 9
    for start in (200, 20):
        end = start + 125
        d.arc(box(cx - ar, cy - ar, cx + ar, cy + ar), start=start, end=end, fill="#FFFFFF", width=round(w * s))
        a = math.radians(end)
        tip = (cx + ar * math.cos(a), cy + ar * math.sin(a))
        tangent = (-math.sin(a), math.cos(a))           # direction of travel (clockwise in screen space)
        normal = (math.cos(a), math.sin(a))
        head = 15
        p1 = (tip[0] + tangent[0] * head * 0.9, tip[1] + tangent[1] * head * 0.9)
        p2 = (tip[0] + normal[0] * head * 0.75 - tangent[0] * 2, tip[1] + normal[1] * head * 0.75 - tangent[1] * 2)
        p3 = (tip[0] - normal[0] * head * 0.75 - tangent[0] * 2, tip[1] - normal[1] * head * 0.75 - tangent[1] * 2)
        d.polygon([(p[0] * s, p[1] * s) for p in (p1, p2, p3)], fill="#FFFFFF")

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    for name, size, dark in [("icon.png", 256, False), ("icon@2x.png", 512, False),
                             ("dark_icon.png", 256, True), ("dark_icon@2x.png", 512, True)]:
        draw(size, dark).save(BRAND / name, optimize=True)
        print("wrote", (BRAND / name).relative_to(ROOT))

    if "--preview" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--preview") + 1])
        sheet = Image.new("RGBA", (900, 420), "#FFFFFF")
        light = Image.new("RGBA", (440, 400), "#FAFAFA")
        dark = Image.new("RGBA", (440, 400), "#111111")
        for bg, is_dark in ((light, False), (dark, True)):
            big, small = draw(256, is_dark), draw(48, is_dark)
            bg.paste(big, (20, 20), big)
            bg.paste(small, (310, 40), small)
            tiny = draw(32, is_dark)
            bg.paste(tiny, (318, 120), tiny)
        sheet.paste(light, (10, 10))
        sheet.paste(dark, (450, 10))
        sheet.save(out)
        print("preview", out)


if __name__ == "__main__":
    main()
