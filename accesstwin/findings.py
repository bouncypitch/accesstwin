"""Findings: one failed (or passed) check, traceable to a cited rule and a place in the space."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .spec import Vec2

IN = 0.0254  # meters per inch


def inches(m: float) -> float:
    return m / IN


def fmt(m: float) -> str:
    return f'{inches(m):.1f}" ({m:.2f} m)'


class Citation(BaseModel):
    source: str
    section: str
    url: str
    basis: Literal["legal", "standard", "best_practice"] = "legal"


class Fix(BaseModel):
    """A suggested change. `op` is machine-applicable by the remediation agent."""

    summary: str
    op: Literal["move", "resize", "set", "add", "none"] = "none"
    element_id: str | None = None
    params: dict = Field(default_factory=dict)


class Finding(BaseModel):
    agent: str
    rule_id: str
    title: str
    passed: bool
    severity: Literal["blocking", "major", "minor"] = "major"
    element_id: str | None = None
    location: Vec2 | None = None
    measured: float | None = None
    required: str = ""
    detail: str = ""
    citation: Citation
    fix: Fix | None = None
    path: list[Vec2] = Field(default_factory=list)  # route the persona tried, for walkthroughs


class Rule(BaseModel):
    id: str
    title: str
    citation: Citation
    severity: Literal["blocking", "major", "minor"] = "major"


ADA = "2010 ADA Standards for Accessible Design"
ADA_URL = "https://www.access-board.gov/ada/"


def ada(section: str) -> Citation:
    return Citation(source=ADA, section=section, url=f"{ADA_URL}#ada-{section.replace('.', '_')}")
