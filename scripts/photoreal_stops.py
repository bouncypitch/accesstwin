"""Hero viewpoints for each finding stop in a tour: color + exact depth renders of the metric twin.

    uv run python scripts/photoreal_stops.py out/04_tour/explainer specs/design_a.json

Writes <tour>/hero/stop_NN_color.png and stop_NN_depth.png and stores each camera in tour.json as seg["hero"].
tools/photoreal/photoreal.py turns these into photoreal frames (ControlNet depth + edges keep the geometry), and
scripts/worldlabs.py turns each frame into a Marble world whose origin is this camera.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

from accesstwin.spec import Space

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SIZE = (768, 432)
FOV = 70

tour_dir, spec = Path(sys.argv[1]), sys.argv[2]
space = Space.load(spec)
minx, miny, maxx, maxy = space.floor().bounds
tour = json.loads((tour_dir / "tour.json").read_text())
hero = tour_dir / "hero"
hero.mkdir(exist_ok=True)
page = hero / "twin.html"
subprocess.run(["uv", "run", "python", "scripts/build_viewer.py", spec, str(page)], check=True, capture_output=True)


from shapely.geometry import LineString, Point

FLOOR = space.floor()


def vis_h(o) -> float:
    """Visual height: benches carry a 0.7 m riser shelf above the work surface."""
    return o.height + (0.75 if o.kind == "workbench" else 0.0)


def best_view(L, A, seg):
    """Occlusion-aware hero camera: open floor under the eye, clear sightline over anything taller than the eye line,
    preferring the side the agent approached from."""
    if seg.get("sign"):
        dists, eye_h, tgt_h = (1.8, 2.4, 3.0), seg["sign"]["height"], seg["sign"]["height"]
    elif seg.get("reach") or seg.get("noise") or seg.get("filter") or seg["finding"]["rule_id"] in ("quiet-retreat", "color-only-coding"):
        dists, eye_h, tgt_h = (4.0, 5.0, 6.0), 2.4, 0.5
    else:
        dists, eye_h, tgt_h = (2.8, 3.4, 4.2), 1.65, 0.9
    pref = math.atan2(A[1] - L[1], A[0] - L[0]) if math.dist(A, L) > 0.4 else None
    best = None
    for k in range(36):
        ang = math.radians(k * 10)
        for dist in dists:
            e = (L[0] + math.cos(ang) * dist, L[1] + math.sin(ang) * dist)
            if not FLOOR.buffer(-0.35).contains(Point(e)):
                continue
            if any(o.footprint().buffer(0.5 if vis_h(o) > eye_h - 0.2 else 0.25).contains(Point(e)) for o in space.elements if o.model != "arena"):
                continue
            arena = next((o.footprint() for o in space.elements if o.model == "arena"), None)
            if arena is not None and arena.buffer(0.3).contains(Point(e)) and not arena.contains(Point(L)):
                continue  # don't shoot through the netting from inside the arena
            if arena is not None and not arena.contains(Point(L)) and LineString([e, L]).crosses(arena.exterior) and LineString([e, L]).intersection(arena).length > 0.5:
                blocked_net = 1.0
            else:
                blocked_net = 0.0
            ray = LineString([e, L])
            blocked = 0.0
            for o in space.elements:
                fp = o.footprint() if o.model != "arena" else None
                if fp is None or vis_h(o) < min(eye_h, tgt_h) + 0.1:
                    continue
                if fp.distance(Point(L)) < 0.3:  # the subject itself
                    continue
                blocked += ray.intersection(fp).length
            score = -blocked * 10 - blocked_net * 3 - abs(dist - dists[1])
            if pref is not None:
                score -= 0.8 * abs((ang - pref + math.pi) % (2 * math.pi) - math.pi)
            if best is None or score > best[0]:
                best = (score, e)
    e = best[1]
    return [round(e[0], 3), round(e[1], 3), eye_h], [L[0], L[1], tgt_h]


def clamp(x, lo, hi):
    return min(hi - 0.4, max(lo + 0.4, x))


def shoot(cam: str, dest: Path, extra: str) -> None:
    subprocess.run([CHROME, "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                    f"--window-size={SIZE[0]},{SIZE[1]}", "--virtual-time-budget=6000", f"--screenshot={dest.resolve()}",
                    f"file://{page.resolve()}#cam={cam}&clean&ceil&fov={FOV}{extra}"],
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=120)


n = 0
for seg in tour["segments"]:
    if seg["type"] != "stop":
        continue
    f = seg["finding"]
    L, A = f["location"], seg["at"]
    eye, tgt = best_view(L, A, seg)
    seg["hero"] = {"eye": eye, "target": tgt, "fov": FOV, "index": n}
    cam = ",".join(f"{v:.3f}" for v in eye + tgt)
    shoot(cam, hero / f"stop_{n:02d}_color.png", "")
    shoot(cam, hero / f"stop_{n:02d}_depth.png", "&depth")
    print(f"stop {n}: {f['title'][:60]}  eye {eye}", flush=True)
    n += 1
(tour_dir / "tour.json").write_text(json.dumps(tour, indent=1))
print(f"rendered {n} hero viewpoints into {hero}")
