"""Builds specs/design_a.json: the robotics lab laid out inside the scanned hackathon venue (RoomPlan shell).

Design A is a plausible first pass by a designer working from knowledge/robotics_lab.json. It fits the full
program into 208 m2 and, like most first passes, makes accessibility mistakes that the persona agents should find.
Wayfinding is color-coded by zone; several of those choices are deliberately weak for low-vision and color-blind
users (red/green zones, pastel text, small high-mounted signs) and are listed in demo/design_a_notes.md.
"""
import math

from accesstwin.spec import Element, KneeClearance, OperablePart, Sign, Source, Space, Zone

IN = 0.0254
shell = Space.load("demo/assets/01_scan_venue/shell.json")
W, D = 18.33, 11.355  # interior extents of the scanned room (x east, y north)

ZONES = [
    Zone(id="welcome", label="Entry, PPE and lockers", color="#8250df"),
    Zone(id="break", label="Kitchenette, dining and restroom", color="#2da44e"),       # green ...
    Zone(id="robots", label="Robot cells", color="#d1242f"),                           # ... vs red: CVD confusion
    Zone(id="arena", label="Test arena", color="#bf8700"),
    Zone(id="electronics", label="Electronics and soldering (ESD)", color="#0969da"),
    Zone(id="fab", label="Fabrication", color="#fb8f44"),
    Zone(id="maintenance", label="Maintenance and repair", color="#e85aad"),
    Zone(id="storage", label="Storage", color="#6e7781"),
    Zone(id="desks", label="Software desks", color="#1b7c83"),
]
ZC = {z.id: z.color for z in ZONES}
LIGHT = {"break": "#a7f3b5", "robots": "#ffb3b3", "arena": "#fff1a8"}  # pastel sign text colors


def sign(zone: str, text: str, style: str = "solid", **kw) -> Sign:
    """solid: white on the zone color. pastel: light zone tint on white (low contrast)."""
    if style == "pastel":
        return Sign(text=text, fg=LIGHT.get(zone, "#d0d7de"), bg="#ffffff", **kw)
    return Sign(text=text, fg="#ffffff", bg=ZC[zone], **kw)


def wall(x_or_y: float, side: str, size, depth_off: float = 0.0) -> tuple[tuple[float, float], float]:
    """Center and rotation for an element backed against a wall, working face toward the room."""
    w, d = size
    if side == "south":
        return (x_or_y, d / 2 + depth_off), 180
    if side == "north":
        return (x_or_y, D - d / 2 - depth_off), 0
    if side == "west":
        return (d / 2 + depth_off, x_or_y), 90
    return (W - d / 2 - depth_off, x_or_y), -90


def front(center, rot, dist) -> tuple[float, float]:
    a = math.radians(rot)
    return (center[0] + dist * math.sin(a), center[1] - dist * math.cos(a))


def el(id, kind, label, center, size, rot=0.0, zone=None, model=None, style="solid", sign_kw=None, **kw) -> Element:
    return Element(id=id, kind=kind, label=label, center=center, size=size, rotation_deg=rot, zone=zone, model=model,
                   sign=sign(zone, label.split(" (")[0], style, **(sign_kw or {})) if zone else None,
                   source=Source(kind="design", note="Design A"), **kw)


E: list[Element] = []

# --- Welcome: lockers and PPE on the west wall between the open doorway (D5) and the main entrance (D1) ---
c, r = wall(4.85, "west", (1.5, 0.45)); E.append(el("lockers", "storage", "Day lockers", c, (1.5, 0.45), r, "welcome", "lockers", height=1.8))
c, r = wall(6.2, "west", (1.0, 0.4)); E.append(el("ppe", "storage", "PPE station (glasses, hearing, coats)", c, (1.0, 0.4), r, "welcome", "ppe_rack", height=1.8))

# --- Break zone (NW): restroom, kitchenette along the north wall, dining ---
E.append(el("restroom", "partition", "Accessible restroom", (1.2, 10.15), (2.3, 2.4), 0, "break", "restroom", height=2.4,
            sign_kw={"mount_height": 1.5}))  # seeded: no raised characters or braille (ADA 703.2-703.4)
c, r = wall(3.75, "north", (2.4, 0.65))
E.append(el("kitchen", "equipment", "Kitchenette (sink, dishwasher)", c, (2.4, 0.65), r, "break", "kitchen_counter", height=0.91,
            parts=[OperablePart(id="SINK", kind="control_panel", position=front(c, r, 0.0), height=0.86, obstruction_depth=0.6)]))
c, r = wall(5.45, "north", (0.8, 0.75))
E.append(el("fridge", "equipment", "Refrigerator", c, (0.8, 0.75), r, "break", "fridge", height=1.8,
            parts=[OperablePart(id="FRIDGE", kind="handle", position=front(c, r, 0.0), height=1.1, approach="side")]))
