"""SpaceSpec: the metric source of truth for a space. All lengths are meters, all heights are above finished floor."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import Point, Polygon
from shapely.affinity import rotate, translate

Vec2 = tuple[float, float]


class Source(BaseModel):
    """Where a measurement came from, so every number in the twin is traceable."""

    kind: Literal["tape", "lidar", "video", "drawing", "voice", "design"] = "design"
    confidence: float = 1.0
    note: str = ""


class OperablePart(BaseModel):
    """A control someone has to reach and operate: e-stop, switch, handle, outlet, keypad."""

    id: str
    kind: Literal["e_stop", "switch", "outlet", "handle", "keypad", "control_panel"]
    position: Vec2
    height: float
    approach: Literal["forward", "side"] = "forward"
    obstruction_depth: float = 0.0  # depth of the counter or object a seated user reaches over
    one_hand: bool = True
    tight_grasp: bool = False
    force_lbf: float = 2.0


class KneeClearance(BaseModel):
    height: float
    width: float
    depth: float


class Element(BaseModel):
    """Furniture or equipment with a rectangular footprint."""

    id: str
    kind: Literal[
        "workbench", "workstation", "table", "shelf", "cabinet", "robot_cell", "amr_track",
        "equipment", "seating", "storage", "partition",
    ]
    label: str = ""
    center: Vec2
    size: Vec2  # (width along local x, depth along local y)
    rotation_deg: float = 0.0
    height: float = 0.9
    work_surface_height: float | None = None
    knee_clearance: KneeClearance | None = None
    accessible_station: bool = False  # designated as the station a wheelchair user would use
    safeguard_margin: float = 0.0  # robot cells: no-go buffer around the footprint while running
    parts: list[OperablePart] = Field(default_factory=list)
    source: Source = Field(default_factory=Source)

    def footprint(self) -> Polygon:
        w, d = self.size
        box = Polygon([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)])
        return translate(rotate(box, self.rotation_deg, origin=(0, 0)), *self.center)

    def obstacle(self) -> Polygon:
        """Floor area a person cannot occupy (footprint plus any robot safeguard zone)."""
        fp = self.footprint()
        return fp.buffer(self.safeguard_margin, join_style="mitre") if self.safeguard_margin else fp

    def front_point(self, offset: float = 0.0) -> Vec2:
        """Point in front of the element's working face (local -y side), `offset` meters out."""
        _, d = self.size
        a = math.radians(self.rotation_deg)
        dist = d / 2 + self.safeguard_margin + offset
        return (self.center[0] + dist * math.sin(a), self.center[1] - dist * math.cos(a))


class Door(BaseModel):
    id: str
    position: Vec2  # midpoint of the opening, on the wall line
    inward: Vec2  # unit vector pointing into the room
    clear_width: float
    opening_force_lbf: float = 5.0
    hardware: Literal["lever", "push_bar", "knob", "automatic"] = "lever"
    role: Literal["entrance", "exit", "both"] = "both"
    source: Source = Field(default_factory=Source)

    def inside_point(self, depth: float = 0.6) -> Vec2:
        return (self.position[0] + self.inward[0] * depth, self.position[1] + self.inward[1] * depth)


class Space(BaseModel):
    name: str
    outline: list[Vec2]
    ceiling_height: float = 3.0
    doors: list[Door] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    source: Source = Field(default_factory=Source)

    def floor(self) -> Polygon:
        return Polygon(self.outline)

    def element(self, element_id: str) -> Element:
        return next(e for e in self.elements if e.id == element_id)

    def parts(self) -> list[tuple[Element, OperablePart]]:
        return [(e, p) for e in self.elements for p in e.parts]

    @classmethod
    def load(cls, path: str | Path) -> "Space":
        return cls.model_validate(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2))


def point(v: Vec2) -> Point:
    return Point(*v)
