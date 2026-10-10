"""Wheelchair user: circulation width, turning space, doors, reach ranges, work surfaces."""

from __future__ import annotations

import math

from shapely.geometry import Point

from ..findings import IN, Citation, Finding, Fix, ada, fmt, inches
from ..spec import Element, OperablePart, Space
from .base import AuditContext, Body, Persona, approach_point

ID = "wheelchair"

CLEAR_PATH = 36 * IN  # 403.5.1
TURN = 60 * IN  # 304.3.1
DOOR_CLEAR = 32 * IN  # 404.2.3
DOOR_FORCE_LBF = 5.0  # 404.2.9 interior hinged doors
REACH_MIN = 15 * IN  # 308.2.1 / 308.3.1
REACH_MAX = 48 * IN
SURFACE_MIN, SURFACE_MAX = 28 * IN, 34 * IN  # 902.3
KNEE_H, KNEE_W, KNEE_D = 27 * IN, 30 * IN, 17 * IN  # 306.3, 305.3 / 306.2 combined toe+knee depth


def side_points(e: Element) -> list[tuple[float, float]]:
    """Midpoints of an element's four faces."""
    xs, ys = e.footprint().exterior.coords.xy
    corners = list(zip(xs, ys))[:4]
    return [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(corners, corners[1:] + corners[:1])]


def max_reach(part: OperablePart) -> tuple[float | None, str]:
    """Highest allowed operable-part height for a seated reach, and the section that sets it."""
    d = part.obstruction_depth
    if part.approach == "forward":
        if d <= 0:
            return REACH_MAX, "308.2.1"
        if d <= 20 * IN:
            return REACH_MAX, "308.2.2"
        if d <= 25 * IN:
            return 44 * IN, "308.2.2"
        return None, "308.2.2"
    if d <= 10 * IN:
        return REACH_MAX, "308.3.1" if d <= 0 else "308.3.2"
    if d <= 24 * IN:
        return 46 * IN, "308.3.2"
    return None, "308.3.2"


