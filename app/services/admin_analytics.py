"""Backward-compatible facade.

Prefer importing from ``app.statistics`` for new code. This module remains so
older references do not break during the Advanced Analytics refactor.
"""

from app.statistics.analytics import (
    build_advanced_analytics,
    build_distribution,
    compute_risk_factor_analytics,
    compute_surgeon_analytics,
)
from app.statistics.distribution import suggest_distribution
from app.statistics.odds_ratio import compute_odds_ratio_vs_rest

__all__ = [
    "build_advanced_analytics",
    "build_distribution",
    "compute_risk_factor_analytics",
    "compute_surgeon_analytics",
    "suggest_distribution",
    "compute_odds_ratio_vs_rest",
]
