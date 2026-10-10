"""Low vision and color vision deficiency: sign contrast, character size, color-only coding, tactile signs."""

from __future__ import annotations

import itertools
import math

import numpy as np

from ..findings import IN, Citation, Finding, Fix, ada
from ..spec import Space
from .base import AuditContext, Body, Persona

ID = "low_vision"

WCAG = "WCAG 2.2"
WCAG_URL = "https://www.w3.org/TR/WCAG22/"


def wcag(section: str) -> Citation:
    return Citation(source=WCAG, section=section, url=WCAG_URL, basis="best_practice")


def _lin(c: str) -> np.ndarray:
    v = np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def luminance(c: str) -> float:
    return float(np.dot(_lin(c), [0.2126, 0.7152, 0.0722]))


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# Machado, Oliveira & Fernandes (2009), severity 1.0, applied in linear RGB.
CVD = {
    "protanopia": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]),
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]),
}


def _lab(lin: np.ndarray) -> np.ndarray:
    xyz = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]) @ np.clip(lin, 0, 1)
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def delta_e(a: str, b: str, cvd: str | None = None) -> float:
    la, lb = _lin(a), _lin(b)
    if cvd:
        la, lb = CVD[cvd] @ la, CVD[cvd] @ lb
    return float(np.linalg.norm(_lab(la) - _lab(lb)))


def min_char_height(mount: float, distance: float) -> tuple[float, str]:
    """ADA 703.5.5 Table: minimum visual character height for a sign's mounting height and viewing distance."""
    h, d = mount / IN, distance / IN
    if h <= 70:
        need = 5 / 8 + (max(0.0, d - 72) / 12) * (1 / 8)
    elif h <= 120:
        need = 2 + (max(0.0, d - 180) / 12) * (1 / 8)
    else:
        need = 3 + (max(0.0, d - 252) / 12) * (1 / 8)
    return need * IN, "703.5.5"


VIEWING_DISTANCE = 1.8  # m: reading a station sign from the aisle in front of it