class Wheelchair(Persona):
    id = ID
    name = "Wheelchair user"
    summary = "Manual or power wheelchair; seated eye height ~1.2 m; needs 36\" routes and 60\" turning space."
    body = Body(path_width=CLEAR_PATH, turn_diameter=TURN, eye_height=1.2)

    def audit(self, space: Space, ctx: AuditContext) -> list[Finding]:
        out: list[Finding] = []
        out += self.doors(space)
        if ctx.planner is None:
            return out
        out += self.routes(space, ctx)
        out += self.reach(space)
        out += self.work_surfaces(space, ctx)
        return out

    # 404: doors -----------------------------------------------------------------------------------
    def doors(self, space: Space) -> list[Finding]:
        out = []
        for d in space.doors:
            ok = d.clear_width >= DOOR_CLEAR - 1e-6
            out.append(Finding(
                agent=ID, rule_id="door-clear-width", title=f"Door {d.id} clear width", passed=ok,
                severity="blocking", element_id=d.id, location=d.position, measured=d.clear_width,
                required=f'>= {fmt(DOOR_CLEAR)}', citation=ada("404.2.3"),
                detail=f"Clear opening is {fmt(d.clear_width)}.",
                fix=None if ok else Fix(summary=f"Widen door {d.id} to at least 32\" clear (a 36\" leaf gives ~34\").",
                                        op="set", element_id=d.id, params={"clear_width": round(34 * IN, 3)}),
            ))
            if d.hardware != "automatic":
                ok = d.opening_force_lbf <= DOOR_FORCE_LBF
                out.append(Finding(
                    agent=ID, rule_id="door-opening-force", title=f"Door {d.id} opening force", passed=ok,
                    severity="major", element_id=d.id, location=d.position, measured=d.opening_force_lbf,
                    required="<= 5 lbf", citation=ada("404.2.9"),
                    detail=f"Takes {d.opening_force_lbf:.0f} lbf to open.",
                    fix=None if ok else Fix(summary=f"Adjust the closer on {d.id} to 5 lbf or add an automatic opener.",
                                            op="set", element_id=d.id, params={"opening_force_lbf": 5.0}),
                ))
        return out

    # 403 / 304: routes and turning space ---------------------------------------------------------
    def targets(self, space: Space) -> list[tuple[str, str, list[tuple[float, float]], str, str | None]]:
        """(target id, label, candidate approach points, kind, element id) a wheelchair user must reach.

        Tables and seating can be used from any side, so the best side counts; everything else is used
        from its working face."""
        t = []
        for e in space.elements:
            if e.kind in ("table", "seating"):
                pts = [approach_point(e, e.front_point()), *(approach_point(e, p) for p in side_points(e))]
                t.append((e.id, e.label or e.id, pts, "station", e.id))
            elif e.kind in ("workbench", "workstation", "equipment", "storage", "shelf", "cabinet"):
                t.append((e.id, e.label or e.id, [approach_point(e, e.front_point())], "station", e.id))
        for e, p in space.parts():
            if p.kind == "e_stop":
                t.append((p.id, f"E-stop {p.id} on {e.label or e.id}", [approach_point(e, p.position)], "e_stop", e.id))
        for d in space.doors:
            if d.role in ("exit", "both"):
                t.append((d.id, f"Exit {d.id}", [d.inside_point(0.6)], "exit", None))
        return t

    def routes(self, space: Space, ctx: AuditContext) -> list[Finding]:
        out = []
        for tid, label, candidates, kind, el_id in self.targets(space):
            routes = [(ctx.planner.route(c, CLEAR_PATH), c) for c in candidates]
            r, at = max(routes, key=lambda rc: rc[0].bottleneck.width if rc[0].bottleneck else -1)
            bn = r.bottleneck
            severity = "blocking" if kind in ("e_stop", "exit") else "major"
            if bn is None:
                out.append(Finding(
                    agent=ID, rule_id="route-clear-width", title=f"Route to {label}", passed=False,
                    severity=severity, element_id=el_id, location=at, required=f">= {fmt(CLEAR_PATH)}",
                    citation=ada("403.5.1"), detail="No route exists from the entrance.",
                ))
                continue
            fix = None if r.reachable else self.widen_fix(space, bn)
            out.append(Finding(
                agent=ID, rule_id="route-clear-width", title=f"Route to {label}", passed=r.reachable,
                severity=severity, element_id=el_id, location=bn.location, measured=bn.width,
                required=f">= {fmt(CLEAR_PATH)}", citation=ada("403.5.1"),
                detail=(f"Narrowest point is {fmt(bn.width)} between {bn.between[0]} and {bn.between[1]}."
                        if not r.reachable else f"Narrowest point {fmt(bn.width)}; route {r.length:.1f} m."),
                fix=fix, path=r.path,
            ))
            if kind == "station" and r.reachable and el_id and space.element(el_id).accessible_station:
                spot = ctx.planner.has_turning_space(at, TURN, within=1.5)
                out.append(Finding(
                    agent=ID, rule_id="turning-space", title=f"Turning space at {label}", passed=spot is not None,
                    severity="major", element_id=el_id, location=spot or at, required=f'{fmt(TURN)} circle within 1.5 m',
                    citation=ada("304.3"),
                    detail="A wheelchair can turn around near the station." if spot else
                           "No 60\" turning circle near the station; the user would have to reverse out.",
                    fix=None if spot else Fix(summary=f"Clear a 60\" circle beside {label} by moving adjacent furniture."),
                ))
        return out

    def widen_fix(self, space: Space, bn) -> Fix:
        shortfall = CLEAR_PATH - bn.width + 0.03
        movable = [n for n in bn.between if n != "wall" and space.element(n).kind != "robot_cell"]
        if not movable:
            movable = [n for n in bn.between if n != "wall"]
        if not movable:
            return Fix(summary=f"Aisle is {inches(shortfall):.0f}\" too narrow between fixed walls; reroute circulation.")
        name = movable[0]
        el = space.element(name)
        # Push the movable element away from the bottleneck point.
        c = el.obstacle().centroid
        p = Point(bn.location)
        dx, dy = c.x - p.x, c.y - p.y
        # Move along the dominant axis so furniture stays aligned with the room.
        if abs(dx) >= abs(dy):
            dx, dy = math.copysign(shortfall, dx), 0.0
        else:
            dx, dy = 0.0, math.copysign(shortfall, dy)
        return Fix(
            summary=f"Move {el.label or name} {inches(shortfall):.0f}\" ({shortfall:.2f} m) to widen the aisle to 36\".",
            op="move", element_id=name, params={"dx": round(dx, 3), "dy": round(dy, 3)},
        )

    # 308: reach ranges ---------------------------------------------------------------------------
    def reach(self, space: Space) -> list[Finding]:
        out = []
        for el, part in space.parts():
            hi, section = max_reach(part)
            ok = hi is not None and REACH_MIN - 1e-6 <= part.height <= hi + 1e-6
            label = f"{part.kind.replace('_', '-')} {part.id} on {el.label or el.id}"
            req = "not reachable over this obstruction" if hi is None else f"{fmt(REACH_MIN)} to {fmt(hi)}"
            target = min(hi, 42 * IN) if hi else 42 * IN
            out.append(Finding(
                agent=ID, rule_id="reach-range", title=f"Reach to {label}", passed=ok,
                severity="blocking" if part.kind == "e_stop" else "major",
                element_id=el.id, location=part.position, measured=part.height, required=req,
                citation=ada(section),
                detail=f"Mounted at {fmt(part.height)}, {part.approach} approach"
                       + (f" over a {inches(part.obstruction_depth):.0f}\" deep obstruction." if part.obstruction_depth else "."),
                fix=None if ok else Fix(
                    summary=f"Remount {part.id} at {inches(target):.0f}\""
                            + (" and remove the obstruction in front of it." if hi is None else "."),
                    op="set", element_id=el.id,
                    params={"part": part.id, "height": round(target, 3),
                            **({"obstruction_depth": 0.0} if hi is None else {})},
                ),
            ))
        return out

    # 902 / 306: work surfaces --------------------------------------------------------------------
    def work_surfaces(self, space: Space, ctx: AuditContext) -> list[Finding]:
        out = []
        surfaces = [e for e in space.elements if e.work_surface_height is not None]
        stations = [e for e in surfaces if e.accessible_station]
        if surfaces and not stations:
            out.append(Finding(
                agent=ID, rule_id="accessible-station", title="Accessible work station provided", passed=False,
                severity="major", required="at least one wheelchair-usable work surface",
                citation=Citation(source="2010 ADA Standards (226.1, 902) as inclusive practice for work areas",
                                  section="226.1", url="https://www.access-board.gov/ada/#ada-226",
                                  basis="best_practice"),
                detail="No work surface is designated for a seated user.",
                fix=Fix(summary=f"Designate {surfaces[0].label or surfaces[0].id} as an accessible station "
                                "(28-34\" high, knee clearance below).", op="set", element_id=surfaces[0].id,
                        params={"accessible_station": True}),
            ))
        for e in stations:
            h = e.work_surface_height
            ok = SURFACE_MIN - 1e-6 <= h <= SURFACE_MAX + 1e-6
            out.append(Finding(
                agent=ID, rule_id="work-surface-height", title=f"Work surface height at {e.label or e.id}",
                passed=ok, severity="major", element_id=e.id, location=e.center, measured=h,
                required=f"{fmt(SURFACE_MIN)} to {fmt(SURFACE_MAX)}", citation=ada("902.3"),
                detail=f"Surface is {fmt(h)} high.",
                fix=None if ok else Fix(summary=f"Use a height-adjustable bench at {e.label or e.id} (set to 32\").",
                                        op="set", element_id=e.id, params={"work_surface_height": round(32 * IN, 3)}),
            ))
            k = e.knee_clearance
            problems = []
            if k is None:
                problems.append("no knee space (cabinet or drawers below)")
            else:
                if k.height < KNEE_H - 1e-6:
                    problems.append(f"knee height {fmt(k.height)} < 27\"")
                if k.width < KNEE_W - 1e-6:
                    problems.append(f"knee width {fmt(k.width)} < 30\"")
                if k.depth < KNEE_D - 1e-6:
                    problems.append(f"knee depth {fmt(k.depth)} < 17\"")
            out.append(Finding(
                agent=ID, rule_id="knee-clearance", title=f"Knee clearance at {e.label or e.id}", passed=not problems,
                severity="major", element_id=e.id, location=e.center, required='27" high, 30" wide, 17" deep',
                citation=ada("306.3"), detail="; ".join(problems) or "Knee and toe space is clear.",
                fix=None if not problems else Fix(
                    summary=f"Remove the under-bench storage at {e.label or e.id} to open 30\" x 27\" x 19\" knee space.",
                    op="set", element_id=e.id,
                    params={"knee_clearance": {"height": round(27.5 * IN, 3), "width": round(32 * IN, 3),
                                               "depth": round(19 * IN, 3)}}),
            ))
        return out
