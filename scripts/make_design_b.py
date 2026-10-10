"""Design B: Design A after the remediation agent applies every agent's fixes. Writes the spec and a change log.

Program decision first: the fenced industrial cell ('could' priority in knowledge/robotics_lab.json) cannot keep the
ISO 13854 500 mm crush gap at full reach anywhere in the east bay of this room, so it is dropped from this space
(the program's rule: drop 'could' items first when space runs out) and recommended for a separate fenced bay.
"""
import json

from accesstwin.audit import audit
from accesstwin.remediate import Change, remediate
from accesstwin.spec import Space

a = Space.load("specs/design_a.json")
base = audit(a)
start = a.model_copy(deep=True)
start.elements = [e for e in start.elements if e.id != "industrial"]
decision = Change(agent="program", rule_id="crush-gap", finding="Industrial arm cell (fenced): gap between arm and wall",
                  change="Dropped the fenced industrial arm cell ('could' priority): a 1.4 m reach needs a 3.8 m clear circle "
                         "the room cannot give it. Recommended for a separate fenced bay.")
b, changes, reports = remediate(start)
changes.insert(0, decision)
reports.insert(0, base)
b.save("specs/design_b.json")
log = {"rounds": [{"overall": r.overall, "scores": [s.model_dump() for s in r.scores]} for r in reports],
       "changes": [c.model_dump() for c in changes]}
open("out/03_design/changes_b.json", "w").write(json.dumps(log, indent=1))
print(f"Design A {reports[0].overall}% -> Design B {reports[-1].overall}% after {len(reports) - 2} rounds, {len(changes)} changes")
for s0, s1 in zip(reports[0].scores, reports[-1].scores):
    print(f"  {s0.name:<26} {s0.score:>5}% -> {s1.score:>5}%   failed {s0.failed} -> {s1.failed}, blocking {s0.blocking_failed} -> {s1.blocking_failed}")