c, r = wall(6.3, "north", (0.6, 0.5))
E.append(el("microwave", "equipment", "Microwave", c, (0.6, 0.5), r, "break", "microwave", height=1.2,
            parts=[OperablePart(id="MW", kind="control_panel", position=front(c, r, 0.0), height=1.15, obstruction_depth=0.3)]))
# Seeded: the 6-seat table sits 34" from the kitchen counter (ADA 804.2.1 needs 40").
E.append(el("dining1", "table", "Dining table (6 seats)", (3.6, 9.4), (1.8, 0.9), 0, "break", "dining_table", height=0.74,
            work_surface_height=0.74, knee_clearance=KneeClearance(height=0.7, width=1.5, depth=0.48)))
E.append(el("dining2", "table", "Dining table (4 seats, accessible end)", (5.0, 8.3), (1.2, 0.9), 0, "break", "dining_table",
            height=0.74, work_surface_height=0.74, knee_clearance=KneeClearance(height=0.7, width=0.9, depth=0.48)))

# --- Battery cabinet: near exit D2, in view of the benches ---
c, r = wall(0.7, "west", (1.2, 0.6))
E.append(el("battery", "cabinet", "Lithium battery cabinet (charging)", c, (1.2, 0.6), r, "storage", "battery_cabinet",
            height=1.8, parts=[OperablePart(id="BATT", kind="handle", position=front(c, r, 0.0), height=1.0)]))

# --- Electronics: ESD benches and soldering along the quiet south wall ---
for i, x in enumerate([3.2, 5.1, 7.0, 8.9], start=1):
    c, r = wall(x, "south", (1.8, 0.75))
    acc = i == 3
    E.append(el(f"esd{i}", "workbench", f"ESD bench {i}" + (" (height-adjustable)" if acc else ""), c, (1.8, 0.75), r,
                "electronics", "esd_bench", height=0.86 if acc else 0.9, work_surface_height=0.81 if acc else 0.9,
                accessible_station=acc,
                knee_clearance=KneeClearance(height=0.70, width=0.80, depth=0.50) if acc else None,
                # Seeded: tiny pastel-free but small, high signs on benches 1-2 only (sign size check)
                sign_kw={"text_height": 0.012, "mount_height": 1.75} if i in (1, 2) else None))
c, r = wall(10.6, "south", (1.5, 0.75))
E.append(el("solder", "workbench", "Soldering station (fume extraction)", c, (1.5, 0.75), r, "electronics", "solder_station",
            height=0.9, work_surface_height=0.9,
            parts=[OperablePart(id="FUME", kind="switch", position=front(c, r, 0.0), height=1.0, obstruction_depth=0.6)]))
c, r = wall(12.1, "south", (1.2, 0.5))
E.append(el("components", "storage", "ESD component drawers", c, (1.2, 0.5), r, "electronics", "drawers", height=1.5))

# --- Fabrication (SE) ---
c, r = wall(13.6, "south", (1.4, 1.0))
E.append(el("laser", "equipment", "Laser cutter", c, (1.4, 1.0), r, "fab", "laser_cutter", height=1.1,
            parts=[OperablePart(id="LASER", kind="control_panel", position=front(c, r, 0.0), height=1.0)]))
c, r = wall(15.7, "south", (2.4, 0.8))
E.append(el("printers", "equipment", "3D printer bank (HEPA + carbon)", c, (2.4, 0.8), r, "fab", "printer_bank", height=1.9))
c, r = wall(17.65, "south", (1.2, 0.9))
E.append(el("cnc", "equipment", "Benchtop CNC mill", c, (1.2, 0.9), r, "fab", "cnc", height=1.6,
            parts=[OperablePart(id="CNC", kind="e_stop", position=front(c, r, 0.0), height=1.0)]))
E.append(el("mech", "workbench", "Mechanical assembly bench", (14.2, 2.4), (2.0, 0.8), 180, "fab", "mech_bench",
            height=0.9, work_surface_height=0.9))
E.append(el("eyewash", "equipment", "Emergency eyewash", (12.3, 2.4), (0.5, 0.4), 180, "fab", "eyewash", height=1.0,
            parts=[OperablePart(id="EYE", kind="handle", position=front((12.3, 2.4), 180, 0.0), height=0.9)]))

# --- Hardware-in-the-loop bench between electronics and the arena ---
E.append(el("hil", "workbench", "HIL test bench (motor dyno)", (10.4, 3.3), (1.8, 0.8), 0, "electronics", "hil_bench",
            height=0.9, work_surface_height=0.9,
            parts=[OperablePart(id="HIL", kind="e_stop", position=front((10.4, 3.3), 0, 0.0), height=1.0, obstruction_depth=0.5)]))

# --- Cobot teaching corner (south-west of the arena) ---
E.append(el("cobot1", "robot_cell", "Cobot cell 1 (UR5e class)", (4.0, 3.3), (1.2, 1.2), 0, "robots", "cobot_small",
            style="pastel", height=2.0, safeguard_margin=0.5,
            # Seeded: e-stop at 54" (ADA 308 side reach max 48")
            parts=[OperablePart(id="ES1", kind="e_stop", position=(4.0 + 1.1, 3.3), height=54 * IN, approach="side")]))
