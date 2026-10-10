"""Builds the demo website (demo/site/index.html + media/) from the project's real outputs.

    uv run python scripts/build_site.py && open demo/site/index.html

Everything numeric on the page (scores, findings, changes, research program) is read from the audit and spec files,
so the site always matches the current Design A / Design B.
"""
import json
import shutil
import subprocess
from html import escape
from pathlib import Path

from accesstwin.audit import audit, personas
from accesstwin.spec import Space

SITE = Path("demo/site")
MEDIA = SITE / "media"
MEDIA.mkdir(parents=True, exist_ok=True)


def copy(src: str, name: str | None = None) -> str | None:
    p = Path(src)
    if not p.exists():
        return None
    dest = MEDIA / (name or p.name)
    if not dest.exists() or dest.stat().st_mtime < p.stat().st_mtime:
        shutil.copy2(p, dest)
    return f"media/{dest.name}"


def video(src: str, name: str) -> str | None:
    """Web copy of a video: 1080p H.264, smaller file."""
    p = Path(src)
    if not p.exists():
        return None
    dest = MEDIA / name
    if not dest.exists() or dest.stat().st_mtime < p.stat().st_mtime:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-c:v", "libx264", "-crf", "27", "-preset", "fast",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dest)], check=True)
    return f"media/{dest.name}"


A, B = Space.load("specs/design_a.json"), Space.load("specs/design_b.json")
ra, rb = audit(A), audit(B)
changes = json.loads(Path("out/03_design/changes_b.json").read_text())["changes"]
know = json.loads(Path("knowledge/robotics_lab.json").read_text())
tour = json.loads(Path("out/04_tour/explainer/tour.json").read_text())
AG_COLOR = {"wheelchair": "#3b82f6", "low_vision": "#a855f7", "neurodivergent": "#14b8a6", "motion": "#f59e0b",
            "program": "#8b949e"}

img = {
    "asis": copy("out/01_capture/as_is.png", "scan_as_is.png"),
    "shell": copy("out/01_capture/shell.png", "scan_shell.png"),
    "rgbd": copy("demo/assets/02_rgbd_venue/overlay.png", "rgbd_overlay.png"),
    "pano": copy("out/05_world/venue/pano_empty.jpg", "venue_empty_pano.jpg"),
    "planA": copy("out/03_design/design_a_findings.png", "plan_a_findings.png"),
    "planB": copy("out/03_design/design_b_findings.png", "plan_b_findings.png"),
    "a3d": copy("out/03_design/ab_a_Overview.png", "twin_a_overview.png"),
    "b3d": copy("out/03_design/ab_b_Overview.png", "twin_b_overview.png"),
    "aRobots": copy("out/03_design/ab_a_Robotcells.png", "twin_a_robots.png"),
    "bRobots": copy("out/03_design/ab_b_Robotcells.png", "twin_b_robots.png"),
    "explainer": video("out/04_tour/explainer/video.mp4", "explainer.mp4"),
    "explainer_photo": video("out/04_tour/explainer/video_photoreal.mp4", "explainer_photoreal.mp4"),
}
for k in ("Electronics", "Testarena", "Fabrication", "Kitchenrestroom"):
    img[k] = copy(f"out/03_design/twin_{k}.png", f"twin_a_{k.lower()}.png")
twins = {"a": copy("out/03_design/twin.html", "twin_design_a.html"), "b": copy("out/03_design/twin_b.html", "twin_design_b.html")}
pairs = []
for s in tour["segments"]:
    if s.get("hero"):
        i = s["hero"]["index"]
        r = copy(f"out/04_tour/explainer/hero/stop_{i:02d}_color.png", f"hero_{i:02d}_twin.png")
        p = copy(f"out/04_tour/explainer/hero/stop_{i:02d}_photo.jpg", f"hero_{i:02d}_photo.jpg")
        if r and p:
            pairs.append((s, r, p))
worlds = []
for d, label in (("out/05_world/venue", "The real venue, emptied (people and furniture removed from the LiDAR scan)"),
                 ("out/05_world/a", "Design A, from twin renders")):
    w = Path(d) / "world.json"
    if w.exists():
        worlds.append((label, json.loads(w.read_text()).get("world_marble_url"), copy(f"{d}/marble_thumb.jpg", f"{Path(d).name}_thumb.jpg")))
