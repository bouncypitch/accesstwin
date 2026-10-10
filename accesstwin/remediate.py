"""Remediation agent: applies the persona agents' fixes to a SpaceSpec, re-audits, and repeats.

Every change is validated (stays in the room, no new overlaps, keeps door approaches clear) and logged against
the finding it addresses, so Design B is traceable change by change.
"""

from __future__ import annotations

import copy
import math

from pydantic import BaseModel
from shapely.geometry import Point, box as sbox

from .agents.low_vision import contrast, delta_e, CVD
from .agents.motion import CRUSH_GAP, MESH_DISTANCE, REACH
from .audit import Report, audit
from .findings import Finding
from .spec import Element, KneeClearance, Sign, Source, Space

# Okabe-Ito based wayfinding palette, darkened so white lettering reaches 4.5:1 and lightness separates hues for CVD.
CVD_SAFE = ["#0057a8", "#a34a00", "#007a5a", "#7a3f9d", "#8a6d00", "#b0306a", "#1b5e7a", "#4d4d4d", "#5c5c00"]


PUSH_FURNITURE = False  # multi-object relocation; off: it tends to trade one pinch point for another in crowded rooms


class Change(BaseModel):
    agent: str
    rule_id: str
    finding: str
    change: str


def darken_until(color: str, fg: str = "#ffffff", target: float = 4.6) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    for _ in range(40):
        c = f"#{r:02x}{g:02x}{b:02x}"
        if contrast(fg, c) >= target:
            return c
        r, g, b = int(r * 0.93), int(g * 0.93), int(b * 0.93)
    return "#1f2328"


