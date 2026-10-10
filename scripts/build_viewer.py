"""Inlines a SpaceSpec (and optionally a tour timeline) into viewer/twin.html so it opens straight from disk.

    uv run python scripts/build_viewer.py [spec.json] [out.html] [tour.json]
"""
import sys
from pathlib import Path

args = sys.argv[1:] + [None] * 3
spec = args[0] or "specs/design_a.json"
out = args[1] or "out/03_design/twin.html"
tour = args[2]


def inline(text: str) -> str:
    return text.replace("</", "<\\/")


html = Path("viewer/twin.html").read_text()
html = html.replace("/*DIRECTOR*/", Path("viewer/director.js").read_text())
html = html.replace("/*SPEC*/", inline(Path(spec).read_text()))
html = html.replace("/*TOUR*/", inline(Path(tour).read_text()) if tour else "null")
Path(out).parent.mkdir(parents=True, exist_ok=True)
Path(out).write_text(html)
print(f"wrote {out}")
