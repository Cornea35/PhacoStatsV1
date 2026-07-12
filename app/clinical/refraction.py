"""Backward-compatible re-exports. Prefer app.clinical.refractive / astigmatism. """

from app.clinical.astigmatism import (
    ORIENTATION_LABELS,
    AstigmatismOrientation,
    CylinderConventionError,
    classify_orientation,
    cylinder_magnitude,
    require_negative_cylinder,
)
from app.clinical.refractive import (
    RefractionResult,
    astigmatism_stars,
    evaluate_refraction,
    residual_astigmatism,
    seq_stars,
    spherical_equivalent,
)
from app.statistics.double_angle import double_angle_xy

__all__ = [
    "AstigmatismOrientation",
    "ORIENTATION_LABELS",
    "CylinderConventionError",
    "RefractionResult",
    "spherical_equivalent",
    "residual_astigmatism",
    "classify_orientation",
    "seq_stars",
    "astigmatism_stars",
    "double_angle_xy",
    "evaluate_refraction",
    "require_negative_cylinder",
    "cylinder_magnitude",
]
