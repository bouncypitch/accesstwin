"""accesstwin audit <spec.json> [--json out.json] [--svg out.svg]
accesstwin import-roomplan <roomplan.json> <out_dir>   writes as_is.json, shell.json and plan SVGs
accesstwin rgbd <recording_dir> <out_dir> [--roomplan roomplan.json]   fused cloud, alignment, Rerun walkthrough"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from .audit import audit
from . import roomplan
from .findings import fmt
from .render import svg
from .spec import Space


def main() -> None:
    ap = argparse.ArgumentParser(prog="accesstwin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="audit a SpaceSpec with every persona agent")
    a.add_argument("spec")
    a.add_argument("--json", help="write the full report as JSON")
    a.add_argument("--svg", help="write a plan with findings drawn on it")
    r = sub.add_parser("import-roomplan", help="turn a RoomScan export into SpaceSpecs")
    r.add_argument("roomplan")
    r.add_argument("out_dir")
    g = sub.add_parser("rgbd", help="fuse an RGB-D walkthrough and align it to the RoomPlan scan")
    g.add_argument("recording")
    g.add_argument("out_dir")
    g.add_argument("--roomplan")
    g.add_argument("--voxel", type=float, default=0.02)
    g.add_argument("--stride", type=int, default=2, help="use every Nth frame for fusion")
    args = ap.parse_args()

    if args.cmd == "rgbd":
        return rgbd_cmd(args)
    if args.cmd == "import-roomplan":
        return import_roomplan(args.roomplan, args.out_dir)

    space = Space.load(args.spec)
    report = audit(space)
    print(f"\n{report.space}: overall score {report.overall}%\n")
    for s in report.scores:
        print(f"  {s.name:<22} {s.score:>5}%  {s.failed}/{s.checks} failed ({s.blocking_failed} blocking)")
    print()
    for f in report.failures():
        measured = "" if f.measured is None else (f" measured {fmt(f.measured)}" if f.rule_id != "door-opening-force"
                                                   else f" measured {f.measured:.0f} lbf")
        print(f"  [{f.severity.upper():8}] {f.title}:{measured}, required {f.required}  ({f.citation.source} §{f.citation.section})")
        print(f"             {f.detail}")
        if f.fix:
            print(f"             fix: {f.fix.summary}")
    if args.json:
        Path(args.json).write_text(report.model_dump_json(indent=2))
        print(f"\nwrote {args.json}")
    if args.svg:
        Path(args.svg).write_text(svg(space, report.findings))
        print(f"wrote {args.svg}")


def import_roomplan(src: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    as_is = roomplan.load(src, remove="none")
    shell = roomplan.load(src, remove="empty")
    for name, space in (("as_is", as_is), ("shell", shell)):
        space.save(out / f"{name}.json")
        (out / f"{name}.svg").write_text(svg(space))
    floor = shell.floor()
    print(f"floor area {floor.area:.1f} m2 ({floor.area * 10.7639:.0f} ft2), ceiling {fmt(shell.ceiling_height)}")
    print(f"removed all {len(as_is.elements)} objects from the floor; kept {len(shell.doors)} doors and openings")
    for d in shell.doors:
        print(f"  {d.id}: clear width {fmt(d.clear_width)}  ({d.source.note})")
    print("longest walls (check one with a tape):", ", ".join(fmt(w) for w in roomplan.wall_lengths(src)[:4]))
    print(f"wrote {out}/as_is.json, shell.json and SVG plans")


if __name__ == "__main__":
    main()


def rgbd_cmd(args) -> None:
    import json
    import time

    from . import rgbd

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    frames = rgbd.load(args.recording)
    ok = sum(f.tracking == "normal" for f in frames)
    print(f"{len(frames)} frames ({frames[-1].timestamp - frames[0].timestamp:.0f} s), {ok} with normal tracking")
    pts, cols = rgbd.fuse(frames, voxel=args.voxel, stride=args.stride)
    print(f"fused {len(pts):,} points at {args.voxel * 100:.0f} cm voxels in {time.time() - t0:.0f} s")
    al = None
    if args.roomplan:
        al = rgbd.align(pts, args.roomplan)
        print(f"aligned to RoomPlan walls: yaw {math.degrees(al.yaw):.1f} deg, shift {al.t.round(2).tolist()} m")
        pts_out = al.apply(pts)
        offsets = rgbd.wall_offsets(pts_out, args.roomplan)
        print("LiDAR wall surface vs RoomPlan wall (+ = inside the room):")
        for o in offsets:
            print(f"  {o['length']:6.2f} m wall: {o['offset'] * 100:+5.1f} cm  ({o['points']:,} points)")
        (out / "alignment.json").write_text(json.dumps({"yaw": al.yaw, "t": al.t.tolist(), "fit_rms": al.rms,
                                                         "matrix": al.matrix().tolist(), "wall_offsets": offsets},
                                                        indent=2))
        overlay(pts_out, cols, args.roomplan, out / "overlay.png")
        print(f"wrote {out}/overlay.png (fused points over the RoomPlan floor plan)")
    else:
        pts_out = pts
    rgbd.save_ply(out / "fused.ply", pts_out, cols)
    rgbd.to_rerun(frames, pts, cols, out / "walkthrough.rrd", roomplan_path=args.roomplan, alignment=al,
                  stride=args.stride)
    print(f"wrote {out}/fused.ply and {out}/walkthrough.rrd  (view: uv run rerun {out}/walkthrough.rrd)")


def overlay(points, colors, roomplan_path, dest, px_per_m: int = 60) -> None:
    """Top-down image: fused points (colored, mid-height slice darker) with the RoomPlan floor outline."""
    import json

    import numpy as np
    from PIL import Image, ImageDraw

    d = json.loads(Path(roomplan_path).read_text())
    frame = roomplan.plan_frame(d)
    shell = roomplan.load(roomplan_path, remove="empty")
    uv = np.array([frame(x, z) for x, z in points[:, [0, 2]]]) if len(points) < 200_000 else None
    if uv is None:  # vectorised version of frame(x, z) for big clouds
        u, v = points[:, 0], -points[:, 2]
        uu = u * frame.c - v * frame.s - frame.offset[0]
        vv = u * frame.s + v * frame.c - frame.offset[1]
        uv = np.c_[uu, vv]
    minx, miny, maxx, maxy = shell.floor().bounds
    pad = 1.0
    w = int((maxx - minx + 2 * pad) * px_per_m)
    h = int((maxy - miny + 2 * pad) * px_per_m)
    img = Image.new("RGB", (w, h), (251, 250, 247))
    X = ((uv[:, 0] - minx + pad) * px_per_m).astype(int)
    Y = ((maxy - uv[:, 1] + pad) * px_per_m).astype(int)
    ok = (X >= 0) & (X < w) & (Y >= 0) & (Y < h)
    # Draw low points first so walls (tall) end up on top.
    order = np.argsort(points[ok, 1])
    arr = np.asarray(img).copy()
    arr[Y[ok][order], X[ok][order]] = colors[ok][order]
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)
    outline = [((x - minx + pad) * px_per_m, (maxy - y + pad) * px_per_m) for x, y in shell.outline]
    draw.line(outline + outline[:1], fill=(46, 160, 67), width=3)
    img.save(dest)
