"""Confidence interval helpers for ratio statistics."""

from __future__ import annotations

from math import exp, log, sqrt


def wald_log_ratio_ci(
    estimate: float,
    *,
    se: float,
    z: float = 1.96,
) -> tuple[float, float]:
    """Wald CI on the log scale, exponentiated back to the ratio scale."""
    if estimate <= 0:
        raise ValueError("estimate must be positive for a log-scale CI")
    if se < 0:
        raise ValueError("standard error must be non-negative")
    lower = exp(log(estimate) - z * se)
    upper = exp(log(estimate) + z * se)
    return lower, upper


def or_standard_error(a: float, b: float, c: float, d: float) -> float:
    """SE of log(OR) for a 2x2 table (cells already corrected if needed)."""
    return sqrt((1 / a) + (1 / b) + (1 / c) + (1 / d))
