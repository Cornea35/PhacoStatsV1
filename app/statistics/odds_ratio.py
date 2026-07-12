"""Odds ratio calculations with Haldane-Anscombe continuity correction.

Note: file is named ``odds_ratio.py`` because ``or`` is a Python keyword.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.statistics.confidence_interval import or_standard_error, wald_log_ratio_ci
from app.statistics.fisher import fisher_exact_pvalue


@dataclass(frozen=True)
class OddsRatioResult:
    odds_ratio: float | None
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    relative_risk: float | None
    absolute_risk_difference: float | None
    used_haldane_correction: bool
    comparable: bool


def _haldane_cells(a: int, b: int, c: int, d: int) -> tuple[float, float, float, float, bool]:
    cells = [float(a), float(b), float(c), float(d)]
    corrected = any(value == 0 for value in cells)
    if corrected:
        cells = [value + 0.5 for value in cells]
    return cells[0], cells[1], cells[2], cells[3], corrected


def compute_odds_ratio_vs_rest(
    exposed_events: int,
    exposed_total: int,
    other_events: int,
    other_total: int,
) -> OddsRatioResult:
    """Compare one surgeon (exposed) against all remaining surgeons pooled."""
    if exposed_total < 0 or other_total < 0 or exposed_events < 0 or other_events < 0:
        raise ValueError("counts must be non-negative")
    if exposed_events > exposed_total or other_events > other_total:
        raise ValueError("events cannot exceed totals")

    if exposed_total == 0 or other_total == 0:
        return OddsRatioResult(
            odds_ratio=None,
            ci_low=None,
            ci_high=None,
            p_value=None,
            relative_risk=None,
            absolute_risk_difference=None,
            used_haldane_correction=False,
            comparable=False,
        )

    a = exposed_events
    b = exposed_total - exposed_events
    c = other_events
    d = other_total - other_events

    aa, bb, cc, dd, corrected = _haldane_cells(a, b, c, d)
    odds_ratio = (aa * dd) / (bb * cc)
    se = or_standard_error(aa, bb, cc, dd)
    ci_low, ci_high = wald_log_ratio_ci(odds_ratio, se=se)
    p_value = fisher_exact_pvalue(a, b, c, d)

    risk_exposed = a / exposed_total
    risk_other = c / other_total
    if risk_other == 0:
        risk_other_corr = (c + 0.5) / (other_total + 1.0)
        relative_risk = risk_exposed / risk_other_corr if risk_other_corr else None
    else:
        relative_risk = risk_exposed / risk_other
    absolute_risk_difference = risk_exposed - risk_other

    return OddsRatioResult(
        odds_ratio=odds_ratio,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_value,
        relative_risk=relative_risk,
        absolute_risk_difference=absolute_risk_difference,
        used_haldane_correction=corrected,
        comparable=True,
    )