def valid(space: Space, el: Element) -> bool:
    floor = space.floor()
    if not floor.buffer(1e-6).contains(el.footprint()):
        return False
    for o in space.elements:
        if o.id == el.id:
            continue
        if o.footprint().intersection(el.footprint()).area > 1e-4:
            return False
    for d in space.doors:  # keep a 1.2 m deep clear approach inside every door
        ix, iy = d.inward
        tx, ty = -iy, ix
        hw = d.clear_width / 2 + 0.1
        pts = [(d.position[0] + tx * s * hw + ix * k, d.position[1] + ty * s * hw + iy * k) for s in (-1, 1) for k in (0, 1.2)]
        zone = sbox(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        if el.obstacle().intersection(zone).area > 1e-4:
            return False
    return True


def try_move(space: Space, el: Element, dx: float, dy: float) -> bool:
    old = el.center
    for scale in (1.0, 1.25, 1.5, 2.0):
        el.center = (round(old[0] + dx * scale, 3), round(old[1] + dy * scale, 3))
        for p in el.parts:
            p.position = (p.position[0] + el.center[0] - old[0], p.position[1] + el.center[1] - old[1])
        if valid(space, el):
            return True
        for p in el.parts:
            p.position = (p.position[0] - (el.center[0] - old[0]), p.position[1] - (el.center[1] - old[1]))
        el.center = old
    return False


def set_param(space: Space, el: Element | None, key: str, value) -> str | None:
    if el is None:
        return None
    if key.startswith("sign."):
        if el.sign is None:
            return None
        k = key[5:]
        if k == "bg" and value == "darken":
            zc = next((z.color for z in space.zones if z.id == el.zone), "#1f2328")
            value = darken_until(zc)
        setattr(el.sign, k, value)
        return f"{el.label}: sign {k} -> {value}"
    setattr(el, key, value)
    return f"{el.label}: {key} -> {value}"


def apply_fix(space: Space, f: Finding) -> str | None:
    fix = f.fix
    if fix is None:
        return None
    el = next((e for e in space.elements if e.id == fix.element_id), None)
    door = next((d for d in space.doors if d.id == fix.element_id), None)
    if fix.op == "move" and el is not None:
        if "dx" in fix.params:
            options = [(fix.params["dx"], fix.params["dy"])]
            other = fix.params.get("away_from")
            if other and other != "wall":
                # Push directly away from the other obstacle along whichever axis separates them.
                from shapely.ops import nearest_points
                a, b = nearest_points(el.footprint(), space.element(other).obstacle())
                vx, vy = a.x - b.x, a.y - b.y
                sf = fix.params.get("shortfall", math.hypot(*options[0]))
                options += [(math.copysign(sf, vx or 1), 0.0), (0.0, math.copysign(sf, vy or 1))]
            for dx, dy in options:
                if try_move(space, el, dx, dy):
                    return f"Moved {el.label} by ({dx:+.2f}, {dy:+.2f}) m"
            return None
        return move_clear_of_walls(space, el)
    if fix.op == "set":
        if door is not None:
            for k, v in fix.params.items():
                setattr(door, k, v)
            return f"Door {door.id}: " + ", ".join(f"{k} -> {v}" for k, v in fix.params.items())
        if el is not None and "part" in fix.params:
            part = next(p for p in el.parts if p.id == fix.params["part"])
            part.height = fix.params["height"]
            if "obstruction_depth" in fix.params:
                part.obstruction_depth = fix.params["obstruction_depth"]
            return f"Remounted {part.id} on {el.label} at {part.height / 0.0254:.0f}\""
        if f.rule_id == "sweep-in-zone" and el is not None:
            return contain_sweep(space, el)
        if el is not None:
            msgs = [set_param(space, el, k, v) for k, v in fix.params.items()]
            return "; ".join(m for m in msgs if m) or None
    return None


def already_set(space: Space, f: Finding) -> bool:
    el = next((e for e in space.elements if e.id == f.fix.element_id), None)
    if el is None or "part" in f.fix.params:
        return False
    for k, v in f.fix.params.items():
        cur = getattr(el.sign, k[5:], None) if k.startswith("sign.") and el.sign else getattr(el, k, None)
        if cur != v:
            return False
    return True


def reach_of(el: Element) -> float:
    r = REACH[el.model]
    return min(r, el.reach_limit) if el.reach_limit else r


def move_clear_of_walls(space: Space, el: Element) -> str | None:
    """Robot cell whose reach crowds a wall or furniture: slide it toward open floor, else limit its reach."""
    if el.model not in REACH:
        return None
    best = None
    steps = [0] + [s * k / 20 for k in range(1, 21) for s in (-1, 1)]  # up to 1 m each way
    for dx in steps:
        for dy in steps:
            trial = copy.deepcopy(el)
            trial.center = (el.center[0] + dx, el.center[1] + dy)
            others = [o for o in space.elements if o.id != el.id]
            sweep = Point(trial.center).buffer(REACH[trial.model])
            walls = sbox(-50, -50, 50, 50).difference(space.floor())
            gap = min([sweep.distance(walls)] + [sweep.distance(o.footprint()) for o in others if o.model != "arena"])
            tmp = copy.deepcopy(space)
            tmp.elements = [trial if o.id == el.id else o for o in tmp.elements]
            if gap >= CRUSH_GAP and valid(tmp, trial) and (best is None or abs(dx) + abs(dy) < best[0]):
                best = (abs(dx) + abs(dy), dx, dy)
    if best is None and PUSH_FURNITURE:
        # Second pass: relocate the arm far enough from walls, then push the furniture it would crowd.
        from shapely.ops import nearest_points
        for dx in steps:
            for dy in steps:
                trial = copy.deepcopy(el)
                trial.center = (el.center[0] + dx, el.center[1] + dy)
                sweep = Point(trial.center).buffer(REACH[trial.model])
                walls = sbox(-50, -50, 50, 50).difference(space.floor())
                tmp = copy.deepcopy(space)
                tmp.elements = [trial if o.id == el.id else o for o in tmp.elements]
                if sweep.distance(walls) < CRUSH_GAP or not valid(tmp, trial):
                    continue
                blockers = [o for o in tmp.elements if o.id != el.id and o.model != "arena" and sweep.distance(o.footprint()) < CRUSH_GAP]
                ok = True
                for o in blockers:
                    a, b = nearest_points(o.footprint(), sweep)
                    need = CRUSH_GAP - sweep.distance(o.footprint()) + 0.03
                    vx, vy = a.x - b.x, a.y - b.y
                    mv = (math.copysign(need, vx), 0.0) if abs(vx) >= abs(vy) else (0.0, math.copysign(need, vy))
                    if not try_move(tmp, o, *mv) or sweep.distance(o.footprint()) < CRUSH_GAP - 1e-6:
                        ok = False
                        break
                if ok and (best is None or abs(dx) + abs(dy) < best[0]):
                    best = (abs(dx) + abs(dy), dx, dy, tmp, [o.label for o in blockers])
        if best is not None:
            _, dx, dy, tmp, pushed = best
            space.elements = tmp.elements
            moved = next(o for o in space.elements if o.id == el.id)
            moved.reach_limit = None
            return (f"Moved {el.label} by ({dx:+.2f}, {dy:+.2f}) m and shifted {', '.join(pushed)} "
                    "to keep a 0.5 m crush gap at full reach")
    if best:
        _, dx, dy = best[:3]
        el.center = (round(el.center[0] + dx, 3), round(el.center[1] + dy, 3))
        el.reach_limit = None
        for p in el.parts:
            p.position = (p.position[0] + dx, p.position[1] + dy)
        return f"Moved {el.label} by ({dx:+.2f}, {dy:+.2f}) m to keep a 0.5 m crush gap at full reach"
    # Otherwise cap the reach with a safety-rated soft axis limit.
    others = [o.footprint() for o in space.elements if o.id != el.id and o.model != "arena"]
    walls = sbox(-50, -50, 50, 50).difference(space.floor())
    c = Point(el.center)
    room = min([c.distance(walls)] + [c.distance(o) for o in others])
    limit = round(room - CRUSH_GAP, 2)
    if limit < 0.6:
        return None
    el.reach_limit = limit
    return f"{el.label}: safety-rated reach limit {limit:.2f} m (ISO 10218 soft axis limiting)"


def contain_sweep(space: Space, el: Element) -> str | None:
    """Arm sweeps past its tape line or fence: widen the zone if there is room, else limit the reach."""
    reach = reach_of(el)
    need = MESH_DISTANCE if el.model == "industrial_cage" else 0.0
    half = max(el.size) / 2
    margin = round(reach + need + 0.05 - half, 2) if el.model == "industrial_cage" else round(reach + 0.05 - half * 0.0 - half, 2)
    trial = copy.deepcopy(el)
    trial.safeguard_margin = max(el.safeguard_margin, margin)
    tmp = copy.deepcopy(space)
    tmp.elements = [trial if o.id == el.id else o for o in tmp.elements]
    others_ok = all(trial.obstacle().intersection(o.footprint()).area < 1e-4 for o in space.elements
                    if o.id != el.id and o.model != "arena") and space.floor().buffer(0.05).contains(trial.obstacle())
    if others_ok:
        el.safeguard_margin = trial.safeguard_margin
        for p in el.parts:  # keep e-stops on the new boundary
            if p.kind == "e_stop":
                dx, dy = p.position[0] - el.center[0], p.position[1] - el.center[1]
                n = math.hypot(dx, dy) or 1
                d = half + el.safeguard_margin + 0.05
                p.position = (round(el.center[0] + dx / n * d, 3), round(el.center[1] + dy / n * d, 3))
        return f"{el.label}: {'fence' if need else 'tape line'} moved out to {half + el.safeguard_margin:.2f} m from the base"
    zone_half = half + el.safeguard_margin
    el.reach_limit = round(zone_half - need - 0.05, 2)
    return f"{el.label}: safety-rated reach limit {el.reach_limit:.2f} m keeps the arm inside its {'fence' if need else 'zone'}"


def cvd_palette(n: int) -> list[str]:
    """Greedy max-min palette: dark enough for white text (>= 4.6:1), maximally distinct for typical, protan and deutan vision."""
    import colorsys
    cands = []
    for h in range(0, 360, 10):
        for l in (0.24, 0.30, 0.36, 0.42):
            for sat in (0.55, 0.9):
                r, g, b = colorsys.hls_to_rgb(h / 360, l, sat)
                c = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
                if contrast("#ffffff", c) >= 4.6:
                    cands.append(c)
    gray = ["#4a4f57"]
    cands += gray

    def dist(a, b):
        return min(delta_e(a, b), *(delta_e(a, b, k) for k in CVD))
    pal = ["#0057a8"]
    while len(pal) < n:
        pal.append(max(cands, key=lambda c: min(dist(c, p) for p in pal)))
    return pal


def recolor_zones(space: Space) -> str:
    for z, c in zip(space.zones, cvd_palette(len(space.zones))):
        z.color = c
    for e in space.elements:
        if e.sign:
            zc = next(z.color for z in space.zones if z.id == e.zone)
            e.sign.fg, e.sign.bg = "#ffffff", zc
    return "Zone palette -> color-blind-safe, darkened for white lettering (" + ", ".join(z.color for z in space.zones) + ")"


def add_quiet_room(space: Space) -> str | None:
    """Place a quiet room in the quietest free spot: 36" clear around it, entrance kept clear, still reachable."""
    from .agents.base import AuditContext
    from .agents.neurodivergent import level_at
    floor = space.floor()
    cands = []
    for size in ((2.4, 2.4), (2.2, 2.0)):
        for x in [i * 0.2 for i in range(5, 92)]:
            for y in [j * 0.2 for j in range(5, 57)]:
                el = Element(id="quiet", kind="partition", label="Quiet room", center=(x, y), size=size, height=2.4,
                             zone="welcome", model="quiet_room", source=Source(kind="design", note="Design B"))
                if not floor.contains(el.footprint()):
                    continue
                tmp = copy.deepcopy(space)
                tmp.elements.append(el)
                if not valid(tmp, el) or any(el.footprint().distance(o.obstacle()) < 0.3 for o in space.elements):
                    continue
                cands.append((level_at(space, (x, y))[0], el))
        if cands:
            break
    for lv, el in sorted(cands, key=lambda c: c[0])[:25]:
        tmp = copy.deepcopy(space)
        tmp.elements.append(el)
        ctx = AuditContext(tmp)
        if ctx.planner and ctx.planner.route(el.front_point(0.6), 0.92).reachable:
            zc = next(z.color for z in space.zones if z.id == "welcome")
            el.sign = Sign(text="Quiet room", fg="#ffffff", bg=zc, text_height=0.05, mount_height=54 * 0.0254,
                           tactile=True, pictogram=True)
            space.elements.append(el)
            return f"Added a {el.size[0]:.1f} x {el.size[1]:.1f} m quiet room at ({el.center[0]:.1f}, {el.center[1]:.1f}), {lv:.0f} dBA"
    return None


def remediate(space: Space, rounds: int = 6) -> tuple[Space, list[Change], list[Report]]:
    space = copy.deepcopy(space)
    space.name = space.name.replace("Design A", "Design B")
    changes: list[Change] = []
    reports = [audit(space)]
    global_done = set()
    for _ in range(rounds):
        before = reports[-1]
        applied = 0
        seen: set = set()
        GLOBAL = ("zone-color-cvd", "color-only-coding", "sign-consistency")
        rank = lambda f: (0 if f.rule_id in GLOBAL else 1 if f.rule_id == "route-clear-width" else 2 if f.rule_id == "crush-gap"
                          else 4 if f.rule_id == "quiet-retreat" else 3)
        for f in sorted(before.failures(), key=rank):
            msg = None
            key = (f.fix.op, f.fix.element_id, str(sorted(f.fix.params.items()))) if f.fix else None
            if key is not None and f.rule_id not in ("zone-color-cvd", "color-only-coding", "sign-consistency", "quiet-retreat"):
                if key in seen or (f.fix.op == "set" and already_set(space, f)):
                    continue
                seen.add(key)
            if f.rule_id in ("zone-color-cvd", "color-only-coding", "sign-consistency"):
                if "palette" not in global_done:
                    msg = recolor_zones(space)
                    for e in space.elements:
                        if e.sign:
                            e.sign.pictogram = True
                            e.sign.text_height = max(e.sign.text_height, 0.05)
                            e.sign.mount_height = 1.6 if e.sign.mount_height < 2.0 else e.sign.mount_height
                    msg += "; every sign gets a zone pictogram and one template (50 mm letters at 63\")"
                    global_done.add("palette")
            elif f.rule_id == "quiet-retreat":
                if "quiet" not in global_done:
                    msg = add_quiet_room(space)
                    if msg:
                        global_done.add("quiet")
            else:
                msg = apply_fix(space, f)
            if msg:
                applied += 1
                changes.append(Change(agent=f.agent, rule_id=f.rule_id, finding=f.title, change=msg))
        reports.append(audit(space))
        if applied == 0 or reports[-1].overall <= before.overall + 0.05:
            break
    return space, changes, reports
