"""Empty the real venue: keep only wall, floor and ceiling points from the fused RGB-D scan, refill the floor where
people and furniture stood, and render a real-color 360-degree equirectangular panorama from the room's center.

    uv run python scripts/empty_venue.py   -> out/05_world/venue/pano_empty.jpg (+ pano_asis.jpg for comparison)

People and furniture are removed geometrically (everything off the wall, floor and ceiling surfaces is dropped),
so nobody captured in the walkthrough appears in the output.
"""
import json
from pathlib import Path

import numpy as np
import shapely
from PIL import Image, ImageFilter
from scipy import ndimage

from accesstwin.roomplan import plan_frame
from accesstwin.rgbd import _floor_height
from accesstwin.spec import Space
from shapely.geometry import Point

ASSETS = Path("demo/assets")
OUT = Path("out/05_world/venue")
OUT.mkdir(parents=True, exist_ok=True)


def read_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    end = raw.index(b"end_header\n") + len(b"end_header\n")
    rec = np.frombuffer(raw[end:], dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    return np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64), np.stack([rec["r"], rec["g"], rec["b"]], 1)


rp = json.loads((ASSETS / "01_scan_venue/roomplan.json").read_text())
frame = plan_frame(rp)
space = Space.load(ASSETS / "01_scan_venue/shell.json")
pts, cols = read_ply(ASSETS / "02_rgbd_venue/fused.ply")
floor_y = _floor_height(rp)
uv = np.array([frame(x, z) for x, z in zip(pts[:, 0], pts[:, 2])]) if len(pts) < 50_000 else None
if uv is None:  # vectorized version of frame()
    u0, v0 = pts[:, 0], -pts[:, 2]
    u = u0 * frame.c - v0 * frame.s - frame.offset[0]
    v = u0 * frame.s + v0 * frame.c - frame.offset[1]
    uv = np.stack([u, v], 1)
h = pts[:, 1] - floor_y
H = space.ceiling_height
print(f"{len(pts):,} points; height range {np.percentile(h, 1):.2f}..{np.percentile(h, 99):.2f} m; ceiling {H:.2f} m")

# Distance from each point to the room boundary (+ inside).
ring = shapely.LineString(space.floor().exterior.coords)
P = shapely.points(uv)
d = shapely.distance(ring, P) * np.where(shapely.contains(space.floor(), P), 1, -1)

# Wall surface per boundary segment: the most common distance among points 0.5-2.5 m up (above furniture tops is
# ideal, but tables are ~0.75 m so this band is dominated by bare wall).
coords = list(space.floor().exterior.coords)
segs = [shapely.LineString([coords[i], coords[i + 1]]) for i in range(len(coords) - 1)]
seg_d = np.stack([shapely.distance(s, P) for s in segs], 1)
seg_id = seg_d.argmin(1)
keep_wall = np.zeros(len(pts), bool)
for i in range(len(segs)):
    m = (seg_id == i) & (d > -0.3) & (d < 0.6)
    band = m & (h > 1.4) & (h < H - 0.3)
    if band.sum() < 200:
        continue
    hist, edges = np.histogram(d[band], bins=np.arange(-0.3, 0.6, 0.01))
    surf = edges[hist.argmax()] + 0.005
    keep_wall |= m & (np.abs(d - surf) < 0.05) & (h > 0.03)
keep_floor = (h < 0.035) & (d > -0.05)
keep_ceil = h > H - 0.25
print(f"kept wall {keep_wall.sum():,}, floor {keep_floor.sum():,}, ceiling {keep_ceil.sum():,}; "
      f"dropped {(~(keep_wall | keep_floor | keep_ceil)).sum():,} (people, furniture, clutter)")

