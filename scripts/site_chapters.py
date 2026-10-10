"""Chapter layout for the demo site: the same 11 chapters as the story video, each with its own looping clip.

Imported by build_site.py after the data helpers are defined (it uses the names passed in `ctx`).
"""
import json
import subprocess
from html import escape
from pathlib import Path

CSS = """
:root{--bg:#0b0e13;--card:#151a21;--line:#252b34;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--good:#3fb950;--bad:#f85149}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#fafbfc;--card:#ffffff;--line:#e1e4e8;--text:#1f2328;--muted:#57606a;--accent:#0969da;--good:#1a7f37;--bad:#cf222e}}
:root[data-theme="light"]{--bg:#fafbfc;--card:#ffffff;--line:#e1e4e8;--text:#1f2328;--muted:#57606a;--accent:#0969da;--good:#1a7f37;--bad:#cf222e}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font:17px/1.55 Inter,-apple-system,Helvetica,Arial,sans-serif}
a{color:var(--accent)} img,video{max-width:100%;width:100%;display:block;border-radius:14px;background:#000}
nav{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
nav .in{max-width:1100px;margin:auto;padding:10px 16px;display:flex;gap:16px;overflow-x:auto;white-space:nowrap;font-size:13px}
nav a{color:var(--muted);text-decoration:none} nav a:hover{color:var(--text)} nav b{color:var(--text)}
section{max-width:1100px;margin:auto;padding:72px 16px 24px}
h1{font-size:clamp(44px,8vw,84px);line-height:1;margin:0 0 16px;letter-spacing:-.035em} h2{font-size:clamp(28px,4vw,42px);margin:0 0 10px;letter-spacing:-.025em}
h3{margin:0;font-size:18px} .kicker{color:var(--accent);font-weight:650;letter-spacing:.14em;font-size:13px;margin-bottom:6px}
.lead{font-size:clamp(17px,2vw,21px);color:var(--muted);max-width:820px;margin:0 0 22px} .muted{color:var(--muted)} .small{font-size:13px}
.grid{display:grid;gap:16px} .g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))} .g3{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.agent{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px} .stat b{display:block;font-size:34px;letter-spacing:-.02em}
table{width:100%;border-collapse:collapse;font-size:14px} th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em;padding:8px}
td{padding:9px 8px;border-top:1px solid var(--line);vertical-align:top} td.n{text-align:right;font-variant-numeric:tabular-nums;font-weight:650}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--card);margin-top:10px} .tablewrap td:first-child,.tablewrap th:first-child{padding-left:14px}
.bad{color:var(--bad)} .good{color:var(--good)} .fix{color:var(--good)}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:8px;vertical-align:middle}
.bar{height:7px;background:var(--line);border-radius:4px;overflow:hidden;margin-bottom:3px;min-width:80px} .bar i{display:block;height:100%}
.sev{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;padding:2px 8px;border-radius:5px;color:#fff;white-space:nowrap}
.sev.blocking{background:#d1242f} .sev.major{background:#bc4c00} .sev.minor{background:#9a6700}
.pri{font-size:12px;font-weight:700;padding:2px 8px;border-radius:5px;background:var(--line)} .pri.must{background:#1f6feb;color:#fff}
.agent header{display:flex;align-items:center;gap:8px} .agent .dot{background:var(--c);width:14px;height:14px}
.crit{padding-left:20px;margin:12px 0} .crit li{margin:6px 0} .crit em{display:block;color:var(--muted);font-size:12px;font-style:normal}
.found{border-top:1px solid var(--line);padding-top:10px;margin:0} .found b{color:var(--c)}
.ba{position:relative;--p:45%;border-radius:14px;overflow:hidden;aspect-ratio:16/9;background:#000}
.ba img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:0} .ba-top{position:absolute;inset:0;clip-path:inset(0 calc(100% - var(--p)) 0 0)}
.ba-top::after{content:"";position:absolute;top:0;bottom:0;left:var(--p);width:2px;background:#fff;box-shadow:0 0 8px #000}
.ba input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}
.ba-label{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin-top:6px}
figure{margin:0} figcaption{color:var(--muted);font-size:14px;margin-top:8px}
.world{display:block;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;text-decoration:none;color:var(--text)}
.world img{border-radius:0;aspect-ratio:16/9;object-fit:cover} .ph{display:grid;place-items:center;background:var(--line);color:var(--muted);aspect-ratio:16/9;border-radius:14px}
.world .ph{border-radius:0} .world span{display:block;padding:10px 12px;font-size:13px}
.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-weight:650;padding:10px 16px;border-radius:10px;margin:14px 8px 0 0}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--line)}
details summary{cursor:pointer;color:var(--accent);margin:16px 0 4px}
footer{max-width:1100px;margin:auto;padding:48px 16px;color:var(--muted);font-size:13px}
"""


