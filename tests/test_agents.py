from accesstwin.agents.low_vision import contrast, delta_e, min_char_height
from accesstwin.agents.motion import MotionClearance
from accesstwin.agents.neurodivergent import turns
from accesstwin.audit import audit
from accesstwin.findings import IN
from accesstwin.spec import Space


def test_contrast_matches_wcag_reference():
    assert round(contrast("#ffffff", "#000000"), 1) == 21.0
    assert round(contrast("#ffffff", "#767676"), 2) == 4.54


def test_red_green_merge_for_deuteranopes():
    assert delta_e("#d1242f", "#2da44e") > 40
    assert delta_e("#d1242f", "#2da44e", "deuteranopia") < delta_e("#d1242f", "#2da44e") / 2


def test_char_height_table():
    assert abs(min_char_height(60 * IN, 72 * IN)[0] - 0.625 * IN) < 1e-6
    assert abs(min_char_height(100 * IN, 100 * IN)[0] - 2 * IN) < 1e-6


def test_turns_counts_corners_not_wiggles():
    assert turns([(0, 0), (5, 0), (5, 5), (10, 5)]) == 2
    assert turns([(0, 0), (1, 0.05), (2, -0.05), (3, 0)]) == 0


def test_design_a_motion_findings():
    failed = {(f.rule_id, f.element_id) for f in audit(Space.load("specs/design_a.json"), [MotionClearance()]).failures()}
    assert ("sweep-in-zone", "cobot2") in failed and ("sweep-in-zone", "industrial") in failed
    assert ("estop-outside-sweep", "cobot2") in failed
    assert ("sweep-in-zone", "cobot1") not in failed
