"""Risk-factor frequency analytics (pure + catalog aware)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskFactorStat:
    code: str
    label: str
    cases: int
    prevalence_pct: float
    cumulative_pct: float


def build_risk_factor_stats(
    counts_by_code: dict[str, int],
    *,
    total_surgeries: int,
    catalog: dict[str, str],
    top_n: int = 10,
) -> list[RiskFactorStat]:
    """Return top-N risk factors sorted by absolute frequency (Pareto-ready)."""
    if total_surgeries < 0:
        raise ValueError("total_surgeries must be non-negative")
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    if total_surgeries == 0:
        return []

    ordered = sorted(counts_by_code.items(), key=lambda item: (-item[1], item[0]))
    ordered = ordered[:top_n]
    running = 0
    total_factor_cases = sum(count for _, count in ordered) or 1
    result: list[RiskFactorStat] = []
    for code, count in ordered:
        running += count
        result.append(
            RiskFactorStat(
                code=code,
                label=catalog.get(code, code.replace("_", " ").title()),
                cases=int(count),
                prevalence_pct=round((count / total_surgeries) * 100, 2),
                cumulative_pct=round((running / total_factor_cases) * 100, 2),
            )
        )
    return result