def page(c: dict) -> str:
    A, ra, rb, know, changes, MEDIA = c["A"], c["ra"], c["rb"], c["know"], c["changes"], c["MEDIA"]
    story = Path("out/04_tour/story/accesstwin_story.mp4")
    st = json.loads(Path("out/04_tour/story/tour.json").read_text())
    chap = [(s["chapter"], s["t0"]) for s in st["segments"] if s.get("chapter")]
    bounds = [(n, t0, chap[i + 1][1] if i + 1 < len(chap) else st["duration"]) for i, (n, t0) in enumerate(chap)]
    clips = {}
    if story.exists():
        for i, (n, t0, t1) in enumerate(bounds):
            dest = MEDIA / f"ch{i + 1:02d}.mp4"
            if not dest.exists() or dest.stat().st_mtime < story.stat().st_mtime:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.2f}", "-to", f"{t1:.2f}", "-i", str(story), "-an",
                                "-vf", "scale=1280:-2", "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                                "-movflags", "+faststart", str(dest)], check=True)
            poster = dest.with_suffix(".jpg")
            if not poster.exists() or poster.stat().st_mtime < dest.stat().st_mtime:
                mid = max(0.5, (t1 - t0) * 0.6)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", str(dest), "-frames:v", "1",
                                "-q:v", "3", str(poster)], check=True)
            clips[n] = f"media/{dest.name}"
    full = c["video"](str(story), "accesstwin_story.mp4") if story.exists() else None
    fa, fb = sum(s.failed for s in ra.scores), sum(s.failed for s in rb.scores)
    ba, bb = sum(s.blocking_failed for s in ra.scores), sum(s.blocking_failed for s in rb.scores)
    img, twins = c["img"], c["twins"]

    def clip(n: str) -> str:
        if n in clips:
            return (f'<video src="{clips[n]}" poster="{clips[n][:-4]}.jpg" autoplay muted loop playsinline '
                    'preload="auto"></video>')
        return '<div class="ph">clip rendering</div>'

    text = {
        "The problem": "Benches, controls and signs built for one standard body quietly shut out wheelchair users, people with "
                       "low vision and neurodivergent workers, and it is usually discovered after the space is built.",
        "Our solution": "A phone scan becomes a measured digital twin. AI agents, each living with a different disability, walk "
                        "it, cite every problem and fix the design before anything is bought.",
        "Live example": "This hackathon room, scanned tonight, redesigned as a full robotics lab.",
        "The RGB-D scan": f"iPhone LiDAR and video: 1,092 frames fused into 2 million colored points, aligned to the RoomPlan "
                          f"walls. {A.floor().area:.0f} m², 3.65 m ceiling.",
        "Remove people and tables": "Everything that is not wall, floor or ceiling is removed geometrically, and the carpet underneath "
                                    "is re-tiled from a clean patch of the real carpet. No one captured in the scan survives.",
        "Research the lab": f"{len(know['zones'])} zones and {sum(len(z.get('equipment', [])) for z in know['zones'])} pieces of "
                            f"equipment, every requirement traced to one of {len(know['sources'])} sources: ISO 10218 / 13854 / "
                            "13857, ANSI ESD S20.20, Penn EHRS lab guidelines, university battery and soldering guidance, ADA 2010.",
        "Add everything": f"Design A: {len(A.elements)} stations in {len(A.zones)} color-coded zones, a sign at every one. Robot arms, "
                          "a fenced industrial cell, humanoids, quadrupeds, AMRs and drones in a netted mocap arena.",
        "The disability agents": "Four agents, each with a body model and a cited rulebook.",
        "Where the agents find issues": "Each agent walks real routes from the entrance. Every problem is shown where it is, as a "
                                        "photoreal World Labs world, with the measured value, the rule and the fix.",
        "Fix the design": f"A remediation agent applies {len(changes)} validated changes and the agents re-audit. One program "
                          "decision is left to the designer: the industrial arm moves to its own fenced bay.",
        "The results": "Design A versus Design B: same room, same agents.",
    }
    slider = (f'<div class="ba" style="aspect-ratio:1600/1250;margin-top:16px"><img src="{img["planB"]}" alt="Design B plan">'
              f'<div class="ba-top"><img src="{img["planA"]}" alt="Design A plan"></div>'
              '<input type="range" min="0" max="100" value="50" aria-label="Design A vs B" '
              'oninput="this.parentNode.style.setProperty(\'--p\', this.value + \'%\')"></div>'
              f'<div class="ba-label"><span>◀ Design A · {fa} problems</span><span>Design B · {fb} minor ▶</span></div>')
    extra = {
        "Research the lab": '<details><summary>The lab program</summary><div class="tablewrap"><table><tr><th>Zone</th>'
                            '<th style="text-align:right">m²</th><th>Priority</th><th>Equipment</th><th>Requirements</th></tr>'
                            + c["program_rows"]() + "</table></div></details>",
        "The disability agents": f'<div class="grid g2">{c["agent_cards"]()}</div>',
        "Where the agents find issues": (f'<div class="grid g2" style="margin-top:16px">{c["pairs_html"]}</div>'
                                         '<p class="muted small">Drag: metric twin render ◀▶ photoreal frame.</p>' if c["pairs_html"] else "")
            + f'<details><summary>All {fa} findings in Design A</summary><div class="tablewrap"><table><tr><th>Severity</th>'
              '<th>Agent</th><th>Finding</th><th>Rule</th><th>Fix</th></tr>' + c["findings_table"]() + "</table></div></details>",
        "Fix the design": slider + f'<details><summary>All {len(changes)} changes</summary><div class="tablewrap"><table><tr>'
                                   '<th>Agent</th><th>Finding</th><th>Change</th></tr>' + c["change_rows"]() + "</table></div></details>",
        "The results": f'''<div class="stats"><div class="stat"><span class="muted">Score</span><b><span class="bad">{ra.overall:.0f}%</span> → <span class="good">{rb.overall:.0f}%</span></b></div>
          <div class="stat"><span class="muted">Problems</span><b><span class="bad">{fa}</span> → <span class="good">{fb}</span></b></div>
          <div class="stat"><span class="muted">Blocking</span><b><span class="bad">{ba}</span> → <span class="good">{bb}</span></b></div>
          <div class="stat"><span class="muted">Checks</span><b>{sum(s.checks for s in ra.scores)}</b></div></div>
          <div class="tablewrap" style="margin-top:16px"><table><tr><th>Agent</th><th style="text-align:right">Checks</th><th style="text-align:right">A failed</th><th style="text-align:right">A blocking</th><th>A score</th><th style="text-align:right">B failed</th><th style="text-align:right">B blocking</th><th>B score</th></tr>{c["score_rows"]()}</table></div>
          <p><a class="btn" href="{twins['a']}" target="_blank">Explore Design A in 3D</a><a class="btn ghost" href="{twins['b']}" target="_blank">Design B</a></p>
          <h3 style="margin:28px 0 10px">Photoreal worlds · World Labs Marble</h3><div class="grid g3">{c["worlds_html"]}</div>''',
    }
    chapters = "\n".join(f'<section id="ch{i + 1}"><div class="kicker">{i + 1:02d}</div><h2>{escape(n)}</h2>'
                         f'<p class="lead">{escape(text.get(n, ""))}</p>{clip(n)}{extra.get(n, "")}</section>'
                         for i, (n, _, _) in enumerate(bounds))
    nav = "".join(f'<a href="#ch{i + 1}">{escape(n)}</a>' for i, (n, _, _) in enumerate(bounds))
    hero = f'<video src="{full}" poster="media/ch09.jpg" controls preload="metadata" playsinline></video>' if full else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AccessTwin Demo</title>
<meta name="description" content="Walk a workplace before it is built, as the people it might shut out. 70% to 99% accessibility score, 68 to 3 problems.">
<meta property="og:title" content="AccessTwin"><meta property="og:description" content="Walk a workplace before it is built, as the people it might shut out.">
<meta property="og:image" content="https://bouncypitch.github.io/accesstwin/media/social-preview.png"><meta property="og:url" content="https://bouncypitch.github.io/accesstwin/">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="https://bouncypitch.github.io/accesstwin/media/social-preview.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;650;800&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<nav><div class="in"><b>AccessTwin</b>{nav}</div></nav>
<section><div class="kicker">FUTURE OF WORK HACKATHON · TRACK 1</div><h1>AccessTwin</h1>
<p class="lead">Walk a workplace before it is built, as the people it might shut out.</p>{hero}</section>
{chapters}
<footer>Built with iPhone RoomPlan + ARKit LiDAR · Python metric twin and agents (shapely, numpy) · three.js · Stable Diffusion 1.5 + ControlNet depth on Apple Silicon · World Labs Marble API · Spark · Playwright + ffmpeg · macOS neural voice. Every number on this page comes from the metric twin; world models are used only for visuals.</footer>
</body></html>"""