E.append(el("teach", "workbench", "Teach-pendant bench", (6.3, 3.3), (1.5, 0.75), 90, "robots", "teach_bench",
            style="pastel", height=0.9, work_surface_height=0.86))
E.append(el("desks", "table", "Software desks (3 seats)", (3.4, 5.6), (3.6, 0.8), 0, "desks", "desk_row",
            height=0.74, work_surface_height=0.74, knee_clearance=KneeClearance(height=0.69, width=1.0, depth=0.5)))

# --- Test arena: 6 x 6 m netted mocap volume, center of the room ---
E.append(el("arena", "amr_track", "Test arena (netted, motion capture)", (10.0, 7.3), (6.0, 6.0), 0, "arena", "arena",
            style="pastel", height=3.0, sign_kw={"text_height": 0.15, "mount_height": 2.55}))  # banner on the truss
E.append(el("mocap", "workstation", "Mocap operator station", (6.4, 7.3), (1.4, 0.7), -90, "arena", "mocap_station",
            style="pastel", height=0.75, work_surface_height=0.74,
            knee_clearance=KneeClearance(height=0.69, width=0.8, depth=0.48)))

# --- Storage along the north wall behind the arena (seeded: 22" aisle) ---
for id_, label, x, size, kind, model in [
    ("shelving", "Parts shelving", 8.0, (2.4, 0.5), "shelf", "shelving"),
    ("rawstock", "Raw stock rack", 10.2, (1.8, 0.6), "shelf", "raw_stock"),
    ("flammables", "Flammable liquids cabinet", 11.8, (1.1, 0.5), "cabinet", "flammables"),
]:
    c, r = wall(x, "north", size)
    E.append(el(id_, kind, label, c, size, r, "storage", model, height=2.0 if kind == "shelf" else 1.7))

# --- Maintenance bay between the arena and the robot cells ---
E.append(el("repair", "workbench", "Robot repair bench", (15.1, 5.0), (2.0, 0.8), -90, "maintenance", "repair_bench",
            height=0.9, work_surface_height=0.9))
E.append(el("humanoid_stand", "equipment", "Humanoid service stand (hoist)", (14.1, 7.3), (1.2, 1.2), 0, "maintenance",
            "humanoid_stand", height=2.4))
E.append(el("quad_stand", "equipment", "Quadruped service stand", (14.1, 8.7), (1.2, 0.7), 90, "maintenance", "quad_stand",
            height=0.7))
E.append(el("spares", "cabinet", "Spare actuators and sensors", (15.55, 7.0), (1.2, 0.5), -90, "maintenance", "spares",
            height=1.9, parts=[OperablePart(id="SPARE", kind="handle", position=front((15.55, 7.0), -90, 0.0), height=1.0)]))
E.append(el("parking", "storage", "Robot parking", (13.85, 10.75), (1.8, 1.0), 0, "maintenance", "robot_parking", height=0.6))

# --- Robot cells on the east side ---
E.append(el("cobot2", "robot_cell", "Cobot cell 2 (UR10e class)", wall(4.92, "east", (1.5, 1.5), 0.5)[0], (1.5, 1.5), 0,
            "robots", "cobot_large", style="pastel", height=2.0, safeguard_margin=0.5,
            parts=[OperablePart(id="ES2", kind="e_stop", position=(W - 0.5 - 1.5 - 0.5 - 0.05, 4.92), height=1.07, approach="side")]))
E.append(el("industrial", "robot_cell", "Industrial arm cell (fenced)", (16.55, 9.8), (1.6, 1.6), 0, "robots", "industrial_cage",
            style="pastel", height=2.2, safeguard_margin=0.7,
            parts=[OperablePart(id="ES3", kind="e_stop", position=(14.98, 9.0), height=1.07, approach="side"),
                   OperablePart(id="CTRL", kind="control_panel", position=(14.98, 9.6), height=1.1)]))

space = Space(name="Design A: robotics lab in the hackathon venue", outline=shell.outline,
              ceiling_height=shell.ceiling_height, doors=shell.doors, elements=E, zones=ZONES,
              source=Source(kind="design", note="Layout over the RoomPlan scan of the venue; program from knowledge/robotics_lab.json"))

# Sanity: nothing overlaps another element or leaves the room.
floor = space.floor()
for i, a in enumerate(E):
    assert floor.buffer(1e-6).contains(a.footprint()), f"{a.id} leaves the room"
    for b in E[i + 1:]:
        inside = {a.model, b.model} & {"arena"}
        if not inside and a.footprint().intersection(b.footprint()).area > 1e-4:
            raise SystemExit(f"overlap: {a.id} / {b.id}")
space.save("specs/design_a.json")
print(f"wrote specs/design_a.json: {len(E)} elements in {floor.area:.0f} m2")
