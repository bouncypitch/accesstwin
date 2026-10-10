"""Top-down SVG plans of a SpaceSpec, optionally with audit findings and routes drawn on top."""

from __future__ import annotations

from html import escape

from .findings import Finding, fmt
from .spec import Space

FILL = {
    "robot_cell": "#f4c7a1", "workbench": "#b9d3ee", "workstation": "#b9d3ee", "table": "#d8d2c4",
    "seating": "#e6e1d6", "storage": "#cfc6e8", "shelf": "#cfc6e8", "cabinet": "#cfc6e8",
    "equipment": "#c9dfc4", "partition": "#bbbbbb", "amr_track": "#f1e3a6",
}
SEVERITY = {"blocking": "#d1242f", "major": "#e8710a", "minor": "#b58b00"}


def svg(space: Space, findings: list[Finding] | None = None, width_px: int = 1200, title: str | None = None,
        show_routes: bool = True) -> str:
    floor = space.floor()
    minx, miny, maxx, maxy = floor.bounds
    pad = 0.8
    sx = width_px / (maxx - minx + 2 * pad)
    h_px = (maxy - miny + 2 * pad) * sx + 60

    def X(x): return (x - minx + pad) * sx
    def Y(y): return (maxy - y + pad) * sx + 60  # flip so +y is up

    def poly(coords, **attrs):
        pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in coords)
        a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return f'<polygon points="{pts}" {a}/>'

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {h_px:.0f}" '
           f'font-family="Inter, Helvetica, Arial, sans-serif">',
           f'<rect width="100%" height="100%" fill="#fbfaf7"/>',
           f'<text x="24" y="38" font-size="22" font-weight="600" fill="#1f2328">{escape(title or space.name)}</text>']
    # 1 m grid
    for gx in range(int(minx), int(maxx) + 1):
        out.append(f'<line x1="{X(gx):.1f}" y1="{Y(miny):.1f}" x2="{X(gx):.1f}" y2="{Y(maxy):.1f}" stroke="#eeeae2" stroke-width="1"/>')
    for gy in range(int(miny), int(maxy) + 1):
        out.append(f'<line x1="{X(minx):.1f}" y1="{Y(gy):.1f}" x2="{X(maxx):.1f}" y2="{Y(gy):.1f}" stroke="#eeeae2" stroke-width="1"/>')
    out.append(poly(floor.exterior.coords, fill="#ffffff", stroke="#1f2328", stroke_width=6, stroke_linejoin="round"))

    for e in space.elements:
        if e.safeguard_margin:
            out.append(poly(e.obstacle().exterior.coords, fill="#f4c7a1", fill_opacity=0.35, stroke="#c4561a",
                            stroke_width=1.5, stroke_dasharray="6 4"))
        out.append(poly(e.footprint().exterior.coords, fill=FILL.get(e.kind, "#dddddd"), stroke="#57606a", stroke_width=1.2))
        c = e.footprint().centroid
        if e.size[0] * sx > 60:
            out.append(f'<text x="{X(c.x):.1f}" y="{Y(c.y) + 4:.1f}" font-size="11" text-anchor="middle" fill="#1f2328">'
                       f'{escape(e.label or e.id)}</text>')
        for p in e.parts:
            out.append(f'<circle cx="{X(p.position[0]):.1f}" cy="{Y(p.position[1]):.1f}" r="5" '
                       f'fill="{"#d1242f" if p.kind == "e_stop" else "#57606a"}" stroke="#fff" stroke-width="1.5"/>')

    for d in space.doors:
        # Draw the opening as a gap marker across the wall, perpendicular to the inward normal.
        tx, ty = -d.inward[1], d.inward[0]
        half = (d.clear_width + 0.05) / 2
        a = (d.position[0] - tx * half, d.position[1] - ty * half)
        b = (d.position[0] + tx * half, d.position[1] + ty * half)
        out.append(f'<line x1="{X(a[0]):.1f}" y1="{Y(a[1]):.1f}" x2="{X(b[0]):.1f}" y2="{Y(b[1]):.1f}" '
                   f'stroke="#fbfaf7" stroke-width="9"/>')
        out.append(f'<line x1="{X(a[0]):.1f}" y1="{Y(a[1]):.1f}" x2="{X(b[0]):.1f}" y2="{Y(b[1]):.1f}" '
                   f'stroke="#2da44e" stroke-width="3"/>')
        lx, ly = d.inside_point(0.45)
        out.append(f'<text x="{X(lx):.1f}" y="{Y(ly) + 4:.1f}" font-size="11" text-anchor="middle" fill="#1a7f37">'
                   f'{d.id}{" (in)" if d.role == "entrance" else ""}</text>')

    for f in findings or []:
        if f.passed or f.location is None:
            continue
        color = SEVERITY[f.severity]
        if show_routes and f.path:
            pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in f.path[::3])
            out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-opacity="0.55"/>')
        x, y = X(f.location[0]), Y(f.location[1])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{color}" stroke="#fff" stroke-width="2.5">'
                   f'<title>{escape(f.title)}: {escape(f.detail)}</title></circle>')
        out.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="12" font-weight="700" text-anchor="middle" fill="#fff">!</text>')

    # Scale bar
    bx, by = 24, h_px - 20
    out.append(f'<line x1="{bx}" y1="{by}" x2="{bx + sx:.1f}" y2="{by}" stroke="#1f2328" stroke-width="3"/>')
    out.append(f'<text x="{bx + sx + 8:.1f}" y="{by + 4}" font-size="12" fill="#1f2328">1 m</text>')
    w, h = maxx - minx, maxy - miny
    out.append(f'<text x="{width_px - 24}" y="38" font-size="14" text-anchor="end" fill="#57606a">'
               f'{escape(fmt(w))} x {escape(fmt(h))} bounding box</text>')
    out.append("</svg>")
    return "\n".join(out)