for s, _, _ in pairs:
    if s.get("world"):
        worlds.append((f"Finding: {s['finding']['title']}", s["world"].get("marble_url"), None))


def score_rows() -> str:
    out = []
    for sa, sb in zip(ra.scores, rb.scores):
        col = AG_COLOR.get(sa.agent, "#888")
        out.append(f"""<tr><td><span class="dot" style="background:{col}"></span>{escape(sa.name)}</td>
          <td class="n">{sa.checks}</td><td class="n bad">{sa.failed}</td><td class="n">{sa.blocking_failed}</td>
          <td><div class="bar"><i style="width:{sa.score}%;background:{col};opacity:.55"></i></div><b>{sa.score:.0f}%</b></td>
          <td class="n good">{sb.failed}</td><td class="n">{sb.blocking_failed}</td>
          <td><div class="bar"><i style="width:{sb.score}%;background:{col}"></i></div><b>{sb.score:.0f}%</b></td></tr>""")
    return "\n".join(out)


def agent_cards() -> str:
    out = []
    for p in personas():
        col = AG_COLOR[p.id]
        fa = [f for f in ra.findings if f.agent == p.id and not f.passed]
        crit = "".join(f"<li><span>{escape(t)}</span><em>{escape(c)}</em></li>" for t, c in p.criteria)
        out.append(f"""<article class="agent" style="--c:{col}"><header><span class="dot"></span><h3>{escape(p.name)}</h3></header>
          <p class="muted">{escape(p.summary)}</p><ol class="crit">{crit}</ol>
          <p class="found"><b>{len(fa)}</b> problems found in Design A · <b>{sum(f.severity == 'blocking' for f in fa)}</b> blocking</p></article>""")
    return "\n".join(out)


def findings_table() -> str:
    order = {"blocking": 0, "major": 1, "minor": 2}
    rows = []
    for f in sorted(ra.failures(), key=lambda f: (order[f.severity], f.agent))[:40]:
        rows.append(f"""<tr><td><span class="sev {f.severity}">{f.severity}</span></td><td><span class="dot" style="background:{AG_COLOR[f.agent]}"></span>{escape(f.agent.replace('_', ' '))}</td>
          <td>{escape(f.title)}<div class="muted small">{escape(f.detail)}</div></td><td class="small">{escape(f.citation.source.split(' (')[0])} §{escape(f.citation.section)}</td>
          <td class="small fix">{escape(f.fix.summary if f.fix else '')}</td></tr>""")
    return "\n".join(rows)


def change_rows() -> str:
    return "\n".join(f"""<tr><td><span class="dot" style="background:{AG_COLOR.get(c['agent'], '#888')}"></span>{escape(c['agent'].replace('_', ' '))}</td>
        <td class="small">{escape(c['finding'])}</td><td class="small">{escape(c['change'])}</td></tr>""" for c in changes)


def program_rows() -> str:
    return "\n".join(f"""<tr><td><b>{escape(z['label'])}</b></td><td class="n">{z['area_m2']}</td><td><span class="pri {z['priority']}">{z['priority']}</span></td>
        <td class="small">{len(z.get('equipment', []))} items</td><td class="small">{len(z.get('requirements', []))} cited requirements</td></tr>""" for z in know["zones"])


