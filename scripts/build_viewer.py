"""Inlines a SpaceSpec into viewer/twin.html so the 3D twin opens straight from disk (no server needed)."""
import sys
from pathlib import Path

spec, out = (sys.argv[1:] + ["specs/design_a.json", "out/03_design/twin.html"])[:2]
html = Path("viewer/twin.html").read_text().replace("/*SPEC*/", Path(spec).read_text().replace("</", "<\\/"))
Path(out).parent.mkdir(parents=True, exist_ok=True)
Path(out).write_text(html)
print(f"wrote {out}")
