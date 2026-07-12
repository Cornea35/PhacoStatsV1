"""Refractive evaluation: SEQ, stars, orchestration. Minus-cylinder only. No PII."""

from __future__ import annotations

from dataclasses import dataclass

from app.clinical.astigmatism import (
    ORIENTATION_LABELS,
    AstigmatismOrientation,
    CylinderConventionError,
    classify_orientation,
    cylinder_magnitude,
    require_negative_cylinder,
)
from app.clinical.refractive_scoring import (
    calculate_astigmatism_stars,
    calculate_overall_refractive_stars,
    calculate_seq_stars,
)
from app.clinical.vector_analysis import astigmatic_vector


@dataclass(frozen=True)
class RefractionResult:
    spherical_equivalent: float
    residual_astigmatism: float
    astigmatism_orientation: str
    spherical_equivalent_stars: int
    astigmatism_stars: int
    overall_refractive_stars: float | None
    j0: float
    j45: float
    double_angle_x: float
    double_angle_y: float


def spherical_equivalent(sphere: float, cylinder: float) -> float:
    """SEQ = sphere + cylinder/2 (signed cylinder; do not abs)."""
    return round(float(sphere) + (float(cylinder) / 2.0), 3)


def residual_astigmatism(cylinder: float) -> float:
    return cylinder_magnitude(cylinder)


def seq_stars(seq: float) -> int:
    return calculate_seq_stars(seq)


def astigmatism_stars(cylinder: float, orientation: str) -> int:
    return calculate_astigmatism_stars(cylinder, orientation)


def evaluate_refraction(
    sphere: float,
    cylinder: float,
    axis: float | None,
    *,
    enforce_negative: bool = True,
) -> RefractionResult:
    """Evaluate refraction in minus-cylinder notation."""
    if enforce_negative:
        cylinder = require_negative_cylinder(cylinder)

    if abs(cylinder) < 1e-9:
        axis = None
        cylinder = 0.0
    elif axis is None:
        raise ValueError("axis is required when cylinder != 0")
    elif not (0 <= axis <= 180):
        raise ValueError("axis must be between 0 and 180")

    seq = spherical_equivalent(sphere, cylinder)
    resid = residual_astigmatism(cylinder)
    orientation = classify_orientation(cylinder, axis)
    s_stars = calculate_seq_stars(seq)
    a_stars = calculate_astigmatism_stars(cylinder, orientation)
    overall = calculate_overall_refractive_stars(s_stars, a_stars)
    vec = astigmatic_vector(cylinder, axis)
    return RefractionResult(
        spherical_equivalent=seq,
        residual_astigmatism=resid,
        astigmatism_orientation=orientation,
        spherical_equivalent_stars=s_stars,
        astigmatism_stars=a_stars,
        overall_refractive_stars=overall,
        j0=vec.j0,
        j45=vec.j45,
        double_angle_x=vec.double_angle_x,
        double_angle_y=vec.double_angle_y,
    )


__all__ = [
    "AstigmatismOrientation",
    "ORIENTATION_LABELS",
    "CylinderConventionError",
    "RefractionResult",
    "spherical_equivalent",
    "residual_astigmatism",
    "seq_stars",
    "astigmatism_stars",
    "evaluate_refraction",
    "classify_orientation",
    "require_negative_cylinder",
    "cylinder_magnitude",
]
