"""Double-angle plot helpers for residual cylinder (minus notation)."""

from __future__ import annotations

from app.clinical.vector_analysis import astigmatic_vector, j0_j45


def double_angle_xy(cylinder: float, axis: float | None) -> tuple[float, float]:
    """Cartesian coordinates for double-angle polar plot (2·J0, 2·J45)."""
    vec = astigmatic_vector(cylinder, axis)
    return vec.double_angle_x, vec.double_angle_y


def case_vector(cylinder: float, axis: float | None) -> dict[str, float | None]:
    j0, j45 = j0_j45(cylinder, axis)
    vec = astigmatic_vector(cylinder, axis)
    return {
        "j0": j0,
        "j45": j45,
        "x": vec.double_angle_x,
        "y": vec.double_angle_y,
        "magnitude": vec.magnitude,
    }
