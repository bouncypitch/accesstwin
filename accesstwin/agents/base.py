"""Persona agents: a body model plus a rulebook, run against a SpaceSpec."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Point
from shapely.ops import nearest_points

from ..findings import Finding
from ..geometry import FreeSpace, RoutePlanner
from ..spec import Element, Space, Vec2


@dataclass
class Body:
    path_width: float  # clear width the person needs to move along a route
    turn_diameter: float | None = None
    eye_height: float = 1.6  # first-person camera height for walkthroughs


class Persona:
    id: str = ""
    name: str = ""
    summary: str = ""
    criteria: list[tuple[str, str]] = []  # (what is checked, citation), shown on walkthrough title cards
    body: Body

    def audit(self, space: Space, ctx: "AuditContext") -> list[Finding]:
        raise NotImplementedError


class AuditContext:
    """Shared analysis for one space, computed once and reused by every persona."""

    def __init__(self, space: Space):
        self.space = space
        self.free = FreeSpace(space)
        entrances = [d for d in space.doors if d.role in ("entrance", "both")]
        self.entrance = entrances[0] if entrances else None
        self.planner = RoutePlanner(self.free, self.entrance.inside_point()) if self.entrance else None


def approach_point(el: Element, at: Vec2, standoff: float = 0.45) -> Vec2:
    """Where a person stands to use something at `at` on element `el`: outside its obstacle, facing it."""
    obs = el.obstacle()
    edge, _ = nearest_points(obs.exterior, Point(at))
    cx, cy = obs.centroid.x, obs.centroid.y
    dx, dy = edge.x - cx, edge.y - cy
    n = math.hypot(dx, dy) or 1.0
    return (edge.x + dx / n * standoff, edge.y + dy / n * standoff)
