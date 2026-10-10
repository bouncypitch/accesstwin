"""Renders the RoomScan app icon (1024x1024): an isometric wireframe room with a LiDAR sweep."""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 4096  # supersampled, downscaled at the end
out = sys.argv[1]

# Background: diagonal gradient, deep navy to indigo with a cyan bloom in the lower right.
y, x = np.mgrid[0:S, 0:S] / S
t = (x * 0.55 + y * 0.45)
top, mid, bot = np.array([8, 12, 32]), np.array([28, 30, 92]), np.array([10, 70, 140])
bg = np.where(t[..., None] < 0.6, top + (mid - top) * (t[..., None] / 0.6), mid + (bot - mid) * ((t[..., None] - 0.6) / 0.4))
bloom = np.exp(-(((x - 0.72) ** 2 + (y - 0.70) ** 2) / 0.09))[..., None]
bg = bg + bloom * np.array([0, 120, 170]) * 0.55
img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))

# Isometric projection of a room corner: floor plus two back walls.
def iso(px, py, pz, scale=1250, cx=S * 0.5, cy=S * 0.5 - 137):
    u = (px - py) * math.cos(math.radians(30))
    v = (px + py) * math.sin(math.radians(30)) - pz
    return (cx + u * scale, cy + v * scale)

L, H = 1.0, 0.78
floor = [iso(0, 0, 0), iso(L, 0, 0), iso(L, L, 0), iso(0, L, 0)]
wall_a = [iso(0, 0, 0), iso(L, 0, 0), iso(L, 0, H), iso(0, 0, H)]
wall_b = [iso(0, 0, 0), iso(0, L, 0), iso(0, L, H), iso(0, 0, H)]

glass = Image.new("RGBA", (S, S), (0, 0, 0, 0))
g = ImageDraw.Draw(glass)
g.polygon(wall_a, fill=(120, 200, 255, 38))
g.polygon(wall_b, fill=(160, 140, 255, 30))
g.polygon(floor, fill=(80, 220, 255, 26))

# LiDAR dot grid on the floor, brightest along a sweep line, fading with distance from it.
dots = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(dots)
n = 15
sweep = 0.62
for i in range(n + 1):
    for j in range(n + 1):
        fx, fy = i / n, j / n
        k = math.exp(-((fx + fy) / 2 - sweep) ** 2 / 0.02)
        a = int(60 + 195 * k)
        r = 9 + 10 * k
        px, py = iso(fx * L, fy * L, 0)
        d.ellipse([px - r, py - r, px + r, py + r], fill=(140, 240, 255, a))
# Dots on the walls too, sparser.
for i in range(n + 1):
    for k_ in range(1, 12):
        fz = k_ / 12 * H
        for wall in ("a", "b"):
            f = i / n
            px, py = iso(f * L, 0, fz) if wall == "a" else iso(0, f * L, fz)
            d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=(170, 210, 255, 70))

# Wireframe edges with glow.
lines = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ld = ImageDraw.Draw(lines)
edges = [floor + floor[:1], wall_a[1:3], wall_a[2:4], wall_b[1:3], wall_b[2:4], [iso(0, 0, 0), iso(0, 0, H)]]
for e in edges:
    ld.line(e, fill=(150, 235, 255, 255), width=26, joint="curve")
glow = lines.filter(ImageFilter.GaussianBlur(60))

# Sweep beam: a bright line across the floor at the sweep position, with a soft halo.
beam = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bd = ImageDraw.Draw(beam)
a0 = iso(min(1, 2 * sweep) * L, max(0, 2 * sweep - 1) * L, 0)
a1 = iso(max(0, 2 * sweep - 1) * L, min(1, 2 * sweep) * L, 0)
bd.line([a0, a1], fill=(200, 250, 255, 255), width=34)
beam_glow = beam.filter(ImageFilter.GaussianBlur(110))

base = img.convert("RGBA")
for layer in (glass, dots, glow, glow, lines, beam_glow, beam_glow, beam):
    base = Image.alpha_composite(base, layer)
base.convert("RGB").resize((1024, 1024), Image.LANCZOS).save(out)
print("wrote", out)
