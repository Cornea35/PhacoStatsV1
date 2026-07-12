"""Astigmatism orientation and negative-cylinder conventions. No PII.

Platform-wide rule: cylinder is ALWAYS ≤ 0 (minus-cylinder notation).

Orientation (minus cylinder):
  WTR:     0–30° or 150–180°
  ATR:     60–120°
  Oblique: 31–59° or 121–149°
  None:    cylinder == 0
"""

from __future__ import annotations

from enum import Enum


class AstigmatismOrientation(str, Enum):
    WTR = "wtr"
    ATR = "atr"
    OBLIQUE = "oblique"
    NONE = "none"


ORIENTATION_LABELS = {
    AstigmatismOrientation.WTR.value: "WTR (a favor de la regla)",
    AstigmatismOrientation.ATR.value: "ATR (en contra de la regla)",
    AstigmatismOrientation.OBLIQUE.value: "Oblicuo",
    AstigmatismOrientation.NONE.value: "Ninguno",
}


class CylinderConventionError(ValueError):
    """Raised when a positive cylinder is supplied."""


def cylinder_magnitude(cylinder: float) -> float:
    """Absolute cylinder power (D)."""
    return round(abs(cylinder), 3)


def require_negative_cylinder(cylinder: float) -> float:
    """Validate minus-cylinder notation (cylinder ≤ 0)."""
    if cylinder > 1e-9:
        raise CylinderConventionError(
            "Solo se admite notación de cilindro negativo (cilindro ≤ 0)."
        )
    return float(cylinder)


def normalize_axis(axis: float) -> float:
    """Normalize axis to [0, 180]."""
    a = float(axis) % 180.0
    if a < 0:
        a += 180.0
    # 180 is equivalent to 0 for display; keep 180 when exactly 180 input edge
    if abs(a) < 1e-9:
        return 0.0
    return round(a, 3)


def classify_orientation(cylinder: float, axis: float | None) -> str:
    """Single platform definition for WTR/ATR/oblique (minus cylinder)."""
    if abs(cylinder) < 1e-9:
        return AstigmatismOrientation.NONE.value
    if axis is None:
        raise ValueError("axis is required when cylinder is non-zero")
    if not (0 <= axis <= 180):
        raise ValueError("axis must be between 0 and 180")

    # Minus-cylinder clinical definition
    if 0 <= axis <= 30 or 150 <= axis <= 180:
        return AstigmatismOrientation.WTR.value
    if 60 <= axis <= 120:
        return AstigmatismOrientation.ATR.value
    # 31–59 or 121–149
    return AstigmatismOrientation.OBLIQUE.value


def plus_to_minus_cylinder(
    sphere: float,
    cylinder: float,
    axis: float | None,
) -> tuple[float, float, float | None]:
    """Convert plus-cylinder refraction to minus-cylinder notation.

    new_sphere = sphere + cylinder
    new_cylinder = -cylinder
    new_axis = axis + 90; if > 180 subtract 180
    """
    if abs(cylinder) < 1e-9:
        return float(sphere), 0.0, None
    if cylinder <= 0:
        # Already minus (or plano cyl)
        ax = None if axis is None else normalize_axis(axis)
        return float(sphere), float(cylinder), ax

    new_sphere = float(sphere) + float(cylinder)
    new_cylinder = -float(cylinder)
    if axis is None:
        raise ValueError("axis is required to convert plus cylinder")
    new_axis = float(axis) + 90.0
    if new_axis > 180.0:
        new_axis -= 180.0
    return round(new_sphere, 3), round(new_cylinder, 3), normalize_axis(new_axis)
