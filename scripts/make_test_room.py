"""Builds specs/test_room.json: a typical space-efficient first-pass robotics lab with realistic, seeded issues."""
from accesstwin.spec import Space, Door, Element, OperablePart, KneeClearance, Source

IN = 0.0254
W, D = 12.19, 8.53  # 40 ft x 28 ft
aisle = 32 * IN  # seeded: bench-to-cell aisle 32" (< 36")
cell_bottom = 4.5
bench_y = cell_bottom - aisle - 0.375

space = Space(
    name="Test room: hand-built robotics lab",
    outline=[(0, 0), (W, 0), (W, D), (0, D)],
    ceiling_height=3.4,
    source=Source(kind="design", note="Hand-built test room; replaced by the reconstruction of the real venue."),
    doors=[
        Door(id="D1", position=(1.5, 0), inward=(0, 1), clear_width=34 * IN, role="entrance"),
        Door(id="D2", position=(W, 6.5), inward=(-1, 0), clear_width=30 * IN, opening_force_lbf=8, hardware="knob", role="exit"),
    ],
    elements=[
        Element(id="cell1", kind="robot_cell", label="Cobot cell 1 (UR10e)", center=(4.0, 6.0), size=(2.0, 2.0),
                height=2.0, safeguard_margin=0.5,
                parts=[OperablePart(id="E1", kind="e_stop", position=(5.0, 4.5), height=54 * IN, approach="side")]),
        Element(id="cell2", kind="robot_cell", label="Cobot cell 2 (Franka FR3)", center=(8.5, 6.0), size=(2.0, 2.0),
                height=2.0, safeguard_margin=0.5,
                parts=[OperablePart(id="E2", kind="e_stop", position=(8.5, 4.5), height=42 * IN, approach="side")]),
        Element(id="bench1", kind="workbench", label="Electronics bench 1", center=(3.0, bench_y), size=(3.0, 0.75),
                height=0.91, work_surface_height=36 * IN, knee_clearance=None, accessible_station=True),
        Element(id="bench2", kind="workbench", label="Electronics bench 2", center=(7.2, bench_y), size=(3.0, 0.75),
                height=0.91, work_surface_height=36 * IN, knee_clearance=None),
        Element(id="solder", kind="workstation", label="Soldering station", center=(11.0, 1.5), size=(1.5, 0.75),
                height=0.76, work_surface_height=30 * IN, knee_clearance=KneeClearance(height=28 * IN, width=34 * IN, depth=20 * IN),
                parts=[OperablePart(id="FX1", kind="switch", position=(11.0, 1.2), height=36 * IN,
                                    obstruction_depth=0)]),
        Element(id="table", kind="table", label="Teaching table", center=(6.0, 1.2), size=(3.0, 1.2), height=0.74,
                work_surface_height=29 * IN, knee_clearance=KneeClearance(height=28 * IN, width=60 * IN, depth=24 * IN)),
        Element(id="shelf", kind="shelf", label="Parts shelving", center=(0.25, 6.0), size=(2.5, 0.5), rotation_deg=90,
                height=2.0),
        Element(id="cabinet", kind="cabinet", label="Tool cabinet", center=(11.6, 4.5), size=(1.2, 0.6), rotation_deg=-90,
                height=1.8, parts=[OperablePart(id="K1", kind="keypad", position=(11.3, 4.5), height=1.30,
                                                 obstruction_depth=12 * IN)]),
    ],
)
space.save("specs/test_room.json")
print("wrote specs/test_room.json")
