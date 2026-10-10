"""Neurodivergent worker (autism, ADHD, sensory processing): noise, visual motion, wayfinding, consistency, retreat."""

from __future__ import annotations

import math

from shapely.geometry import LineString

from ..findings import IN, Citation, Finding, Fix
from ..spec import Element, Space
from .base import AuditContext, Body, Persona, approach_point

ID = "neurodivergent"

PAS = Citation(source="BSI PAS 6463:2022 Design for the mind: neurodiversity and the built environment", section="",
               url="https://knowledge.bsigroup.com/products/design-for-the-mind-neurodiversity-and-the-built-environment-guide",
               basis="best_practice")
S12 = Citation(source="ANSI/ASA S12.2 room noise criteria; PAS 6463 acoustic zoning", section="",
               url="https://webstore.ansi.org/standards/asa/ansiasas122019", basis="best_practice")

# Typical A-weighted sound level at 1 m while running (manufacturer and EHS survey figures).
# The CNC is specified inside an enclosure (~-13 dB); the assembly bench figure is the drill press in use.
NOISE_DBA_1M = {"cnc": 72, "mech_bench": 75, "hil_bench": 72, "laser_cutter": 65, "industrial_cage": 70,
                "arena": 68, "printer_bank": 50, "cobot_small": 55, "cobot_large": 55}
QUIET = {"desk_row", "esd_bench", "solder_station", "dining_table"}  # focused work or rest
QUIET_LIMIT = 55.0  # dBA at the seat from lab equipment
MOTION = {"arena", "cobot_small", "cobot_large", "industrial_cage"}
MOTION_DIST = 2.0  # m: continuous robot motion this close to a seat pulls attention
MAX_TURNS = 4


def level_at(space: Space, at: tuple[float, float]) -> tuple[float, list[tuple[str, float]]]:
    parts = []
    for e in space.elements:
        L1 = NOISE_DBA_1M.get(e.model or "")
        if L1 is None:
            continue
        r = max(1.0, e.footprint().distance(LineString([at, at]).centroid) + 0.3)
        parts.append((e.label or e.id, L1 - e.attenuation_db - 20 * math.log10(r)))
    total = 10 * math.log10(sum(10 ** (lv / 10) for _, lv in parts)) if parts else 0.0
    return total, sorted(parts, key=lambda p: -p[1])


def turns(path: list[tuple[float, float]]) -> int:
    if len(path) < 3:
        return 0
    simple = list(LineString(path).simplify(0.6).coords)
    n = 0
    for a, b, c in zip(simple, simple[1:], simple[2:]):
        h1 = math.atan2(b[1] - a[1], b[0] - a[0])
        h2 = math.atan2(c[1] - b[1], c[0] - b[0])
        if abs((h2 - h1 + math.pi) % (2 * math.pi) - math.pi) > math.radians(40):
            n += 1
    return n


