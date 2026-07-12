"""Central refractive star scoring. Single source of truth. No PII.

overall_refractive_stars = (seq_stars + astigmatism_stars) / 2

Never use min/max/penalties for the overall score.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


class RefractiveScoringError(ValueError):
    """Invalid star combination or invariant violation."""


def calculate_seq_stars(seq: float) -> int:
    """SEQ star bands (clinical rules)."""
    if seq == 0:
        return 5
    if seq < 0:
        if -0.25 <= seq <= 0:
            return 5
        if -0.50 <= seq < -0.25:
            return 4
        if -0.75 <= seq < -0.50:
            return 3
        if -1.50 <= seq < -0.75:
            return 2
        return 1
    if 0 < seq <= 0.50:
        return 5
    if 0.50 < seq <= 0.75:
        return 4
    if 0.75 < seq <= 1.50:
        return 3
    if 1.50 < seq <= 2.00:
        return 2
    return 1


def calculate_astigmatism_stars(cylinder: float, orientation: str) -> int:
    """Astigmatism stars from |C| and orientation (minus-cylinder tables)."""
    from app.clinical.astigmatism import AstigmatismOrientation

    c = abs(float(cylinder))
    if orientation == AstigmatismOrientation.NONE.value or c == 0:
        return 5
    if orientation == AstigmatismOrientation.WTR.value:
        if 0 <= c <= 0.50:
            return 5
        if 0.50 < c <= 1.00:
            return 4
        if 1.00 < c <= 1.50:
            return 3
        if 1.50 < c <= 2.00:
            return 2
        return 1
    # ATR or Oblique
    if 0 <= c <= 0.25:
        return 5
    if 0.25 < c <= 0.50:
        return 4
    if 0.50 < c <= 1.00:
        return 3
    if 1.00 < c <= 2.00:
        return 2
    return 1


def calculate_overall_refractive_stars(
    seq_stars: int | None,
    astigmatism_stars: int | None,
) -> float | None:
    """Mean of the two component star scores. Null if either component is missing."""
    if seq_stars is None or astigmatism_stars is None:
        return None
    overall = (float(seq_stars) + float(astigmatism_stars)) / 2.0
    assert_overall_invariants(seq_stars, astigmatism_stars, overall)
    return overall


def assert_overall_invariants(
    seq_stars: int,
    astigmatism_stars: int,
    overall: float,
) -> None:
    lo = min(seq_stars, astigmatism_stars)
    hi = max(seq_stars, astigmatism_stars)
    expected = (float(seq_stars) + float(astigmatism_stars)) / 2.0
    if abs(overall - expected) > 1e-9:
        raise RefractiveScoringError(
            f"overall {overall} != mean({seq_stars},{astigmatism_stars})={expected}"
        )
    if overall < lo - 1e-9 or overall > hi + 1e-9:
        raise RefractiveScoringError(
            f"overall {overall} outside [{lo}, {hi}] for ({seq_stars}, {astigmatism_stars})"
        )
    if overall < 1.0 - 1e-9 or overall > 5.0 + 1e-9:
        raise RefractiveScoringError(f"overall {overall} outside [1, 5]")


def round_stars_display(value: float | None) -> float | None:
    """Round only for display: one decimal, half-up (3.35→3.4, 3.34→3.3)."""
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def overall_star_bin(overall: float) -> str:
    """Documented bins for distribution charts of continuous overall scores."""
    if 1.0 <= overall < 1.5:
        return "1.0–1.5"
    if 1.5 <= overall < 2.5:
        return "1.5–2.5"
    if 2.5 <= overall < 3.5:
        return "2.5–3.5"
    if 3.5 <= overall < 4.5:
        return "3.5–4.5"
    if 4.5 <= overall <= 5.0:
        return "4.5–5.0"
    return "out_of_range"


OVERALL_BIN_ORDER = ["1.0–1.5", "1.5–2.5", "2.5–3.5", "3.5–4.5", "4.5–5.0"]


def cohort_mean_stars(values: list[float]) -> float | None:
    """Mean without pre-rounding. Empty → None."""
    if not values:
        return None
    return sum(values) / len(values)


def verify_cohort_identity(
    mean_seq: float | None,
    mean_astig: float | None,
    mean_overall: float | None,
    *,
    tol: float = 1e-6,
) -> dict[str, Any]:
    """When all three means come from the same complete cases, overall ≈ (seq+astig)/2."""
    if mean_seq is None or mean_astig is None or mean_overall is None:
        return {"ok": False, "reason": "missing_mean"}
    expected = (mean_seq + mean_astig) / 2.0
    delta = abs(mean_overall - expected)
    return {
        "ok": delta <= tol,
        "expected": expected,
        "actual": mean_overall,
        "delta": delta,
    }
