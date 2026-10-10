import pytest

from accesstwin.agents.wheelchair import Wheelchair, max_reach
from accesstwin.audit import audit
from accesstwin.findings import IN
from accesstwin.spec import Door, Element, KneeClearance, OperablePart, Space


def aisle_room(aisle_in: float) -> Space:
    """A 6 x 4 m room. Two benches leave an aisle of `aisle_in` inches that is the only way to a bench at the back."""
    gap = aisle_in * IN
    return Space(
        name="aisle test",
        outline=[(0, 0), (6, 0), (6, 4), (0, 4)],
        doors=[Door(id="D", position=(0.5, 0), inward=(0, 1), clear_width=34 * IN, role="both")],
        elements=[
            # A wall of benches across the room at y = 2, with a single gap of `gap` starting at x = 3.
            Element(id="left", kind="partition", center=(1.5, 2.0), size=(3.0, 0.3), height=1.2),
            Element(id="right", kind="partition", center=(3 + gap + 1.5, 2.0), size=(3.0, 0.3), height=1.2),
            Element(id="back", kind="workbench", center=(3.0, 3.6), size=(1.5, 0.6),
                    work_surface_height=30 * IN, knee_clearance=KneeClearance(height=28 * IN, width=32 * IN, depth=20 * IN)),
        ],
    )


def route_finding(space: Space, title: str):
    return next(f for f in audit(space).findings if f.rule_id == "route-clear-width" and title in f.title)


@pytest.mark.parametrize("aisle_in,ok", [(35.0, False), (36.0, True), (36.5, True), (32.0, False)])
def test_aisle_width_threshold(aisle_in, ok):
    f = route_finding(aisle_room(aisle_in), "back")
    assert f.passed is ok
    assert f.measured == pytest.approx(aisle_in * IN, abs=0.005)
    if not ok:
        assert f.fix.op == "move"


def test_fix_moves_furniture_enough():
    space = aisle_room(32.0)
    f = route_finding(space, "back")
    el = space.element(f.fix.element_id)
    el.center = (el.center[0] + f.fix.params["dx"], el.center[1] + f.fix.params["dy"])
    assert route_finding(space, "back").passed


@pytest.mark.parametrize("approach,depth_in,height_in,ok", [
    ("forward", 0, 48, True), ("forward", 0, 48.5, False), ("forward", 0, 14.5, False),
    ("forward", 22, 44, True), ("forward", 22, 45, False), ("forward", 26, 30, False),
    ("side", 0, 48, True), ("side", 12, 46, True), ("side", 12, 47, False), ("side", 25, 30, False),
])
def test_reach_ranges(approach, depth_in, height_in, ok):
    part = OperablePart(id="P", kind="switch", position=(0, 0), height=height_in * IN,
                        approach=approach, obstruction_depth=depth_in * IN)
    hi, _ = max_reach(part)
    assert (hi is not None and 15 * IN <= part.height <= hi + 1e-9) is ok


@pytest.mark.parametrize("width_in,ok", [(31.9, False), (32.0, True)])
def test_door_width(width_in, ok):
    space = aisle_room(40)
    space.doors[0].clear_width = width_in * IN
    f = next(f for f in Wheelchair().doors(space) if f.rule_id == "door-clear-width")
    assert f.passed is ok


def test_design_a_seeded_issues():
    report = audit(Space.load("specs/test_room.json"))
    failed = {(f.rule_id, f.element_id) for f in report.failures()}
    assert failed == {
        ("door-clear-width", "D2"), ("door-opening-force", "D2"),
        ("route-clear-width", "cell2"),  # 32" aisle to e-stop E2
        ("reach-range", "cell1"),  # E1 mounted at 54"
        ("reach-range", "cabinet"),  # keypad at 51" over a 12" obstruction
        ("work-surface-height", "bench1"), ("knee-clearance", "bench1"),
    }
