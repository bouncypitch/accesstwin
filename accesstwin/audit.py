"""Run persona agents over a space and score the result."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .agents.base import AuditContext, Persona
from .agents.low_vision import LowVision
from .agents.motion import MotionClearance
from .agents.neurodivergent import Neurodivergent
from .agents.wheelchair import Wheelchair
from .findings import Finding
from .spec import Space

WEIGHTS = {"blocking": 5, "major": 2, "minor": 1}


def personas() -> list[Persona]:
    return [Wheelchair(), LowVision(), Neurodivergent(), MotionClearance()]


class AgentScore(BaseModel):
    agent: str
    name: str
    checks: int
    failed: int
    blocking_failed: int
    score: float  # severity-weighted % of checks passed


class Report(BaseModel):
    space: str
    findings: list[Finding]
    scores: list[AgentScore] = Field(default_factory=list)
    overall: float = 0.0

    def failures(self) -> list[Finding]:
        order = list(WEIGHTS)
        return sorted((f for f in self.findings if not f.passed), key=lambda f: order.index(f.severity))


def score(findings: list[Finding]) -> float:
    total = sum(WEIGHTS[f.severity] for f in findings)
    passed = sum(WEIGHTS[f.severity] for f in findings if f.passed)
    return round(100 * passed / total, 1) if total else 100.0


def audit(space: Space, agents: list[Persona] | None = None) -> Report:
    ctx = AuditContext(space)
    findings: list[Finding] = []
    scores = []
    for p in agents or personas():
        fs = p.audit(space, ctx)
        findings += fs
        scores.append(AgentScore(
            agent=p.id, name=p.name, checks=len(fs), failed=sum(not f.passed for f in fs),
            blocking_failed=sum(not f.passed and f.severity == "blocking" for f in fs), score=score(fs),
        ))
    return Report(space=space.name, findings=findings, scores=scores, overall=score(findings))