FLOW = """<svg viewBox="0 0 1200 330" class="flow" role="img" aria-label="AccessTwin pipeline">
<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker></defs>
<g font-size="14" font-family="inherit">
""" + "".join(
    f'<g transform="translate({x},{y})"><rect width="{w}" height="64" rx="12" fill="var(--card)" stroke="{c}" stroke-width="2"/>'
    f'<text x="{w/2}" y="27" text-anchor="middle" fill="var(--text)" font-weight="700">{t}</text>'
    f'<text x="{w/2}" y="47" text-anchor="middle" fill="var(--muted)" font-size="12">{s}</text></g>'
    for x, y, w, c, t, s in [
        (10, 20, 170, "#58a6ff", "iPhone LiDAR scan", "RoomPlan + RGB-D walk"),
        (215, 20, 170, "#58a6ff", "Metric twin", "SpaceSpec, cm-accurate"),
        (420, 20, 170, "#d29922", "Research agent", "lab program + citations"),
        (625, 20, 170, "#d29922", "Design agent", "Design A layout"),
        (830, 20, 170, "#f85149", "4 persona agents", "walk + audit, cited"),
        (1015, 20, 175, "#a371f7", "Walkthrough videos", "twin + World Labs"),
        (830, 150, 170, "#3fb950", "Remediation agent", "validated fixes"),
        (625, 150, 170, "#3fb950", "Design B", "re-audited"),
        (420, 150, 170, "#3fb950", "A/B report", "scores, changes, cost"),
        (215, 150, 170, "#a371f7", "Photoreal worlds", "ControlNet → Marble"),
        (10, 150, 170, "#8b949e", "Designer review", "human in the loop"),
    ]) + """
<g stroke="var(--muted)" stroke-width="2" fill="none" marker-end="url(#ar)">
<path d="M180 52H213"/><path d="M385 52H418"/><path d="M590 52H623"/><path d="M795 52H828"/><path d="M1000 52H1013"/>
<path d="M915 84V148"/><path d="M830 182H797"/><path d="M625 182H592"/><path d="M420 182H387"/><path d="M215 182H182"/>
<path d="M95 214V280H915V216" stroke-dasharray="5 5"/></g>
<text x="505" y="300" text-anchor="middle" fill="var(--muted)" font-size="12">designer accepts, edits or rejects each change; agents re-audit</text>
</g></svg>"""

pairs_html = "\n".join(f"""<figure class="pair"><div class="ba"><img src="{p}" alt="Photoreal frame"><div class="ba-top"><img src="{r}" alt="Twin render"></div>
  <input type="range" min="0" max="100" value="45" aria-label="Twin vs photoreal" oninput="this.parentNode.style.setProperty('--p', this.value + '%')"></div>
  <figcaption><span class="sev {s['finding']['severity']}">{s['finding']['severity']}</span> {escape(s['finding']['title'])}</figcaption></figure>""" for s, r, p in pairs)
