"""Orchestration layer: load ORM data and apply pure statistics modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import (
    REINTERVENTION_TYPE_LABELS,
    RISK_FACTOR_CATALOG,
    ComplicationType,
    UserRole,
)
from app.models import ComplicationEvent, ReinterventionFollowUp, RiskFactor, Surgery, User
from app.statistics.distribution import (
    DistributionInput,
    DistributionRow,
    suggest_distribution,
)
from app.statistics.odds_ratio import OddsRatioResult, compute_odds_ratio_vs_rest
from app.statistics.risk import RiskFactorStat, build_risk_factor_stats


@dataclass(frozen=True)
class SurgeonAnalyticsRow:
    surgeon_id: int
    surgeon_name: str
    surgeries: int
    pcr_events: int
    pcr_rate_pct: float
    odds_ratio: float | None
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    relative_risk: float | None
    absolute_risk_difference: float | None
    smoothed_risk: float
    used_haldane_correction: bool


@dataclass(frozen=True)
class AdminSummaryCards:
    total_surgeries: int
    total_pcr: int
    global_pcr_rate_pct: float
    surgeon_count: int
    average_odds_ratio: float | None
    top_risk_factor: str | None
    lowest_pcr_surgeon: str | None
    highest_pcr_surgeon: str | None


@dataclass(frozen=True)
class ReinterventionTypeStat:
    code: str
    label: str
    count: int


@dataclass(frozen=True)
class AdvancedAnalyticsBundle:
    summary: AdminSummaryCards
    surgeon_rows: list[SurgeonAnalyticsRow]
    distribution: list[DistributionRow]
    risk_factors: list[RiskFactorStat]
    reintervention_types: list[ReinterventionTypeStat]
    planned_cases: int
    max_difference: int


def _active_surgeons(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.role == UserRole.SURGEON.value, User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )


def _apply_scope_filters(query, *, institution_id: str | None = None, center_id: int | None = None):
    if institution_id:
        return query.filter(Surgery.institution_id == institution_id)
    if center_id is not None:
        return query.filter(Surgery.center_id == center_id)
    return query


def _apply_date_filters(query, date_from: date | None, date_to: date | None):
    if date_from is not None:
        query = query.filter(Surgery.surgery_date >= date_from)
    if date_to is not None:
        query = query.filter(Surgery.surgery_date <= date_to)
    return query


def _surgeon_case_counts(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    institution_id: str | None = None,
    center_id: int | None = None,
) -> list[tuple[User, int, int]]:
    surgeons = _active_surgeons(db)
    rows: list[tuple[User, int, int]] = []
    for surgeon in surgeons:
        base = _apply_date_filters(
            db.query(Surgery).filter(Surgery.surgeon_id == surgeon.id),
            date_from,
            date_to,
        )
        base = _apply_scope_filters(base, institution_id=institution_id, center_id=center_id)
        total = base.count()
        pcr = (
            base.join(ComplicationEvent, ComplicationEvent.surgery_id == Surgery.id)
            .filter(
                ComplicationEvent.occurred.is_(True),
                ComplicationEvent.complication_type == ComplicationType.PCR.value,
            )
            .count()
        )
        rows.append((surgeon, total, pcr))
    return rows


def compute_surgeon_analytics(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    institution_id: str | None = None,
    center_id: int | None = None,
) -> list[SurgeonAnalyticsRow]:
    rows = _surgeon_case_counts(
        db,
        date_from=date_from,
        date_to=date_to,
        institution_id=institution_id,
        center_id=center_id,
    )
    grand_total = sum(total for _, total, _ in rows)
    grand_pcr = sum(pcr for _, _, pcr in rows)

    result: list[SurgeonAnalyticsRow] = []
    for surgeon, total, pcr in rows:
        other_total = grand_total - total
        other_pcr = grand_pcr - pcr
        stats: OddsRatioResult = compute_odds_ratio_vs_rest(
            pcr, total, other_pcr, other_total
        )
        smoothed = (pcr + 1) / (total + 20)
        result.append(
            SurgeonAnalyticsRow(
                surgeon_id=surgeon.id,
                surgeon_name=surgeon.full_name,
                surgeries=total,
                pcr_events=pcr,
                pcr_rate_pct=round((pcr / total) * 100, 2) if total else 0.0,
                odds_ratio=round(stats.odds_ratio, 4) if stats.odds_ratio is not None else None,
                ci_low=round(stats.ci_low, 4) if stats.ci_low is not None else None,
                ci_high=round(stats.ci_high, 4) if stats.ci_high is not None else None,
                p_value=round(stats.p_value, 6) if stats.p_value is not None else None,
                relative_risk=round(stats.relative_risk, 4) if stats.relative_risk is not None else None,
                absolute_risk_difference=(
                    round(stats.absolute_risk_difference, 4)
                    if stats.absolute_risk_difference is not None
                    else None
                ),
                smoothed_risk=smoothed,
                used_haldane_correction=stats.used_haldane_correction,
            )
        )
    return sorted(result, key=lambda item: item.smoothed_risk)


def compute_risk_factor_analytics(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    top_n: int = 10,
    institution_id: str | None = None,
    center_id: int | None = None,
) -> list[RiskFactorStat]:
    query = db.query(Surgery.id).join(User, User.id == Surgery.surgeon_id).filter(
        User.role == UserRole.SURGEON.value,
        User.is_active.is_(True),
    )
    query = _apply_date_filters(query, date_from, date_to)
    query = _apply_scope_filters(query, institution_id=institution_id, center_id=center_id)
    surgery_ids = [row[0] for row in query.all()]
    total = len(surgery_ids)
    if not surgery_ids:
        return []

    grouped = (
        db.query(RiskFactor.code, func.count(func.distinct(RiskFactor.surgery_id)))
        .filter(RiskFactor.surgery_id.in_(surgery_ids))
        .group_by(RiskFactor.code)
        .all()
    )
    counts = {code: int(count) for code, count in grouped}
    return build_risk_factor_stats(
        counts,
        total_surgeries=total,
        catalog=RISK_FACTOR_CATALOG,
        top_n=top_n,
    )


def build_distribution(
    surgeon_rows: list[SurgeonAnalyticsRow],
    *,
    planned_cases: int,
    max_difference: int,
) -> list[DistributionRow]:
    inputs = [
        DistributionInput(
            surgeon_id=row.surgeon_id,
            surgeon_name=row.surgeon_name,
            surgeries=row.surgeries,
            pcr_events=row.pcr_events,
        )
        for row in surgeon_rows
    ]
    return suggest_distribution(
        inputs,
        total_cases=planned_cases,
        max_difference=max_difference,
    )


def build_summary_cards(
    surgeon_rows: list[SurgeonAnalyticsRow],
    risk_factors: list[RiskFactorStat],
) -> AdminSummaryCards:
    total_surgeries = sum(row.surgeries for row in surgeon_rows)
    total_pcr = sum(row.pcr_events for row in surgeon_rows)
    ors = [row.odds_ratio for row in surgeon_rows if row.odds_ratio is not None]
    avg_or = round(sum(ors) / len(ors), 4) if ors else None

    with_cases = [row for row in surgeon_rows if row.surgeries > 0]
    lowest = min(with_cases, key=lambda r: (r.pcr_rate_pct, r.smoothed_risk), default=None)
    highest = max(with_cases, key=lambda r: (r.pcr_rate_pct, r.smoothed_risk), default=None)

    return AdminSummaryCards(
        total_surgeries=total_surgeries,
        total_pcr=total_pcr,
        global_pcr_rate_pct=round((total_pcr / total_surgeries) * 100, 2) if total_surgeries else 0.0,
        surgeon_count=len(surgeon_rows),
        average_odds_ratio=avg_or,
        top_risk_factor=risk_factors[0].label if risk_factors else None,
        lowest_pcr_surgeon=lowest.surgeon_name if lowest else None,
        highest_pcr_surgeon=highest.surgeon_name if highest else None,
    )


def compute_reintervention_type_analytics(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    institution_id: str | None = None,
    center_id: int | None = None,
) -> list[ReinterventionTypeStat]:
    """Count non-voided reintervention follow-ups by general type in the period."""
    q = (
        db.query(
            ReinterventionFollowUp.reintervention_type,
            func.count(ReinterventionFollowUp.id),
        )
        .join(Surgery, Surgery.id == ReinterventionFollowUp.surgery_id)
        .filter(ReinterventionFollowUp.is_voided.is_(False))
        .group_by(ReinterventionFollowUp.reintervention_type)
    )
    q = _apply_date_filters(q, date_from, date_to)
    q = _apply_scope_filters(q, institution_id=institution_id, center_id=center_id)
    rows = q.all()
    counts = {code or "unspecified": int(count) for code, count in rows}
    # Include all catalog types (0 if absent) so admin sees full breakdown
    result: list[ReinterventionTypeStat] = []
    for code, label in REINTERVENTION_TYPE_LABELS.items():
        result.append(
            ReinterventionTypeStat(
                code=code,
                label=label,
                count=counts.get(code, 0),
            )
        )
    # Any unexpected codes
    for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if code not in REINTERVENTION_TYPE_LABELS:
            result.append(
                ReinterventionTypeStat(
                    code=code,
                    label=code.replace("_", " ").title(),
                    count=count,
                )
            )
    result.sort(key=lambda row: (-row.count, row.label))
    return result


def build_advanced_analytics(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    planned_cases: int = 20,
    max_difference: int = 3,
    institution_id: str | None = None,
    center_id: int | None = None,
) -> AdvancedAnalyticsBundle:
    surgeon_rows = compute_surgeon_analytics(
        db,
        date_from=date_from,
        date_to=date_to,
        institution_id=institution_id,
        center_id=center_id,
    )
    risk_factors = compute_risk_factor_analytics(
        db,
        date_from=date_from,
        date_to=date_to,
        institution_id=institution_id,
        center_id=center_id,
    )
    reintervention_types = compute_reintervention_type_analytics(
        db,
        date_from=date_from,
        date_to=date_to,
        institution_id=institution_id,
        center_id=center_id,
    )
    distribution = build_distribution(
        surgeon_rows,
        planned_cases=planned_cases,
        max_difference=max_difference,
    )
    summary = build_summary_cards(surgeon_rows, risk_factors)
    return AdvancedAnalyticsBundle(
        summary=summary,
        surgeon_rows=surgeon_rows,
        distribution=distribution,
        risk_factors=risk_factors,
        reintervention_types=reintervention_types,
        planned_cases=planned_cases,
        max_difference=max_difference,
    )