class Neurodivergent(Persona):
    id = ID
    name = "Neurodivergent worker"
    summary = "Autistic / ADHD / sensory-processing differences: sensitive to noise and motion, relies on predictable layouts."
    body = Body(path_width=36 * IN, eye_height=1.6)
    criteria = [
        ("Quiet stations (desks, ESD benches, soldering, dining) at 55 dBA or less from lab equipment", "ANSI/ASA S12.2, PAS 6463"),
        ("No continuous robot motion within 2 m of a seat without a screen", "PAS 6463"),
        ("Every station reachable from the entrance in 4 turns or fewer", "PAS 6463"),
        ("One consistent sign system: same colors, layout and letter size", "PAS 6463"),
        ("An enclosed quiet retreat room", "PAS 6463"),
    ]

    def audit(self, space: Space, ctx: AuditContext) -> list[Finding]:
        return self.noise(space) + self.motion(space) + self.wayfinding(space, ctx) + self.consistency(space) + self.retreat(space)

    def seat(self, e: Element) -> tuple[float, float]:
        return e.front_point(0.35)

    def noise(self, space: Space) -> list[Finding]:
        out = []
        for e in space.elements:
            if e.model not in QUIET:
                continue
            at = self.seat(e)
            total, parts = level_at(space, at)
            ok = total <= QUIET_LIMIT
            top = parts[0] if parts else ("-", 0)
            out.append(Finding(
                agent=ID, rule_id="noise-at-quiet-station", title=f"Noise at {e.label}", passed=ok,
                severity="major" if total > QUIET_LIMIT + 10 else "minor", element_id=e.id, location=at,
                measured=round(total, 1), required=f"<= {QUIET_LIMIT:.0f} dBA from lab equipment", citation=S12,
                detail=(f"About {total:.0f} dBA while equipment runs; loudest is {top[0]} ({top[1]:.0f} dBA here)."),
                fix=None if ok else Fix(summary=f"Enclose {top[0]} in an acoustic enclosure (-15 dB), or move it away from {e.label}.",
                                        op="set", element_id=next(x.id for x in space.elements if (x.label or x.id) == top[0]),
                                        params={"attenuation_db": 15.0}),
            ))
        return out

    def motion(self, space: Space) -> list[Finding]:
        out = []
        movers = [m for m in space.elements if m.model in MOTION]
        for e in space.elements:
            if e.model not in QUIET:
                continue
            at = self.seat(e)
            near = min(((m.obstacle().distance(LineString([at, at]).centroid), m) for m in movers),
                       key=lambda t: t[0], default=(99, None))
            ok = near[0] >= MOTION_DIST or e.screen_height >= 1.4
            out.append(Finding(
                agent=ID, rule_id="visual-motion", title=f"Robot motion in view at {e.label}", passed=ok,
                severity="minor", element_id=e.id, location=at, measured=round(near[0], 2),
                required=f">= {MOTION_DIST:.1f} m from moving robots, or a visual screen", citation=PAS,
                detail=(f"{near[1].label} moves {near[0]:.1f} m from the seat." if near[1] else ""),
                fix=None if ok else Fix(summary=f"Add a 1.5 m visual screen between {e.label} and {near[1].label}, or move the seats.",
                                        op="set", element_id=e.id, params={"screen_height": 1.5}),
            ))
        return out

    def wayfinding(self, space: Space, ctx: AuditContext) -> list[Finding]:
        out = []
        if ctx.planner is None:
            return out
        for e in space.elements:
            if e.kind not in ("workbench", "workstation", "table", "equipment", "cabinet", "storage", "shelf"):
                continue
            r = ctx.planner.route(approach_point(e, e.front_point()), 0.5)
            if not r.path:
                continue
            n = turns(r.path)
            ok = n <= MAX_TURNS
            out.append(Finding(
                agent=ID, rule_id="wayfinding-turns", title=f"Wayfinding to {e.label}", passed=ok, severity="minor",
                element_id=e.id, location=r.path[len(r.path) // 2], measured=n, required=f"<= {MAX_TURNS} turns from the entrance",
                citation=PAS, detail=f"{n} turns over {r.length:.1f} m from the main entrance.", path=r.path,
                fix=None if ok else Fix(summary=f"Give {e.label} a straight sightline from the main aisle, or add a directional sign at each turn."),
            ))
        return out

    def consistency(self, space: Space) -> list[Finding]:
        styles = {}
        for e in space.elements:
            if e.sign:
                styles.setdefault((e.sign.fg, e.sign.bg == "#ffffff"), []).append(e.zone)
        dark_on_light = sorted({z for (fg, light_bg), zs in styles.items() if light_bg for z in zs if z})
        sizes = {round(e.sign.text_height, 3) for e in space.elements if e.sign and e.sign.mount_height < 2.0}
        ok = not dark_on_light and len(sizes) <= 1
        return [Finding(
            agent=ID, rule_id="sign-consistency", title="One consistent sign system", passed=ok, severity="minor",
            location=(9.0, 5.5), required="same layout, color scheme and letter size everywhere", citation=PAS,
            detail=("Signs switch between white-on-color and pastel-on-white in zones: " + ", ".join(dark_on_light)
                    + f"; {len(sizes)} different letter sizes.") if not ok else "Signs follow one system.",
            fix=None if ok else Fix(summary="Use one sign template: white letters on the zone color, same size and height."),
        )]

    def retreat(self, space: Space) -> list[Finding]:
        has = any("quiet" in (e.label or "").lower() for e in space.elements)
        return [Finding(
            agent=ID, rule_id="quiet-retreat", title="Quiet retreat room", passed=has, severity="major",
            location=(1.2, 7.0), required="an enclosed low-stimulus room off the main circulation", citation=PAS,
            detail="There is nowhere to step away from noise, light and robot motion." if not has else "Quiet room provided.",
            fix=None if has else Fix(summary="Add an enclosed quiet room (about 2.4 x 2.4 m) near the entrance, away from fabrication.", op="add"),
        )]
