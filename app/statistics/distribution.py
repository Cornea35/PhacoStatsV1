"""Surgical case distribution planner."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistributionInput:
    surgeon_id: int
    surgeon_name: str
    surgeries: int
    pcr_events: int


@dataclass(frozen=True)
class DistributionRow:
    surgeon_id: int
    surgeon_name: str
    pcr_events: int
    smoothed_risk: float
    smoothed_risk_pct: float
    weight: float
    suggested_cases: int


def smoothed_risk(pcr_events: int, surgeries: int) -> float:
    """Beta-binomial style smoothing: (RCP+1)/(n+20)."""
    if pcr_events < 0 or surgeries < 0:
        raise ValueError("counts must be non-negative")
    if pcr_events > surgeries:
        raise ValueError("pcr_events cannot exceed surgeries")
    return (pcr_events + 1) / (surgeries + 20)


def _largest_remainder(total_cases: int, shares: list[float]) -> list[int]:
    raw = [total_cases * share for share in shares]
    allocated = [int(value) for value in raw]
    remaining = total_cases - sum(allocated)
    order = sorted(
        range(len(raw)),
        key=lambda idx: (raw[idx] - allocated[idx], shares[idx]),
        reverse=True,
    )
    for idx in order[:remaining]:
        allocated[idx] += 1
    return allocated


def suggest_distribution(
    surgeons: list[DistributionInput],
    *,
    total_cases: int,
    max_difference: int = 3,
) -> list[DistributionRow]:
    """Inverse-risk allocation with max-gap constraint and exact total."""
    if total_cases < 0:
        raise ValueError("total_cases must be non-negative")
    if max_difference < 0:
        raise ValueError("max_difference must be non-negative")
    if not surgeons:
        return []

    risks = [smoothed_risk(item.pcr_events, item.surgeries) for item in surgeons]
    inverse = [1 / max(risk, 1e-9) for risk in risks]
    denom = sum(inverse)
    shares = [weight / denom for weight in inverse]
    allocation = _largest_remainder(total_cases, shares)

    safety = len(surgeons) * (total_cases + 1) + 10
    while allocation and max(allocation) - min(allocation) > max_difference and safety > 0:
        safety -= 1
        max_value = max(allocation)
        min_value = min(allocation)
        gap_before = max_value - min_value
        donors = [idx for idx, value in enumerate(allocation) if value == max_value]
        recipients = [idx for idx, value in enumerate(allocation) if value == min_value]
        donor = min(donors, key=lambda idx: risks[idx])
        recipient = max(recipients, key=lambda idx: risks[idx])
        if donor == recipient:
            break
        allocation[donor] -= 1
        allocation[recipient] += 1
        gap_after = max(allocation) - min(allocation)
        if gap_after >= gap_before:
            allocation[donor] += 1
            allocation[recipient] -= 1
            break

    weight_total = sum(inverse) or 1.0
    rows: list[DistributionRow] = []
    for idx, item in enumerate(surgeons):
        rows.append(
            DistributionRow(
                surgeon_id=item.surgeon_id,
                surgeon_name=item.surgeon_name,
                pcr_events=item.pcr_events,
                smoothed_risk=risks[idx],
                smoothed_risk_pct=round(risks[idx] * 100, 2),
                weight=round(inverse[idx] / weight_total, 6),
                suggested_cases=allocation[idx],
            )
        )
    return rows