worlds_html = "\n".join(f"""<a class="world" href="{escape(u or '#')}" target="_blank" rel="noopener">{f'<img src="{t}" alt="">' if t else '<div class="ph">3D world</div>'}<span>{escape(l)}</span></a>""" for l, u, t in worlds if u)
vid = img["explainer_photo"] or img["explainer"]

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AccessTwin Demo</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;650;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0b0e13;--panel:#11161d;--card:#161b22;--line:#262c36;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--good:#3fb950;--bad:#f85149;--warn:#d29922}}
@media (prefers-color-scheme: light){{:root:not([data-theme="dark"]){{--bg:#f6f8fa;--panel:#ffffff;--card:#ffffff;--line:#d0d7de;--text:#1f2328;--muted:#57606a;--accent:#0969da;--good:#1a7f37;--bad:#cf222e;--warn:#9a6700}}}}
:root[data-theme="light"]{{--bg:#f6f8fa;--panel:#ffffff;--card:#ffffff;--line:#d0d7de;--text:#1f2328;--muted:#57606a;--accent:#0969da;--good:#1a7f37;--bad:#cf222e;--warn:#9a6700}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 Inter,-apple-system,Helvetica,Arial,sans-serif}}
a{{color:var(--accent)}} img,video{{max-width:100%;display:block;border-radius:12px}}
nav{{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}}
nav .in{{max-width:1200px;margin:auto;padding:10px 16px;display:flex;gap:18px;overflow-x:auto;white-space:nowrap;font-size:14px}}
nav a{{color:var(--muted);text-decoration:none}} nav a:hover{{color:var(--text)}} nav b{{color:var(--text)}}
section{{max-width:1200px;margin:auto;padding:56px 16px;border-bottom:1px solid var(--line)}}
h1{{font-size:clamp(40px,7vw,76px);line-height:1;margin:0 0 14px;letter-spacing:-.03em}} h2{{font-size:clamp(26px,3.6vw,38px);margin:0 0 8px;letter-spacing:-.02em}}
h3{{margin:0;font-size:18px}} .kicker{{color:var(--accent);font-weight:650;text-transform:uppercase;letter-spacing:.12em;font-size:13px;margin-bottom:8px}}
.lead{{font-size:clamp(18px,2.2vw,22px);color:var(--muted);max-width:850px}} .muted{{color:var(--muted)}} .small{{font-size:13px}}
.grid{{display:grid;gap:16px}} .g2{{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}} .g3{{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}}
.card,.agent{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:28px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}} .stat b{{display:block;font-size:34px;letter-spacing:-.02em}}
.flow{{width:100%;height:auto;margin-top:20px}}
figure{{margin:0}} figcaption{{color:var(--muted);font-size:14px;margin-top:8px}}
table{{width:100%;border-collapse:collapse;font-size:15px}} th{{text-align:left;color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em;padding:8px;border-bottom:1px solid var(--line)}}
td{{padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}} td.n{{text-align:right;font-variant-numeric:tabular-nums;font-weight:650}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--card)}} .tablewrap table td:first-child,.tablewrap table th:first-child{{padding-left:14px}}
.bad{{color:var(--bad)}} .good{{color:var(--good)}} .fix{{color:var(--good)}}
.dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:8px;vertical-align:middle}}
.bar{{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin-bottom:3px;min-width:90px}} .bar i{{display:block;height:100%}}
.sev{{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;padding:2px 8px;border-radius:5px;color:#fff;white-space:nowrap}}
.sev.blocking{{background:#d1242f}} .sev.major{{background:#bc4c00}} .sev.minor{{background:#9a6700}}
.pri{{font-size:12px;font-weight:700;padding:2px 8px;border-radius:5px;background:var(--line)}} .pri.must{{background:#1f6feb;color:#fff}} .pri.could{{opacity:.7}}
.agent header{{display:flex;align-items:center;gap:8px}} .agent .dot{{background:var(--c);width:14px;height:14px}}
.crit{{padding-left:20px;margin:12px 0}} .crit li{{margin:6px 0}} .crit em{{display:block;color:var(--muted);font-size:12px;font-style:normal}}
.found{{border-top:1px solid var(--line);padding-top:10px;margin:0}} .found b{{color:var(--c)}}
.ba{{position:relative;--p:45%;border-radius:12px;overflow:hidden;aspect-ratio:16/9;background:#000}}
.ba img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:0}} .ba-top{{position:absolute;inset:0;clip-path:inset(0 calc(100% - var(--p)) 0 0)}}
.ba-top::after{{content:"";position:absolute;top:0;bottom:0;left:var(--p);width:2px;background:#fff;box-shadow:0 0 8px #000}}
.ba input{{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}}
.ba-label{{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin-top:6px}}
.world{{display:block;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;text-decoration:none;color:var(--text)}}
.world img,.world .ph{{border-radius:0;aspect-ratio:16/9;object-fit:cover;width:100%}} .world .ph{{display:grid;place-items:center;background:var(--line);color:var(--muted)}} .world span{{display:block;padding:10px 12px;font-size:14px}}
.btn{{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-weight:650;padding:10px 16px;border-radius:10px;margin:6px 8px 0 0}}
.btn.ghost{{background:transparent;color:var(--accent);border:1px solid var(--line)}}
details summary{{cursor:pointer;color:var(--accent);margin:12px 0}}
@media (max-width:600px){{section{{padding:40px 16px}} td,th{{padding:8px 6px}}}}
</style></head><body>
<nav><div class="in"><b>AccessTwin</b><a href="#flow">Flow</a><a href="#scan">Scan</a><a href="#program">Program</a><a href="#design">Design A</a><a href="#agents">Agents</a><a href="#video">Walkthrough</a><a href="#findings">Findings</a><a href="#ab">Before / after</a><a href="#worlds">Worlds</a></div></nav>

<section><div class="kicker">Future of Work Hackathon · Track 1 · Accessible Workplace Twin</div>
<h1>AccessTwin</h1><p class="lead">Walk a workplace before it is built, as the people it might shut out. A 2-minute iPhone scan becomes a metric digital twin;
AI agents living with different disabilities walk it, cite every problem, and fix it before a single bench is bought.</p>
<div class="stats">
<div class="stat"><span class="muted">Room scanned</span><b>{A.floor().area:.0f} m²</b><span class="small muted">iPhone LiDAR, this venue</span></div>
<div class="stat"><span class="muted">Checks run</span><b>{sum(s.checks for s in ra.scores)}</b><span class="small muted">4 agents, cited rules</span></div>
<div class="stat"><span class="muted">Problems in Design A</span><b class="bad">{sum(s.failed for s in ra.scores)}</b><span class="small muted">{sum(s.blocking_failed for s in ra.scores)} blocking</span></div>
<div class="stat"><span class="muted">Score A → B</span><b><span class="bad">{ra.overall:.0f}%</span> → <span class="good">{rb.overall:.0f}%</span></b><span class="small muted">{len(changes)} validated changes</span></div>
</div>
<p><a class="btn" href="{twins['a']}" target="_blank">Open the 3D twin (Design A)</a><a class="btn ghost" href="{twins['b']}" target="_blank">Design B</a><a class="btn ghost" href="#video">Watch the walkthrough</a></p></section>

<section id="flow"><div class="kicker">How it works</div><h2>From a phone scan to a fixed design</h2>
<p class="lead">Every check runs on measured geometry with a citation. Generative world models are used only for what they are good at: making it look real.</p>{FLOW}</section>

<section id="scan"><div class="kicker">Step 1 · Capture</div><h2>The real room, measured</h2>
<p class="lead">RoomPlan gives walls, doors and furniture; a 109-second RGB-D walkthrough (1,092 LiDAR frames) is fused into a 2-million-point model and aligned to it within centimeters.</p>
<div class="grid g3">
<figure><img src="{img['asis']}" alt="Scanned room as is"><figcaption>As scanned: 24 chairs, 7 tables, 4 doors</figcaption></figure>
<figure><img src="{img['shell']}" alt="Empty shell"><figcaption>Empty shell: walls and doors only, {A.floor().area:.0f} m², 3.65 m ceiling</figcaption></figure>
<figure><img src="{img['rgbd']}" alt="RGB-D fusion over plan"><figcaption>RGB-D point cloud aligned to the RoomPlan walls</figcaption></figure></div>
{f'<figure style="margin-top:16px"><img src="{img["pano"]}" alt="Emptied venue panorama"><figcaption>The venue emptied: everything off the walls, floor and ceiling removed geometrically, real carpet re-tiled, rendered as a 360° panorama for World Labs</figcaption></figure>' if img['pano'] else ''}
</section>

<section id="program"><div class="kicker">Step 2 · Research agent</div><h2>What a robotics lab needs</h2>
<p class="lead">{len(know['zones'])} zones and {sum(len(z.get('equipment', [])) for z in know['zones'])} pieces of equipment, each requirement traced to a source: Penn EHRS lab design guidelines, ISO 10218 / 13854 / 13857, ANSI ESD S20.20, university soldering and battery guidance, ADA 2010.</p>
<div class="tablewrap"><table><tr><th>Zone</th><th style="text-align:right">m²</th><th>Priority</th><th>Equipment</th><th>Requirements</th></tr>{program_rows()}</table></div></section>

<section id="design"><div class="kicker">Step 3 · Design agent</div><h2>Design A: a typical first pass</h2>
<p class="lead">The full program laid into the scanned room, color-coded by zone, with a sign at every station. Robot arms, a fenced industrial cell, humanoids, quadrupeds, AMRs and drones in a netted mocap arena.</p>
<div class="grid g2"><figure><img src="{img['a3d']}" alt="Design A 3D"><figcaption>3D twin, Design A</figcaption></figure>
<figure><img src="{img['Testarena']}" alt="Test arena"><figcaption>Netted test arena with motion capture</figcaption></figure>
<figure><img src="{img['Electronics']}" alt="Electronics"><figcaption>ESD electronics benches with wall plaques</figcaption></figure>
<figure><img src="{img['aRobots']}" alt="Robot cells"><figcaption>Cobot cells, maintenance bay, fenced industrial arm</figcaption></figure></div></section>

<section id="agents"><div class="kicker">Step 4 · Persona agents</div><h2>Four agents, each with its own rulebook</h2>
<p class="lead">Each agent has a body model (seated eye height, path width, reach) and a list of cited criteria. They walk real routes from the entrance through the twin.</p>
<div class="grid g2">{agent_cards()}</div></section>

<section id="video"><div class="kicker">Step 5 · Walkthroughs</div><h2>The agents walk the lab</h2>
<p class="lead">Each agent's criteria, then the problems it hits, highlighted where they are, with the measured value, the rule and the fix. Ends with the summary table.</p>
{f'<video src="{vid}" controls preload="metadata" playsinline></video>' if vid else '<p class="muted">Video rendering.</p>'}
{f'<h3 style="margin:28px 0 6px">Twin → photoreal</h3><p class="muted">Each finding\'s view is rendered from the metric twin, then photorealized with a depth-guided diffusion model (geometry locked), then turned into a World Labs Marble world. Drag to compare.</p><div class="grid g2">{pairs_html}</div>' if pairs else ''}
</section>

<section id="findings"><div class="kicker">Step 6 · Report</div><h2>What they found in Design A</h2>
<div class="tablewrap"><table><tr><th>Severity</th><th>Agent</th><th>Finding</th><th>Rule</th><th>Fix</th></tr>{findings_table()}</table></div>
<p class="muted small">Showing the 40 most severe of {sum(s.failed for s in ra.scores)}.</p></section>

<section id="ab"><div class="kicker">Step 7 · Remediation agent</div><h2>Before and after</h2>
<p class="lead">The remediation agent applies each fix, checks it does not create a new collision or block a door, re-audits, and repeats. One program decision is logged for the designer: the fenced industrial arm cannot keep its ISO 13854 crush gaps in this room, so it is recommended for a separate bay.</p>
<div class="tablewrap"><table><tr><th>Agent</th><th style="text-align:right">Checks</th><th style="text-align:right">A failed</th><th style="text-align:right">A blocking</th><th>A score</th><th style="text-align:right">B failed</th><th style="text-align:right">B blocking</th><th>B score</th></tr>{score_rows()}</table></div>
<h3 style="margin:28px 0 8px">Plans with findings</h3>
<div class="ba" style="aspect-ratio:1600/1250"><img src="{img['planB']}" alt="Design B plan"><div class="ba-top"><img src="{img['planA']}" alt="Design A plan"></div><input type="range" min="0" max="100" value="50" aria-label="Design A vs B" oninput="this.parentNode.style.setProperty('--p', this.value + '%')"></div>
<div class="ba-label"><span>◀ Design A · {sum(s.failed for s in ra.scores)} problems</span><span>Design B · {sum(s.failed for s in rb.scores)} minor ▶</span></div>
<h3 style="margin:28px 0 8px">3D, same camera</h3>
<div class="grid g2"><figure><img src="{img['a3d']}" alt="A"><figcaption>Design A</figcaption></figure><figure><img src="{img['b3d']}" alt="B"><figcaption>Design B: color-blind-safe palette, quiet room, screens, aisles opened</figcaption></figure>
<figure><img src="{img['aRobots']}" alt="A robots"><figcaption>Design A robot bay</figcaption></figure><figure><img src="{img['bRobots']}" alt="B robots"><figcaption>Design B robot bay: industrial cell moved out, quiet room in its corner</figcaption></figure></div>
<details><summary>All {len(changes)} changes, each tied to the finding it fixes</summary><div class="tablewrap"><table><tr><th>Agent</th><th>Finding</th><th>Change</th></tr>{change_rows()}</table></div></details></section>

<section id="worlds"><div class="kicker">World models</div><h2>Photoreal worlds (World Labs Marble)</h2>
<p class="lead">Explore in the browser: drag to look, WASD to move. Worlds are for seeing the space; every number on this page comes from the metric twin.</p>
<div class="grid g3">{worlds_html}</div></section>

<section><div class="kicker">Built with</div><p class="muted">iPhone RoomPlan + ARKit LiDAR · Python (shapely, numpy) metric twin and agents · three.js twin · Stable Diffusion 1.5 + ControlNet depth (local, Apple Silicon) · World Labs Marble API · Spark splat renderer · Playwright + ffmpeg video · macOS speech narration.</p></section>
</body></html>"""
(SITE / "index.html").write_text(HTML)
print(f"wrote {SITE}/index.html ({len(list(MEDIA.iterdir()))} media files)")
