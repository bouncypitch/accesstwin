"""accesstwin audit <spec.json> [--json out.json] [--svg out.svg]
accesstwin import-roomplan <roomplan.json> <out_dir>   writes as_is.json, shell.json and plan SVGs"""

from __future__ import annotations

import argparse
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
    args = ap.parse_args()

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
