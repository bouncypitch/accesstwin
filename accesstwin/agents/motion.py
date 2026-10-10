"""Motion clearance: anyone walking or rolling past moving robots. Arm sweep, crush gaps, fence distance, e-stops."""

from __future__ import annotations

import math

from shapely.geometry import Point, Polygon

from ..findings import IN, Citation, Finding, Fix
from ..spec import Space
from .base import AuditContext, Body, Persona

ID = "motion"

ISO13854 = Citation(source="ISO 13854:2017 Minimum gaps to avoid crushing", section="Table 1 (body: 500 mm)",
                    url="https://www.iso.org/standard/66459.html", basis="standard")
ISO13857 = Citation(source="ISO 13857:2019 Safety distances (upper and lower limbs)", section="Table 4 (20 mm mesh: 120 mm)",
                    url="https://www.axelent.co.uk/media/isiiuoe4/white_paper_aw_168_safety_distance_gb.pdf", basis="standard")
ISO10218 = Citation(source="ISO 10218-2:2025 Robot applications and cells", section="safeguarded space",
                    url="https://www.iso.org/standard/73934.html", basis="standard")

REACH = {"cobot_small": 0.85, "cobot_large": 1.3, "industrial_cage": 1.4}  # knowledge/robotics_lab.json robot_types
CRUSH_GAP = 0.5
MESH_DISTANCE = 0.12


class MotionClearance(Persona):
    id = ID
    name = "Motion clearance"
    summary = "Anyone passing robot cells: the arm's full sweep must stay inside its marked or fenced zone."
    body = Body(path_width=36 * IN, eye_height=1.6)
    criteria = [
        ("Each arm's full reach stays inside its taped zone", "ISO 10218-2:2025"),
        ("Fenced cells: 120 mm between the arm's reach and a 20 mm mesh fence", "ISO 13857"),
        ("500 mm crush gap between the arm's reach and walls or furniture", "ISO 13854"),
        ("E-stops can be pressed from outside the arm's reach", "ISO 10218-2:2025"),
    ]

    def audit(self, space: Space, ctx: AuditContext) -> list[Finding]:
        out = []
        room = space.floor()
        for e in space.elements:
            reach = REACH.get(e.model or "")
            if reach is None:
                continue
            if e.reach_limit:
                reach = min(reach, e.reach_limit)
            sweep = Point(e.center).buffer(reach, 64)
            zone = e.obstacle()
            fenced = e.model == "industrial_cage"
            # 1. Sweep stays inside the marked / fenced zone, with mesh distance for fences.
            spare = min(zone.exterior.distance(Point(p)) for p in sweep.exterior.coords) if zone.contains(sweep) else \
                -sweep.difference(zone).area ** 0.5
            need = MESH_DISTANCE if fenced else 0.0
            ok = spare >= need - 1e-6
            out_pt = max(sweep.exterior.coords, key=lambda p: zone.exterior.distance(Point(p)) * (0 if zone.contains(Point(p)) else 1))
            out.append(Finding(
                agent=ID, rule_id="sweep-in-zone", title=f"{e.label}: arm sweep vs {'fence' if fenced else 'floor marking'}",
                passed=ok, severity="blocking" if not ok else "major", element_id=e.id,
                location=out_pt if not ok else e.center, measured=round(spare, 3),
                required=f">= {need * 1000:.0f} mm inside the {'fence (20 mm mesh)' if fenced else 'marked zone'}",
                citation=ISO13857 if fenced else ISO10218,
                detail=(f"Reach {reach:.2f} m from the base; {'fence' if fenced else 'tape line'} is "
                        f"{'only ' if not ok else ''}{spare * 1000:.0f} mm beyond the arm's reach." if spare >= 0 else
                        f"The {reach:.2f} m reach sweeps past the {'fence' if fenced else 'tape line'} into the walkway."),
                fix=None if ok else Fix(
                    summary=(f"Move the {'fence' if fenced else 'floor marking'} out to {reach + need + 0.05:.2f} m from the base, "
                             "or limit the arm's joint range in the safety controller."),
                    op="set", element_id=e.id, params={"safeguard_margin": round(reach + need + 0.05 - max(e.size) / 2, 2)}),
            ))
            # 2. Crush gap: 500 mm between the sweep and walls / furniture (a body caught against them).
            others = [o.footprint() for o in space.elements if o.id != e.id and o.model != "arena"]
            walls = Polygon(room.exterior).buffer(5).difference(room)
            gaps = [(sweep.distance(o), "furniture") for o in others] + [(sweep.distance(walls), "wall")]
            inter = [n for n, o in zip([o.id for o in space.elements if o.id != e.id and o.model != "arena"], others) if sweep.intersects(o)]
            if sweep.intersects(walls):
                inter.append("wall")
            gap, what = min(gaps)
            ok = gap >= CRUSH_GAP - 1e-6 and not inter
            out.append(Finding(
                agent=ID, rule_id="crush-gap", title=f"{e.label}: gap between arm and {what}", passed=ok,
                severity="blocking" if inter else ("major" if not ok else "major"), element_id=e.id, location=e.center,
                measured=round(-1 if inter else gap, 3), required=f">= {CRUSH_GAP * 1000:.0f} mm", citation=ISO13854,
                detail=(f"The arm reaches into {', '.join(inter)}." if inter else
                        f"{gap * 1000:.0f} mm between the arm's reach and the nearest {what}."),
                fix=None if ok else Fix(summary=f"Move {e.label} so its reach stays 0.5 m clear of {what}s.", op="move", element_id=e.id),
            ))
            # 3. E-stops can be pressed from outside the sweep.
            for p in e.parts:
                if p.kind != "e_stop":
                    continue
                d = math.dist(p.position, e.center)
                ok = d >= reach + 0.1
                out.append(Finding(
                    agent=ID, rule_id="estop-outside-sweep", title=f"E-stop {p.id} outside the arm's reach", passed=ok,
                    severity="blocking", element_id=e.id, location=p.position, measured=round(d - reach, 3),
                    required=">= 100 mm outside the reach", citation=ISO10218,
                    detail=f"{p.id} is {d:.2f} m from the base; the arm reaches {reach:.2f} m.",
                    fix=None if ok else Fix(summary=f"Move {p.id} to the zone boundary, {reach + 0.15:.2f} m from the base."),
                ))
        return out
