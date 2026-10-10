"""Inlines a SpaceSpec (and optionally a tour timeline) into viewer/twin.html so it opens straight from disk.

    uv run python scripts/build_viewer.py [spec.json] [out.html] [tour.json]
"""
import sys
from pathlib import Path

args = sys.argv[1:] + [None] * 4
spec = args[0] or "specs/design_a.json"
out = args[1] or "out/03_design/twin.html"
tour = args[2]


def inline(text: str) -> str:
    return text.replace("</", "<\\/")


html = Path("viewer/twin.html").read_text()
html = html.replace("/*DIRECTOR*/", Path("viewer/director.js").read_text())
html = html.replace("/*SPEC*/", inline(Path(spec).read_text()))
html = html.replace("/*TOUR*/", inline(Path(tour).read_text()) if tour else "null")
spec_b = args[3] if len(args) > 3 else None
if spec_b is None and Path(spec).name == "design_a.json" and Path("specs/design_b.json").exists():
    spec_b = "specs/design_b.json"  # the agents / fix modes need Design B too
html = html.replace("/*SPECB*/", inline(Path(spec_b).read_text()) if spec_b else "null")


def audit_payload(spec_path: str, spec_b_path: str | None) -> dict:
    """Findings, agent walking routes and the change log for the viewer's #agents and #fix modes."""
    import json
    import math
    import make_tour as mt
    from accesstwin.agents.base import AuditContext
    from accesstwin.audit import audit, personas
    from accesstwin.geometry import RoutePlanner
    from accesstwin.spec import Space

    A = Space.load(spec_path)
    ra = audit(A)
    ctx = AuditContext(A)
    entrance = mt.stand_point(ctx, ctx.entrance.inside_point(0.8))
    agents = []
    for p in personas():
        mine = [f for f in ra.findings if f.agent == p.id]
        stops = mt.pick_stops(mine, 6)
        here, todo, legs = entrance, stops[:], []
        while todo:
            f = min(todo, key=lambda f: math.dist(here, f.location))
            todo.remove(f)
            target = mt.stand_point(ctx, f.location)
            r = RoutePlanner(ctx.free, tuple(here)).route(tuple(target), 0.3, tolerance=0.4)
            path = mt.smooth(r.path) if r.path else [here, target]
            if math.dist(path[0], here) > 0.05:
                path.insert(0, list(here))
            legs.append({"path": path, "title": f.title, "severity": f.severity, "detail": f.detail,
                         "citation": f"{f.citation.source.split(' (')[0]} §{f.citation.section}".rstrip(" §"),
                         "fix": f.fix.summary if f.fix else "", "element_id": f.element_id, "location": list(f.location)})
            here = path[-1]
        agents.append({"id": p.id, "name": p.name, "color": mt.AGENT_STYLE[p.id]["color"],
                       "criteria": [t for t, _ in p.criteria], "failed": sum(not f.passed for f in mine),
                       "checks": len(mine), "legs": legs})
    pins = [{"agent": f.agent, "title": f.title, "severity": f.severity, "element_id": f.element_id,
             "location": list(f.location)} for f in ra.failures() if f.location]
    out = {"agents": agents, "pins": pins, "score_a": ra.overall}
    if spec_b_path:
        rb = audit(Space.load(spec_b_path))
        out["score_b"] = rb.overall
        out["b_failed"] = [[f.agent, f.title] for f in rb.failures()]
        log = Path("out/03_design/changes_b.json")
        out["changes"] = json.loads(log.read_text())["changes"] if log.exists() else []
    return out


if "/*AUDIT*/" in html:
    import json
    payload = audit_payload(spec, spec_b) if Path(spec).name == "design_a.json" else None
    html = html.replace("/*AUDIT*/", inline(json.dumps(payload)) if payload else "null")
Path(out).parent.mkdir(parents=True, exist_ok=True)
Path(out).write_text(html)
print(f"wrote {out}")
