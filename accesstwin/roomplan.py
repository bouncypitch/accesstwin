"""Import an Apple RoomPlan CapturedRoom (JSON from the RoomScan app) into a SpaceSpec.

RoomPlan is y-up and right-handed; transforms are column-major 4x4. Plan coordinates are (x, -z) seen from
above, then rotated so the longest wall runs along +x and shifted so the room starts at (0, 0).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.validation import make_valid

from .spec import Door, Element, Source, Space

# Objects removed for each import mode. "empty" clears the floor completely for a redesign; "movable" keeps
# fixed items (cabinets, appliances) as constraints; "none" is the room as scanned.
MOVABLE = {"chair", "table", "sofa", "bed", "television"}
KIND = {
    "chair": "seating", "sofa": "seating", "bed": "equipment", "table": "table", "storage": "storage",
    "refrigerator": "equipment", "stove": "equipment", "oven": "equipment", "dishwasher": "equipment",
    "sink": "equipment", "washerDryer": "equipment", "toilet": "equipment", "bathtub": "equipment",
    "fireplace": "equipment", "television": "equipment", "stairs": "equipment",
}
DOUBLE_DOOR_MIN = 1.5  # openings wider than this are treated as a pair of leaves
STOP_ALLOWANCE = 0.05  # door thickness and stops eat into the opening; ADA clear width is measured inside them


def _matrix(o: dict) -> np.ndarray:
    return np.array(o["transform"], dtype=float).reshape(4, 4).T


def _category(o: dict) -> str:
    c = o["category"]
    return next(iter(c)) if isinstance(c, dict) else str(c)


class _Frame:
    """World (x, y, z) -> plan (u, v) in meters."""

    def __init__(self, theta: float, offset: tuple[float, float]):
        self.c, self.s = math.cos(-theta), math.sin(-theta)
        self.offset = offset

    def raw(self, x: float, z: float) -> tuple[float, float]:
        u, v = x, -z
        return (u * self.c - v * self.s, u * self.s + v * self.c)

    def __call__(self, x: float, z: float) -> tuple[float, float]:
        u, v = self.raw(x, z)
        return (round(u - self.offset[0], 4), round(v - self.offset[1], 4))

    def heading(self, m: np.ndarray, axis: int = 0) -> float:
        """Plan angle (degrees) of an object's local axis."""
        a = m[:3, axis]
        u, v = a[0], -a[2]
        u, v = u * self.c - v * self.s, u * self.s + v * self.c
        return math.degrees(math.atan2(v, u))


def load(path: str | Path, remove: str = "empty", name: str | None = None) -> Space:
    assert remove in ("empty", "movable", "none")
    d = json.loads(Path(path).read_text())
    walls = d["walls"]
    longest = max(walls, key=lambda w: w["dimensions"][0])
    lw = _matrix(longest)[:3, 0]
    theta = math.atan2(-lw[2], lw[0])

    floor = d["floors"][0]
    fm = _matrix(floor)
    corners = [fm @ np.array([*c, 1.0]) for c in floor["polygonCorners"]]
    floor_y = float(np.mean([c[1] for c in corners]))
    frame = _Frame(theta, (0.0, 0.0))
    raw = [frame.raw(c[0], c[2]) for c in corners]
    frame.offset = (min(p[0] for p in raw), min(p[1] for p in raw))
    outline = [frame(c[0], c[2]) for c in corners]
    poly = make_valid(Polygon(outline))
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    outline = [tuple(p) for p in list(poly.exterior.coords)[:-1]]

    lidar = lambda note="": Source(kind="lidar", confidence=0.9, note=note)
    doors: list[Door] = []
    for i, o in enumerate([*d["doors"], *d["openings"]]):
        m = _matrix(o)
        pos = frame(m[0, 3], m[2, 3])
        width = float(o["dimensions"][0])
        # The surface normal is local z; point it into the room.
        n = m[:3, 2]
        nu, nv = n[0], -n[2]
        nu, nv = nu * frame.c - nv * frame.s, nu * frame.s + nv * frame.c
        if not poly.contains(Point(pos[0] + nu * 0.5, pos[1] + nv * 0.5)):
            nu, nv = -nu, -nv
        is_opening = _category(o) == "opening"
        if is_opening:
            clear, note = width, "open doorway; width from LiDAR"
        elif width >= DOUBLE_DOOR_MIN:
            clear = width / 2 - STOP_ALLOWANCE
            note = f"double door, {width:.2f} m opening; clear width per leaf estimated, verify with tape"
        else:
            clear = width - STOP_ALLOWANCE
            note = f"{width:.2f} m opening; clear width estimated, verify with tape"
        doors.append(Door(
            id=f"D{i + 1}", position=pos, inward=(round(nu, 4), round(nv, 4)), clear_width=round(clear, 3),
            hardware="none" if is_opening else "lever", role="both", source=lidar(note),
        ))
    if doors:
        doors[0].role = "entrance"

    elements: list[Element] = []
    counts: dict[str, int] = {}
    for o in d["objects"]:
        cat = _category(o)
        if remove == "empty" or (remove == "movable" and cat in MOVABLE):
            continue
        m = _matrix(o)
        w, h, dep = (float(x) for x in o["dimensions"])
        counts[cat] = counts.get(cat, 0) + 1
        top = m[1, 3] - floor_y + h / 2
        elements.append(Element(
            id=f"{cat}{counts[cat]}", kind=KIND.get(cat, "equipment"), label=f"Existing {cat} {counts[cat]}",
            center=frame(m[0, 3], m[2, 3]), size=(round(w, 3), round(dep, 3)),
            rotation_deg=round(frame.heading(m), 2), height=round(top, 3),
            work_surface_height=round(top, 3) if cat == "table" else None,
            source=lidar(f"RoomPlan {cat}, confidence {next(iter(o['confidence']))}"),
        ))

    height = float(np.median([w["dimensions"][1] for w in walls]))
    return Space(
        name=name or {"none": "Scanned room (as-is)", "movable": "Scanned room (fixed items only)",
                      "empty": "Scanned room (empty shell)"}[remove],
        outline=outline, ceiling_height=round(height, 3), doors=doors, elements=elements,
        source=Source(kind="lidar", confidence=0.9,
                      note=f"Apple RoomPlan, {len(walls)} walls, {len(d['objects'])} objects scanned"),
    )


def wall_lengths(path: str | Path) -> list[float]:
    d = json.loads(Path(path).read_text())
    return sorted((float(w["dimensions"][0]) for w in d["walls"]), reverse=True)
