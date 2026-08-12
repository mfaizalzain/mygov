#!/usr/bin/env python3
"""Generate the Open Graph / social preview image (1200x630)."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "og-image.png")

# Dark brand background with subtle teal glow
img = Image.new("RGB", (W, H), "#0a0c10")
d = ImageDraw.Draw(img)
for y in range(H):
    t = y / H
    # gentle vertical gradient toward a teal tint at the bottom
    r = int(10 + (18 - 10) * t)
    g = int(12 + (40 - 12) * t)
    b = int(16 + (45 - 16) * t)
    d.line([(0, y), (W, y)], fill=(r, g, b))

# accent bar
d.rectangle([0, 0, 12, H], fill="#2dd4bf")

def font(size, bold=False):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

f_big = font(96)
f_mid = font(40)
f_small = font(30)

# The brand sets over two lines: "Malaysia at a Glance" at 96px runs past the
# 1200px canvas, and shrinking it to fit would lose the wordmark's weight.
d.text((64, 120), "Malaysia", font=f_big, fill="#e8ecf4")
d.text((64, 225), "at a Glance", font=f_big, fill="#e8ecf4")
d.text((64, 355), "Live government open data", font=f_mid, fill="#2dd4bf")
d.text((64, 430), "weather · fuel prices · economy · transport", font=f_small, fill="#9aa4b8")

d.text((64, 540), "malaysia-at-a-glance.com", font=f_small, fill="#5f6b80")

img.save(OUT, optimize=True)
print(f"✅ {OUT} ({os.path.getsize(OUT)//1024} KB)")
