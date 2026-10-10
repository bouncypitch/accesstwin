"""Builds a walkthrough timeline from an audit: agent intro cards, avatar walks, finding stops, summary table.

    uv run python scripts/make_tour.py specs/design_a.json out/04_tour/explainer --stops 3
    uv run python scripts/make_tour.py specs/design_a.json out/04_tour/wheelchair --agents wheelchair --stops 5

Writes <out>/tour.json and narration clips <out>/audio/*.aiff (macOS `say`). The viewer plays tour.json in
director mode and scripts/record.mjs renders it to video.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from shapely.geometry import LineString

from accesstwin.agents.base import AuditContext
from accesstwin.agents.motion import REACH
from accesstwin.agents.neurodivergent import NOISE_DBA_1M
from accesstwin.audit import audit, personas
from accesstwin.findings import Finding, fmt
from accesstwin.geometry import RoutePlanner
from accesstwin.spec import Space

AGENT_STYLE = {
    "wheelchair": {"color": "#3b82f6", "avatar": "wheelchair"},
    "low_vision": {"color": "#a855f7", "avatar": "cane"},
    "neurodivergent": {"color": "#14b8a6", "avatar": "headphones"},
    "motion": {"color": "#f59e0b", "avatar": "hivis"},
}
WALK_SPEED = 1.4  # m/s on screen
MAX_WALK = 5.0  # s: long walks are sped up
VOICE = "Samantha"
SPOKEN = {  # one-line spoken version of each agent's criteria (the full list is on screen)
    "wheelchair": "route widths, turning space, doors, reach to controls and e-stops, and work-surface heights",
    "low_vision": "sign contrast, letter size, colors that merge for color-blind visitors, and tactile room signs",
    "neurodivergent": "noise at quiet seats, robot motion in view, how easy each station is to find, and a quiet room",
    "motion": "whether each robot arm's full reach stays inside its marked or fenced zone, crush gaps, and e-stop placement",
}


def say(text: str, dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["say", "-v", VOICE, "-r", "192", "-o", str(dest), text], check=True)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def smooth(path: list, simplify: float = 0.25, iters: int = 2) -> list:
    if len(path) < 3:
        return [list(p) for p in path]
    pts = list(LineString(path).simplify(simplify).coords)
    for _ in range(iters):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        out.append(pts[-1])
        pts = out
    return [[round(x, 3), round(y, 3)] for x, y in pts]


def length(path) -> float:
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


def pick_stops(findings: list[Finding], n: int) -> list[Finding]:
    """Most severe first, one per rule before repeating a rule, no two stops within 1.5 m."""
    order = {"blocking": 0, "major": 1, "minor": 2}
    fails = sorted((f for f in findings if not f.passed and f.location), key=lambda f: (order[f.severity], f.rule_id))
    picked: list[Finding] = []
    for pass_ in (0, 1):
        for f in fails:
            if len(picked) >= n:
                break
            if f in picked or (pass_ == 0 and any(p.rule_id == f.rule_id for p in picked)):
                continue
            if any(math.dist(p.location, f.location) < 1.5 for p in picked):
                continue
            picked.append(f)
    return picked


def stand_point(ctx: AuditContext, at) -> list[float]:
    p = ctx.free.to_point(ctx.free.nearest_free(at))
    return [round(p[0], 3), round(p[1], 3)]


def short(text: str) -> str:
    """Speakable text: drop metric asides, say inches, strip quotes."""
    text = re.sub(r"\s*\([\d.]+ m\)", "", text)
    text = re.sub(r'"([^"]*[A-Za-z][^"]*)"', r"\1", text)  # quoted sign names
    text = re.sub(r'(\d)(\.0)?"', r"\1 inches", text)
    text = re.sub(r"(\d)\.0\b", r"\1", text)
    return text.replace('"', "").replace(" (", ", ").replace("(", "").replace(")", "").replace(" x ", " by ")


def spoken_measure(f: Finding) -> str:
    if f.measured is None:
        return ""
    if f.rule_id in ("route-clear-width", "reach-range"):
        return f"Measured {f.measured / 0.0254:.0f} inches. "
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--agents", default="wheelchair,low_vision,neurodivergent,motion")
    ap.add_argument("--stops", type=int, default=3)
    ap.add_argument("--no-intro", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    space = Space.load(args.spec)
    report = audit(space)
    ctx = AuditContext(space)
    agents = [p for p in personas() if p.id in args.agents.split(",")]
    entrance = stand_point(ctx, ctx.entrance.inside_point(0.8))
    segs: list[dict] = []
    clip = 0

    def add(seg: dict, narration: str | None = None, min_dur: float = 0.0, pad: float = 0.7) -> None:
        nonlocal clip
        if narration:
            clip += 1
            f = out / "audio" / f"{clip:03d}.aiff"
            seg["audio"] = f"audio/{f.name}"
            seg["dur"] = round(max(min_dur, say(narration, f) + pad), 2)
            seg["narration"] = narration
        else:
            seg["dur"] = round(max(min_dur, seg.get("dur", 0)), 2)
        segs.append(seg)

    if not args.no_intro:
        add({"type": "card", "kind": "title", "title": "AccessTwin",
             "subtitle": "Walk a workplace before it is built, as the people it might shut out."},
            "AccessTwin. We scanned this hackathon room with an iPhone, redesigned it as a robotics lab, "
            "and sent AI agents through the digital twin, each one living with a different disability.", 6)
        add({"type": "orbit", "caption": f"{space.name}: {len(space.elements)} stations in the scanned {space.floor().area:.0f} square-meter room"},
            "Every wall, door and station is metrically accurate, from the LiDAR scan.", 6)

    by_agent = {}
    for p in agents:
        style = AGENT_STYLE[p.id]
        mine = [f for f in report.findings if f.agent == p.id]
        sc = next(s for s in report.scores if s.agent == p.id)
        by_agent[p.id] = sc
        crit = [{"text": t, "cite": c} for t, c in p.criteria]
        add({"type": "card", "kind": "agent", "agent": p.id, "name": p.name, "summary": p.summary, "color": style["color"],
             "criteria": crit, "stats": {"checks": sc.checks, "failed": sc.failed, "blocking": sc.blocking_failed}},
            f"Agent: {p.name}. It checks {SPOKEN[p.id]}.", 9, 1.0)
        here = entrance
        stops = pick_stops(mine, args.stops)
        # Visit stops in nearest-neighbor order from the entrance.
        todo, ordered = stops[:], []
        while todo:
            nxt = min(todo, key=lambda f: math.dist(here, f.location))
            ordered.append(nxt)
            todo.remove(nxt)
            here = list(nxt.location)
        here = entrance
        for i, f in enumerate(ordered, 1):
            target = stand_point(ctx, f.location)
            r = RoutePlanner(ctx.free, tuple(here)).route(tuple(target), 0.3, tolerance=0.4)
            path = smooth(r.path) if r.path else [here, target]
            if math.dist(path[0], here) > 0.05:
                path.insert(0, here)
            L = length(path)
            if L > 0.3:
                add({"type": "walk", "agent": p.id, "avatar": style["avatar"], "color": style["color"], "path": path,
                     "label": f"{p.name}: heading to finding {i} of {len(ordered)}", "dur": min(MAX_WALK, max(1.2, L / WALK_SPEED))})
            here = path[-1]
            extra = {}
            el = space.element(f.element_id) if f.element_id and any(e.id == f.element_id for e in space.elements) else None
            if f.agent == "motion" and el is not None and el.model in REACH:
                extra["reach"] = {"center": list(el.center), "r": REACH[el.model], "zone": el.obstacle().exterior.coords[:]}
            if f.rule_id == "noise-at-quiet-station":
                src = max((e for e in space.elements if e.model in NOISE_DBA_1M),
                          key=lambda e: NOISE_DBA_1M[e.model] - 20 * math.log10(max(1, math.dist(e.center, f.location))))
                extra["noise"] = {"source": list(src.center), "source_id": src.id, "dba": f.measured}
            if f.rule_id == "zone-color-cvd":
                extra["filter"] = "deuteranopia"
            if f.rule_id in ("sign-contrast", "sign-char-height", "tactile-sign") and el and el.sign:
                extra["sign"] = {"height": el.sign.mount_height}
            if f.rule_id == "visual-motion":
                extra["sightline"] = True
            first = f.detail.split(". ")[0].rstrip(".")
            fix = f.fix.summary.split(", or ")[0].split("; ")[0].rstrip(".") if f.fix else ""
            narr = (f"{'Blocking. ' if f.severity == 'blocking' else ''}{short(f.title)}. {short(first)}. "
                    + (f"Fix: {short(fix)}." if fix else ""))
            add({"type": "stop", "agent": p.id, "avatar": style["avatar"], "color": style["color"], "at": here,
                 "index": i, "of": len(ordered),
                 "finding": {"title": f.title, "detail": f.detail, "required": f.required, "severity": f.severity,
                             "citation": f"{f.citation.source.split(' (')[0]} §{f.citation.section}".rstrip(" §"),
                             "fix": f.fix.summary if f.fix else "", "element_id": f.element_id, "location": list(f.location),
                             "rule_id": f.rule_id}, **extra}, narr, 7)

    rows = []
    for p in agents:
        mine = [f for f in report.findings if f.agent == p.id and not f.passed]
        top = [f.title for f in pick_stops(mine, 3)]
        s = by_agent[p.id]
        rows.append({"agent": p.name, "color": AGENT_STYLE[p.id]["color"], "checks": s.checks, "failed": s.failed,
                     "blocking": s.blocking_failed, "major": sum(f.severity == "major" for f in mine),
                     "minor": sum(f.severity == "minor" for f in mine), "score": s.score, "top": top})
    total_fail = sum(r["failed"] for r in rows)
    total_block = sum(r["blocking"] for r in rows)
    add({"type": "card", "kind": "summary", "title": f"What the agents found in {space.name.split(':')[0]}", "rows": rows,
         "overall": report.overall},
        f"In total the agents ran {sum(r['checks'] for r in rows)} checks and found {total_fail} problems, "
        f"{total_block} of them blocking. Overall accessibility score: {report.overall:.0f} percent. "
        "Every finding comes with a cited rule and a concrete fix, before a single bench is bought.", 9, 1.5)
    if not args.no_intro:
        add({"type": "card", "kind": "end", "title": "Next: Design B",
             "subtitle": "The agents' fixes, applied automatically, then re-audited."},
            "Next, the fixes are applied automatically and the agents walk the new design.", 4)

    t = 0.0
    for s in segs:
        s["t0"] = round(t, 2)
        t += s["dur"]
    (out / "tour.json").write_text(json.dumps({"duration": round(t, 2), "segments": segs}, indent=1))
    print(f"wrote {out}/tour.json: {len(segs)} segments, {t:.0f} s")


if __name__ == "__main__":
    main()
