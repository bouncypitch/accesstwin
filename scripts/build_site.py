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

import site_chapters  # noqa: E402

HTML = site_chapters.page({"A": A, "ra": ra, "rb": rb, "know": know, "changes": changes, "MEDIA": MEDIA, "img": img,
                           "twins": twins, "video": video, "pairs_html": pairs_html, "worlds_html": worlds_html,
                           "program_rows": program_rows, "agent_cards": agent_cards, "findings_table": findings_table,
                           "change_rows": change_rows, "score_rows": score_rows})
(SITE / "index.html").write_text(HTML)
print(f"wrote {SITE}/index.html ({len(list(MEDIA.iterdir()))} media files)")
