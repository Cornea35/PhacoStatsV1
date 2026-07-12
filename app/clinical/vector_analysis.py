"""Jackson cross-cylinder vector components (J0, J45). No PII.

Uses signed cylinder (platform: cylinder ≤ 0):

    J0  = -(C/2) * cos(2θ)
    J45 = -(C/2) * sin(2θ)

Double-angle Cartesian plot coordinates:

    x = 2 * J0
    y = 2 * J45

which equals (|C|·cos(2θ), |C|·sin(2θ)) when C ≤ 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin, sqrt


@dataclass(frozen=True)
class AstigmaticVector:
    j0: float
    j45: float
    double_angle_x: float
    double_angle_y: float
    magnitude: float  # |C| = 2 * sqrt(J0^2 + J45^2)


def j0_j45(cylinder: float, axis: float | None) -> tuple[float, float]:
    """Return (J0, J45) for a cylinder/axis pair."""
    if abs(cylinder) < 1e-9 or axis is None:
        return 0.0, 0.0
    theta = radians(2.0 * float(axis))
    half = -float(cylinder) / 2.0
    j0 = round(half * cos(theta), 6)
    j45 = round(half * sin(theta), 6)
    return j0, j45


def astigmatic_vector(cylinder: float, axis: float | None) -> AstigmaticVector:
    j0, j45 = j0_j45(cylinder, axis)
    x = round(2.0 * j0, 4)
    y = round(2.0 * j45, 4)
    mag = round(2.0 * sqrt(j0 * j0 + j45 * j45), 4)
    return AstigmaticVector(
        j0=j0,
        j45=j45,
        double_angle_x=x,
        double_angle_y=y,
        magnitude=mag,
    )


def axis_from_j0_j45(j0: float, j45: float) -> float | None:
    """Mean refractive cylinder axis (0–180) from J0/J45. Not a simple mean of axes."""
    if abs(j0) < 1e-12 and abs(j45) < 1e-12:
        return None
    # θ = ½ atan2(J45, J0); map to [0, 180)
    ang = 0.5 * degrees(atan2(j45, j0))
    if ang < 0:
        ang += 180.0
    if ang >= 180.0:
        ang -= 180.0
    return round(ang, 3)


def vector_magnitude_from_j(j0: float, j45: float) -> float:
    return round(2.0 * sqrt(j0 * j0 + j45 * j45), 4)