# Floor: rasterize at 3 cm, refill holes with carpet from nearby known cells (texture copy, then a light blur).
cell = 0.03
minx, miny, maxx, maxy = space.floor().bounds
gw, gh = int((maxx - minx) / cell) + 1, int((maxy - miny) / cell) + 1
fi = ((uv[keep_floor, 0] - minx) / cell).astype(int).clip(0, gw - 1)
fj = ((uv[keep_floor, 1] - miny) / cell).astype(int).clip(0, gh - 1)
acc = np.zeros((gw, gh, 3)); cnt = np.zeros((gw, gh))
np.add.at(acc, (fi, fj), cols[keep_floor]); np.add.at(cnt, (fi, fj), 1)
known = cnt > 0
tex = np.where(known[..., None], acc / np.maximum(cnt, 1)[..., None], 0)
# Copy texture from the nearest known cell, offset by a random small jitter so refills look like carpet, not streaks.
_, (ni, nj) = ndimage.distance_transform_edt(~known, return_indices=True)
rng = np.random.default_rng(0)
ji = (ni + rng.integers(-6, 7, ni.shape)).clip(0, gw - 1); jj = (nj + rng.integers(-6, 7, nj.shape)).clip(0, gh - 1)
jitter_ok = known[ji, jj]
src_i = np.where(jitter_ok, ji, ni); src_j = np.where(jitter_ok, jj, nj)
filled = np.where(known[..., None], tex, tex[src_i, src_j])
# Clean carpet: find the best-covered 1.2 m square of real carpet (fully scanned, no furniture shadow), make it
# seamless by mirroring, and tile it across the whole floor. No blotches from hole filling.
P_CELLS = int(1.2 / cell)
cov = ndimage.uniform_filter(known.astype(float), P_CELLS)
lum = tex.mean(-1)
var = ndimage.uniform_filter(lum ** 2, P_CELLS) - ndimage.uniform_filter(lum, P_CELLS) ** 2  # low = no dark shadows
score = cov - 0.002 * var
half = P_CELLS // 2
score[:half] = score[-half:] = -1; score[:, :half] = score[:, -half:] = -1
ci, cj = np.unravel_index(np.argmax(score), score.shape)
patch = tex[ci - half: ci + half, cj - half: cj + half]
tile = np.concatenate([patch, patch[::-1]], 0)
tile = np.concatenate([tile, tile[:, ::-1]], 1)  # mirrored 2x2: seamless
reps = (gw // tile.shape[0] + 1, gh // tile.shape[1] + 1)
filled = np.tile(tile, (reps[0], reps[1], 1))[:gw, :gh]
filled = filled * (tex[known].mean(0) / filled.reshape(-1, 3).mean(0))  # keep the room's average carpet color
print(f"carpet patch at {minx + ci * cell:.1f}, {miny + cj * cell:.1f} m, coverage {cov[ci, cj]:.0%}")
gx, gy = np.meshgrid(np.arange(gw), np.arange(gh), indexing="ij")
fu, fv = minx + (gx.ravel() + 0.5) * cell, miny + (gy.ravel() + 0.5) * cell
inside = shapely.contains(space.floor(), shapely.points(np.stack([fu, fv], 1)))
floor_pts = np.stack([fu[inside], fv[inside], np.zeros(inside.sum())], 1)
floor_cols = filled.reshape(-1, 3)[inside]

# Ceiling: real points where captured, plus a plain plaster plane underneath so the pano has no sky.
ceil_color = np.array([238, 235, 228])  # painted ceiling (the LiDAR barely reaches it at 3.65 m)
cu, cv = minx + (gx.ravel() + 0.5) * cell, miny + (gy.ravel() + 0.5) * cell
cin = inside
ceil_pts = np.stack([cu[cin], cv[cin], np.full(cin.sum(), H)], 1)
ceil_cols = np.tile(ceil_color, (cin.sum(), 1))

# Walls: one texture per boundary segment (2 cm), holes filled from the same height row (plain painted walls
# vary little horizontally), then sampled densely so the panorama has no gaps behind removed furniture.
wall_pts_l, wall_cols_l = [], []
wc = 0.02
for i, sgm in enumerate(segs):
    m = keep_wall & (seg_id == i)
    L = sgm.length
    if L < 0.2:
        continue
    t = shapely.line_locate_point(sgm, P[m])
    nu, nh = int(L / wc) + 1, int(H / wc) + 1
    ti = (t / wc).astype(int).clip(0, nu - 1); hi = (h[m] / wc).astype(int).clip(0, nh - 1)
    acc = np.zeros((nu, nh, 3)); cnt = np.zeros((nu, nh))
    np.add.at(acc, (ti, hi), cols[m]); np.add.at(cnt, (ti, hi), 1)
    known = cnt > 0
    if known.sum() < 50:
        continue
    texw = np.where(known[..., None], acc / np.maximum(cnt, 1)[..., None], 0)
    # Horizontal fill: nearest known cell in the same row; rows with nothing fall back to 2D nearest.
    fill = texw.copy()
    for r in range(nh):
        k = known[:, r]
        if k.any():
            idx = np.where(k, np.arange(nu), 0); np.maximum.accumulate(idx, out=idx)
            first = np.argmax(k); idx[:first] = first
            fill[:, r] = texw[idx, r]
    rows_known = known.any(0)
    if not rows_known.all():
        _, (a, b) = ndimage.distance_transform_edt(~known, return_indices=True)
        fill[:, ~rows_known] = texw[a, b][:, ~rows_known]
    # Furniture pushed against the wall leaves bands below ~1.2 m: rebuild that band from clean wall just above it,
    # with a baseboard strip, except across door openings.
    door_cols = np.zeros(nu, bool)
    for dr in space.doors:
        if sgm.distance(Point(dr.position)) < 0.2:
            t0 = sgm.project(Point(dr.position))
            a, b = int((t0 - dr.clear_width / 2 - 0.1) / wc), int((t0 + dr.clear_width / 2 + 0.1) / wc)
            door_cols[max(a, 0):min(b, nu)] = True
    r_lo, r_hi, r_base = int(1.25 / wc), int(1.6 / wc), int(0.12 / wc)
    clean_wall = np.median(fill[:, r_lo:r_hi], axis=1)  # per column
    base = np.median(fill[~door_cols, 1:r_base].reshape(-1, 3), 0) if (~door_cols).any() else clean_wall.mean(0)
    for r in range(0, int(1.25 / wc)):
        fill[~door_cols, r] = base if r < r_base else clean_wall[~door_cols]
    fill = np.array(Image.fromarray(fill.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), float)
    gu, gv = np.meshgrid(np.arange(nu), np.arange(nh), indexing="ij")
    tt = (gu.ravel() + 0.5) * wc
    xy = shapely.get_coordinates(shapely.line_interpolate_point(sgm, tt))
    wall_pts_l.append(np.stack([xy[:, 0], xy[:, 1], (gv.ravel() + 0.5) * wc], 1))
    wall_cols_l.append(fill.reshape(-1, 3))
wall_pts = np.concatenate(wall_pts_l)
wall_tex_cols = np.concatenate(wall_cols_l)
bright = keep_ceil & (cols.mean(1) > 200)  # keep only captured ceiling pixels that are lit plaster or downlights
keep_ceil = bright
real_ceil = np.stack([uv[keep_ceil, 0], uv[keep_ceil, 1], h[keep_ceil]], 1)
scene_pts = np.concatenate([wall_pts, real_ceil, floor_pts, ceil_pts])
scene_cols = np.concatenate([wall_tex_cols, cols[keep_ceil], floor_cols, ceil_cols]).astype(np.uint8)


def pano(points: np.ndarray, colors: np.ndarray, eye, W=4096, Hh=2048, splat=2) -> Image.Image:
    v = points - np.array(eye)
    r = np.linalg.norm(v, axis=1) + 1e-9
    lon = np.arctan2(v[:, 1], v[:, 0])  # 0 = +x (east), CCW
    lat = np.arcsin(v[:, 2] / r)
    # Equirect: center column looks east (+x); left of center is north.
    px = ((0.5 - lon / (2 * np.pi)) * W).astype(int) % W
    py = ((0.5 - lat / np.pi) * Hh).astype(int).clip(0, Hh - 1)
    depth = np.full((Hh, W), np.inf); img = np.zeros((Hh, W, 3), np.uint8)
    order = np.argsort(-r)  # far first, near overwrites
    for dx in range(-splat + 1, splat):
        for dy in range(-splat + 1, splat):
            xx = (px[order] + dx) % W; yy = (py[order] + dy).clip(0, Hh - 1)
            img[yy, xx] = colors[order]; depth[yy, xx] = np.minimum(depth[yy, xx], r[order])
    hole = ~np.isfinite(depth)
    _, (ii, jj) = ndimage.distance_transform_edt(hole, return_indices=True)
    img = img[ii, jj]
    return Image.fromarray(img).filter(ImageFilter.MedianFilter(3))


eye = ((minx + maxx) / 2, (miny + maxy) / 2, 1.5)
pano(scene_pts, scene_cols, eye).save(OUT / "pano_empty.jpg", quality=92)
asis = np.stack([uv[:, 0], uv[:, 1], h], 1)
pano(np.concatenate([asis, ceil_pts]), np.concatenate([cols, ceil_cols]).astype(np.uint8), eye).save(OUT / "pano_asis.jpg", quality=92)
Image.fromarray(np.transpose(filled.astype(np.uint8), (1, 0, 2))[::-1]).save(OUT / "floor_refilled.jpg", quality=90)
print(f"wrote {OUT}/pano_empty.jpg, pano_asis.jpg, floor_refilled.jpg (eye at {eye[0]:.1f}, {eye[1]:.1f})")

# Story asset: the as-scanned cloud with a per-point flag (0 kept surface, 1 removed: people/furniture/clutter,
# 2 added: re-tiled carpet), downsampled for the browser. float32 x,y,z (plan meters) + uint8 r,g,b,flag.
rng2 = np.random.default_rng(1)
asis_pts = np.stack([uv[:, 0], uv[:, 1], h], 1)
kept = keep_wall | keep_floor | keep_ceil
flag = np.where(kept, 0, 1).astype(np.uint8)
inside_room = (d > -0.15) & (h > -0.05) & (h < H + 0.05)
sel = np.where(inside_room)[0]
sel = sel[rng2.random(len(sel)) < 380_000 / max(len(sel), 1)]
add_sel = rng2.random(len(floor_pts)) < 0.35
P3 = np.concatenate([asis_pts[sel], floor_pts[add_sel] + [0, 0, 0.004]]).astype(np.float32)
C3 = np.concatenate([cols[sel], floor_cols[add_sel].clip(0, 255)]).astype(np.uint8)
F3 = np.concatenate([flag[sel], np.full(add_sel.sum(), 2, np.uint8)])
buf = np.zeros(len(P3), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1"), ("f", "u1")])
buf["x"], buf["y"], buf["z"] = P3.T
buf["r"], buf["g"], buf["b"] = C3.T
buf["f"] = F3
(OUT / "scan_points.bin").write_bytes(buf.tobytes())
print(f"wrote {OUT}/scan_points.bin: {len(buf):,} points ({(F3 == 1).sum():,} removed, {(F3 == 2).sum():,} carpet refill)")
