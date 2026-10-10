"""accesstwin audit <spec.json> [--json out.json]"""

from __future__ import annotations

import argparse
from pathlib import Path

from .audit import audit
from .findings import fmt
from .spec import Space


def main() -> None:
    ap = argparse.ArgumentParser(prog="accesstwin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="audit a SpaceSpec with every persona agent")
    a.add_argument("spec")
    a.add_argument("--json", help="write the full report as JSON")
    args = ap.parse_args()

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


if __name__ == "__main__":
    main()
