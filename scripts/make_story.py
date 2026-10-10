"""The explainer story: problem -> solution -> demo -> scan -> clean -> research -> build -> agents -> findings ->
fixes (A -> B morph) -> metrics. Writes <out>/tour.json + narration audio; reuses photoreal worlds from a prior tour.

    uv run python scripts/make_story.py out/04_tour/story --reuse out/04_tour/explainer

Narration: ElevenLabs if ELEVENLABS_API_KEY is in .env, else macOS "Ava (Premium)".
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from accesstwin.agents.base import AuditContext
from accesstwin.audit import audit, personas
from accesstwin.geometry import RoutePlanner
from accesstwin.spec import Space

import make_tour as mt  # noqa: E402  (scripts/ is on sys.path when run as a script)

COLOR = mt.AGENT_STYLE


def env(key: str) -> str | None:
    for line in Path(".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip() or None
    return os.environ.get(key)


EL_KEY = env("ELEVENLABS_API_KEY")
EL_VOICE = "21m00Tcm4TlvDq8ikWAM"  # "Rachel": warm, clear narration voice


def speak(text: str, dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if EL_KEY:
        mp3 = dest.with_suffix(".mp3")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}?output_format=mp3_44100_128", method="POST",
            data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2",
                             "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25}}).encode(),
            headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"})
        mp3.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), str(dest)], check=True)
    else:
        subprocess.run(["say", "-v", "Ava (Premium)", "-r", "178", "-o", str(dest), text], check=True)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def inches(m: float) -> int:
    return round(m / 0.0254)


def words(n: int) -> str:
    return str(n)


INTRO = {
    "wheelchair": "Our first agent uses a wheelchair. It needs thirty-six-inch aisles, room to turn around, and every "
                  "control, including the emergency stops, within reach from a seat.",
    "low_vision": "Next, an agent with low vision and red-green color blindness. It checks how readable every sign is, "
                  "and whether color alone is doing the work.",
    "neurodivergent": "Our third agent is neurodivergent. Noise and constant motion wear it down, and it relies on a "
                      "layout that's easy to read, so it checks noise at quiet seats, robots moving in view, how many "
                      "turns it takes to find things, and whether there's somewhere quiet to go.",
    "motion": "And our last agent watches the robots. Every arm's full reach has to stay inside its marked zone, "
              "half a meter clear of walls and furniture, with the emergency stop reachable from outside the swing.",
}


def natural(f, space: Space) -> str:
    """A spoken, plain-English line for a finding."""
    d = f.detail
    if f.rule_id == "reach-range":
        return (f"This emergency stop is mounted at {inches(f.measured)} inches. From a wheelchair, you can only reach "
                f"about forty-eight. Moving it down to forty-two fixes it.")
    if f.rule_id == "route-clear-width":
        m = re.search(r"between (\w+) and (\w+)", d)
        names = [space.element(n).label.split(" (")[0].lower() if n != "wall" else "the wall"
                 for n in (m.groups() if m else [])] if m else []
        where = f" between the {names[0]} and the {names[1]}" if len(names) == 2 else ""
        target = f.title.replace("Route to ", "").split(" on ")[0].replace("E-stop", "the emergency stop")
        return (f"To get to {target}, the aisle narrows to just {inches(f.measured)} inches{where}. A wheelchair needs "
                f"thirty-six. Shifting one piece of furniture opens it up.")
    if f.rule_id == "sign-char-height":
        return (f"The letters on this sign are only {round(f.measured * 1000)} millimeters tall. From the aisle, "
                "someone with low vision simply can't read it. They should be at least sixteen.")
    if f.rule_id == "sign-contrast":
        return (f"Pale text on a white sign, a contrast of just {f.measured:.1f} to one. It needs at least four and a half "
                "to one to be readable.")
    if f.rule_id == "color-only-coding":
        return ("Every zone is marked by color alone. For someone who's red-green color blind, the robot zone and the "
                "break area look the same. Adding names and symbols to every sign fixes it.")
    if f.rule_id == "zone-color-cvd":
        return "These two zone colors look identical to someone with red-green color blindness."
    if f.rule_id == "tactile-sign":
        return "The restroom sign has no raised letters or braille, so a blind visitor can't find it by touch."
    if f.rule_id == "quiet-retreat":
        return ("There's nowhere to step away. With no quiet room, the noise and the moving robots never let up.")
    if f.rule_id == "noise-at-quiet-station":
        src = re.search(r"loudest is (.+?) \(", d)
        s = src.group(1).split(" (")[0].lower() if src else "nearby equipment"
        return (f"At this bench it's about {round(f.measured)} decibels whenever the {s} runs. That's too loud for "
                "focused work. An acoustic enclosure brings it down.")
    if f.rule_id == "visual-motion":
        return "A robot arm swings less than two meters from this seat, all day long. A simple screen fixes it."
    if f.rule_id == "wayfinding-turns":
        return f"Getting here from the entrance takes {f.measured:.0f} turns. That's a lot to remember."
    if f.rule_id == "crush-gap":
        return ("This arm's full reach sweeps right into the wall. Anyone caught there could be crushed. The cell has "
                "to move, or the arm's reach has to be capped.")
    if f.rule_id == "sweep-in-zone":
        if "fence" in f.title:
            return ("The fence sits just a hundred millimeters beyond this arm's reach. With this mesh, it needs at "
                    "least a hundred and twenty, or fingers can reach through.")
        return "This arm can swing past its taped zone and into the walkway."
    if f.rule_id == "estop-outside-sweep":
        return "To hit this emergency stop, you'd have to stand inside the arm's swing."
    first = d.split(". ")[0].rstrip(".")
    return f"{f.title}. {first}."


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--reuse", default="out/04_tour/explainer")
    ap.add_argument("--stops", type=int, default=2)
    args = ap.parse_args()
    out = Path(args.out)
    if (out / "audio").exists():
        shutil.rmtree(out / "audio")
    (out / "audio").mkdir(parents=True, exist_ok=True)
    reuse = Path(args.reuse)
    if (reuse / "hero").exists() and not (out / "hero").exists():
        (out / "hero").symlink_to((reuse / "hero").resolve())
    pts = Path("out/05_world/venue/scan_points.bin")
    shutil.copy2(pts, out / "scan_points.bin")
    prior = {}
    if (reuse / "tour.json").exists():
        for s in json.loads((reuse / "tour.json").read_text())["segments"]:
            if s.get("hero"):
                prior[(s["agent"], s["finding"]["title"])] = s

    A, B = Space.load("specs/design_a.json"), Space.load("specs/design_b.json")
    ra, rb = audit(A), audit(B)
    ctx = AuditContext(A)
    know = json.loads(Path("knowledge/robotics_lab.json").read_text())
    log = json.loads(Path("out/03_design/changes_b.json").read_text())["changes"]
    segs: list[dict] = []
    n = 0

    def add(seg: dict, text: str | None = None, min_dur: float = 0.0, pad: float = 0.6) -> None:
        nonlocal n
        if text:
            n += 1
            f = out / "audio" / f"{n:03d}.aiff"
            seg["audio"], seg["narration"] = f"audio/{f.name}", text
            seg["dur"] = round(max(min_dur, speak(text, f) + pad), 2)
        else:
            seg["dur"] = round(max(min_dur, seg.get("dur", 0)), 2)
        segs.append(seg)

    fails_a = sum(s.failed for s in ra.scores)
    block_a = sum(s.blocking_failed for s in ra.scores)

    # 1-3: problem, solution, demo
    add({"type": "card", "kind": "problem", "chapter": "The problem", "kicker": "The problem", "fade": True,
         "title": "Workplaces are built for one kind of body",
         "points": ["Benches, controls and signs that work for most people quietly shut others out.",
                    "Wheelchair users, people with low vision, neurodivergent workers.",
                    "And it's usually found after the space is built, when fixing it is slow and expensive."]},
        "Most workplaces are designed around one standard body. Benches, controls and signs that work for most people "
        "quietly shut others out: wheelchair users, people with low vision, neurodivergent workers. And these problems "
        "usually surface after the space is built, when fixing them is slow and expensive.", 9)
    add({"type": "card", "kind": "solution", "chapter": "Our solution", "kicker": "AccessTwin",
         "title": "Walk it before you build it",
         "points": ["A phone scan becomes a measured digital twin.",
                    "AI agents, each living with a different disability, walk through it.",
                    "Every problem is flagged with the rule it breaks, and fixed in the design."]},
        "AccessTwin lets you test a space before it exists. A phone scan becomes a measured digital twin. Then AI "
        "agents, each living with a different disability, walk through it, flag every problem with the rule it "
        "breaks, and fix the design.", 9)
    add({"type": "card", "kind": "demo", "chapter": "Live example", "kicker": "Live example", "backdrop": "points",
         "title": "This hackathon room, as a robotics lab",
         "points": ["Scanned tonight with an iPhone.", "Redesigned as a full robotics lab.", "Audited by four agents."]},
        "Here's a real example. We took the room this hackathon is in, and asked: what if we turned it into a "
        "robotics lab?", 6)

    # 4-5: scan, clean
    add({"type": "scan", "chapter": "The RGB-D scan", "points": "scan_points.bin", "fade": True,
         "caption": f"{A.floor().area:.0f} m² · 1,092 LiDAR frames fused into 2 million points"},
        "First, we scanned the room with an iPhone. LiDAR and video, fused into two million colored points, accurate "
        "to a few centimeters.", 7)
    add({"type": "clean", "chapter": "Remove people and tables", "points": "scan_points.bin",
         "caption": "Everything off the walls, floor and ceiling is removed geometrically"},
        "Then we strip out everything temporary. People, chairs and tables are removed geometrically, and the carpet "
        "underneath is filled back in, leaving just the walls, doors and floor.", 8)

    # 6: research
    zones = [{"label": z["label"].split(" (")[0], "items": len(z.get("equipment", [])), "reqs": len(z.get("requirements", [])),
              "example": (z.get("equipment") or [{}])[0].get("label", "")[:46]} for z in know["zones"]][:12]
    add({"type": "card", "kind": "research", "chapter": "Research the lab", "backdrop": "points", "after": "clean",
         "title": "What a good robotics lab needs", "zones": zones, "sources": len(know["sources"])},
        "Next, a research agent works out what a good robotics lab needs: robot cells with safety zones, a netted test "
        "arena, electronics and soldering benches, fabrication, battery storage, a maintenance bay, plus a kitchen "
        "and an accessible restroom. Every requirement is traced to a source, from ISO robot safety standards to "
        "university lab guidelines.", 14)

    # 7: build
    add({"type": "build", "chapter": "Add everything", "fade": True,
         "caption": f"Design A · {len(A.elements)} stations in {len(A.zones)} color-coded zones"},
        f"A design agent lays it all into the scanned room. {len(A.elements)} stations, color-coded by zone, with a "
        "sign at every one. This is Design A, a typical first pass.", 9)

    # 8: agents + criteria
    agents = personas()
    for i, p in enumerate(agents):
        sc = next(s for s in ra.scores if s.agent == p.id)
        seg = {"type": "card", "kind": "agent", "agent": p.id, "name": p.name, "summary": p.summary,
               "color": COLOR[p.id]["color"], "criteria": [{"text": t, "cite": c} for t, c in p.criteria],
               "stats": {"checks": sc.checks, "failed": sc.failed, "blocking": sc.blocking_failed}}
        if i == 0:
            seg["chapter"] = "The disability agents"
        add(seg, INTRO[p.id], 8)

    # 9: findings, per agent, reusing photoreal worlds
    entrance = mt.stand_point(ctx, ctx.entrance.inside_point(0.8))
    first = True
    for p in agents:
        mine = [f for f in ra.findings if f.agent == p.id]
        stops = mt.pick_stops(mine, args.stops)
        here = entrance
        style = COLOR[p.id]
        for k, f in enumerate(stops, 1):
            target = mt.stand_point(ctx, f.location)
            r = RoutePlanner(ctx.free, tuple(here)).route(tuple(target), 0.3, tolerance=0.4)
            path = mt.smooth(r.path) if r.path else [here, target]
            if math.dist(path[0], here) > 0.05:
                path.insert(0, here)
            walk = {"type": "walk", "agent": p.id, "avatar": style["avatar"], "color": style["color"], "path": path,
                    "label": f"{p.name}: finding {k} of {len(stops)}", "dur": min(4.5, max(1.5, mt.length(path) / 1.4))}
            if first:
                walk["chapter"], first = "Where the agents find issues", False
            add(walk)
            here = path[-1]
            old = prior.get((p.id, f.title), {})
            stop = {"type": "stop", "agent": p.id, "avatar": style["avatar"], "color": style["color"], "at": here,
                    "index": k, "of": len(stops),
                    "finding": {"title": f.title, "detail": f.detail, "required": f.required, "severity": f.severity,
                                "citation": f"{f.citation.source.split(' (')[0]} §{f.citation.section}".rstrip(" §"),
                                "fix": f.fix.summary if f.fix else "", "element_id": f.element_id,
                                "location": list(f.location), "rule_id": f.rule_id}}
            for key in ("hero", "world", "reach", "noise", "filter", "sign", "sightline"):
                if key in old:
                    stop[key] = old[key]
            if old.get("at"):
                stop["at"] = old["at"]
            add(stop, natural(f, A), 6)

    # 10: fixes -> Design B
    cnt = {}
    for c in log:
        cnt[c["rule_id"]] = cnt.get(c["rule_id"], 0) + 1
    moves = sum(1 for c in log if c["change"].startswith("Moved"))
    bullets = [f"<b>{moves}</b> furniture moves open every aisle to 36\"",
               "E-stop lowered to <b>42\"</b>",
               "<b>Color-blind-safe</b> palette, names and symbols on every sign",
               "<b>Acoustic enclosures</b> and screens at quiet seats",
               "A <b>quiet room</b> added",
               "Industrial arm moved to <b>its own fenced bay</b>",
               "Cobot reach <b>capped</b> by a safety-rated limit"]
    add({"type": "morph", "chapter": "Fix the design", "changes": bullets, "fade": True},
        f"Then a remediation agent fixes the design. It makes {len(log)} changes: it moves furniture to open up the "
        "aisles, lowers the emergency stop, switches to a color-blind-safe palette with names and symbols, encloses "
        "the noisiest machines, adds a quiet room, and moves the industrial arm to its own bay. Every change is "
        "checked, and the agents walk the new design again.", 16)
    add({"type": "card", "kind": "demo", "backdrop": "designB", "kicker": "Design B", "title": "The fixed design",
         "points": [f"{sum(s.failed for s in rb.scores)} minor issues left, none blocking."]},
        "This is Design B.", 4)

    # 11: metrics
    rows = []
    for sa, sb in zip(ra.scores, rb.scores):
        rows.append({"agent": sa.name, "color": COLOR[sa.agent]["color"], "a_failed": sa.failed, "a_blocking": sa.blocking_failed,
                     "a_score": sa.score, "b_failed": sb.failed, "b_blocking": sb.blocking_failed, "b_score": sb.score})
    fails_b = sum(s.failed for s in rb.scores)
    block_b = sum(s.blocking_failed for s in rb.scores)
    add({"type": "card", "kind": "metrics", "chapter": "The results", "backdrop": "designB", "title": "Design A → Design B",
         "tiles": [{"label": "Accessibility score", "a": f"{ra.overall:.0f}%", "b": f"{rb.overall:.0f}%"},
                   {"label": "Problems", "a": str(fails_a), "b": str(fails_b)},
                   {"label": "Blocking", "a": str(block_a), "b": str(block_b)},
                   {"label": "Checks run", "a": str(sum(s.checks for s in ra.scores)), "b": str(sum(s.checks for s in rb.scores))}],
         "rows": rows, "fadeOut": True},
        f"Design A failed {fails_a} checks, {block_a} of them blocking. Design B fails {fails_b}, all minor. The "
        f"accessibility score goes from {ra.overall:.0f} to {rb.overall:.0f} percent, before a single bench is bought. "
        "That's AccessTwin.", 13, 1.5)

    t = 0.0
    for s in segs:
        s["t0"] = round(t, 2)
        t += s["dur"]
    (out / "tour.json").write_text(json.dumps({"duration": round(t, 2), "segments": segs}, indent=1))
    print(f"wrote {out}/tour.json: {len(segs)} segments, {t:.0f} s, voice: {'ElevenLabs' if EL_KEY else 'Ava (Premium)'}")


if __name__ == "__main__":
    main()