class LowVision(Persona):
    id = ID
    name = "Low vision / color-blind"
    summary = "Reduced acuity and contrast sensitivity, or red-green color blindness (~8% of men)."
    body = Body(path_width=36 * IN, eye_height=1.6)
    criteria = [
        ("Sign contrast 4.5:1 or better between letters and background", "WCAG 1.4.3, ADA 703.5.1"),
        ("Letter height large enough for the mounting height and viewing distance", "ADA 703.5.5"),
        ("Zone colors stay distinct for red-green color blindness (protanopia, deuteranopia)", "WCAG 1.4.1"),
        ("Zones identified by name or pictogram, not color alone", "WCAG 1.4.1"),
        ("Room signs have raised characters and braille at 48-60\"", "ADA 216.2, 703.2-703.4"),
    ]

    def audit(self, space: Space, ctx: AuditContext) -> list[Finding]:
        return self.signs(space) + self.zone_colors(space)

    def signs(self, space: Space) -> list[Finding]:
        out = []
        for e in space.elements:
            s = e.sign
            if s is None:
                continue
            at = e.front_point(0.6)
            cr = contrast(s.fg, s.bg)
            ok = cr >= 4.5
            sev = "minor" if cr >= 3.0 else "major"
            out.append(Finding(
                agent=ID, rule_id="sign-contrast", title=f'Sign contrast: "{s.text}"', passed=ok, severity=sev,
                element_id=e.id, location=at, measured=round(cr, 2), required=">= 4.5:1",
                citation=wcag("1.4.3 (and ADA 703.5.1)"),
                detail=f"{s.fg} on {s.bg} is {cr:.1f}:1." + ("" if ok else " Hard to read with low contrast sensitivity."),
                fix=None if ok else Fix(summary=f'Reprint "{s.text}" as white on a darker zone color (>= 4.5:1).',
                                        op="set", element_id=e.id, params={"sign.fg": "#ffffff", "sign.bg": "darken"}),
            ))
            need, sec = min_char_height(s.mount_height, VIEWING_DISTANCE)
            ok = s.text_height >= need - 1e-4
            out.append(Finding(
                agent=ID, rule_id="sign-char-height", title=f'Letter height: "{s.text}"', passed=ok, severity="major",
                element_id=e.id, location=at, measured=s.text_height, required=f'>= {need / IN:.2f}" ({need * 1000:.0f} mm)',
                citation=ada(sec),
                detail=f'Capitals are {s.text_height * 1000:.0f} mm at {s.mount_height / IN:.0f}" high, read from {VIEWING_DISTANCE:.1f} m.',
                fix=None if ok else Fix(summary=f'Enlarge the lettering on "{s.text}" to at least {need * 1000:.0f} mm.',
                                        op="set", element_id=e.id, params={"sign.text_height": round(max(need, 0.05), 3)}),
            ))
            if e.kind == "partition":  # an enclosed room: its door sign is a room-identification sign
                ok = s.tactile and 48 * IN <= s.mount_height <= 60 * IN
                out.append(Finding(
                    agent=ID, rule_id="tactile-sign", title=f'Tactile room sign: "{s.text}"', passed=ok, severity="major",
                    element_id=e.id, location=at, required="raised characters + Grade 2 braille, baseline 48-60\"",
                    citation=ada("216.2, 703.2-703.4"),
                    detail="Room signs need raised characters and braille so blind users can find the room." if not ok
                           else "Tactile sign at the correct height.",
                    fix=None if ok else Fix(summary=f'Replace with a tactile + braille sign, baseline at 54", latch side.',
                                            op="set", element_id=e.id, params={"sign.tactile": True, "sign.mount_height": round(54 * IN, 3)}),
                ))
        return out

    def zone_colors(self, space: Space) -> list[Finding]:
        out = []
        zones = space.zones
        if not zones:
            return out
        for a, b in itertools.combinations(zones, 2):
            normal = delta_e(a.color, b.color)
            worst, kind = min((delta_e(a.color, b.color, k), k) for k in CVD)
            ok = not (normal >= 20 and worst < 12)
            centers = [e.center for e in space.elements if e.zone in (a.id, b.id)]
            loc = (float(np.mean([c[0] for c in centers])), float(np.mean([c[1] for c in centers]))) if centers else None
            safety = {a.id, b.id} & {"robots", "fab"}
            out.append(Finding(
                agent=ID, rule_id="zone-color-cvd", title=f"Zone colors {a.label} vs {b.label}", passed=ok,
                severity=("major" if safety else "minor"), location=loc, measured=round(worst, 1),
                required="stay distinct (dE >= 12) under protanopia/deuteranopia",
                citation=wcag("1.4.1 Use of Color"),
                detail=(f"{a.color} vs {b.color}: dE {normal:.0f} for typical vision but {worst:.0f} with {kind}."
                        + (" These zones look the same to a color-blind visitor." if not ok else "")),
                fix=None if ok else Fix(summary=f"Change {b.label} to a color that differs in lightness, or add a pattern.",
                                        op="set", params={"zone": b.id}),
            ))
        has_text = all(e.sign is None or e.sign.pictogram for e in space.elements)
        out.append(Finding(
            agent=ID, rule_id="color-only-coding", title="Zones identified by color alone", passed=has_text,
            severity="major", location=(sum(x for x, _ in space.outline) / len(space.outline),
                                        sum(y for _, y in space.outline) / len(space.outline)),
            required="zone name, pictogram or pattern in addition to color", citation=wcag("1.4.1 Use of Color"),
            detail="Floor colors and sign colors are the only cue for which zone you are in (no zone names or pictograms).",
            fix=None if has_text else Fix(summary="Add zone names and pictograms to every sign and a floor legend at each entrance.",
                                          op="set", params={"sign.pictogram": True}),
        ))
        return out
