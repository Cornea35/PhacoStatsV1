"""Dashboard aggregation queries for PhacoStats KPIs and charts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.constants import COMPLICATION_TYPE_LABELS, RISK_FACTOR_CATALOG, SURGICAL_STAGE_LABELS
from app.models import ComplicationEvent, RiskFactor, Surgery, User
from app.statistics.risk import build_risk_factor_stats


@dataclass
class DashboardStats:
    total_surgeries: int
    total_complications: int
    complication_rate_pct: float
    total_pcr: int
    monthly_labels: list[str]
    monthly_surgeries: list[int]
    monthly_complications: list[int]
    surgeon_labels: list[str]
    surgeon_totals: list[int]
    surgeon_complications: list[int]
    stage_labels: list[str]
    stage_counts: list[int]
    type_labels: list[str]
    type_counts: list[int]
    risk_labels: list[str]
    risk_counts: list[int]
    risk_pct: list[float]


def compute_dashboard(
    db: Session,
    *,
    surgeon_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    top_risk_n: int = 10,
) -> DashboardStats:
    base = db.query(Surgery.id)
    if surgeon_id is not None:
        base = base.filter(Surgery.surgeon_id == surgeon_id)
    if date_from is not None:
        base = base.filter(Surgery.surgery_date >= date_from)
    if date_to is not None:
        base = base.filter(Surgery.surgery_date <= date_to)
    surgery_ids = [row[0] for row in base.all()]

    empty = DashboardStats(
        total_surgeries=0,
        total_complications=0,
        complication_rate_pct=0.0,
        total_pcr=0,
        monthly_labels=[],
        monthly_surgeries=[],
        monthly_complications=[],
        surgeon_labels=[],
        surgeon_totals=[],
        surgeon_complications=[],
        stage_labels=[],
        stage_counts=[],
        type_labels=[],
        type_counts=[],
        risk_labels=[],
        risk_counts=[],
        risk_pct=[],
    )
    total = len(surgery_ids)
    if total == 0:
        return empty

    complication_count = (
        db.query(func.count(ComplicationEvent.id))
        .filter(ComplicationEvent.surgery_id.in_(surgery_ids), ComplicationEvent.occurred.is_(True))
        .scalar()
        or 0
    )
    pcr_count = (
        db.query(func.count(ComplicationEvent.id))
        .filter(
            ComplicationEvent.surgery_id.in_(surgery_ids),
            ComplicationEvent.occurred.is_(True),
            ComplicationEvent.complication_type == "pcr",
        )
        .scalar()
        or 0
    )
    rate = round((complication_count / total) * 100, 2) if total else 0.0

    month_expr = func.strftime("%Y-%m", Surgery.surgery_date)
    monthly_rows = (
        db.query(
            month_expr.label("ym"),
            func.count(Surgery.id).label("total"),
            func.sum(case((ComplicationEvent.occurred.is_(True), 1), else_=0)).label("comps"),
        )
        .outerjoin(ComplicationEvent, ComplicationEvent.surgery_id == Surgery.id)
        .filter(Surgery.id.in_(surgery_ids))
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )

    surgeon_rows = (
        db.query(
            User.full_name,
            func.count(Surgery.id).label("total"),
            func.sum(case((ComplicationEvent.occurred.is_(True), 1), else_=0)).label("comps"),
        )
        .join(User, User.id == Surgery.surgeon_id)
        .outerjoin(ComplicationEvent, ComplicationEvent.surgery_id == Surgery.id)
        .filter(Surgery.id.in_(surgery_ids))
        .group_by(User.id, User.full_name)
        .order_by(func.count(Surgery.id).desc())
        .all()
    )

    stage_rows = (
        db.query(ComplicationEvent.surgical_stage, func.count(ComplicationEvent.id))
        .filter(ComplicationEvent.surgery_id.in_(surgery_ids), ComplicationEvent.occurred.is_(True))
        .group_by(ComplicationEvent.surgical_stage)
        .all()
    )

    type_rows = (
        db.query(ComplicationEvent.complication_type, func.count(ComplicationEvent.id))
        .filter(ComplicationEvent.surgery_id.in_(surgery_ids), ComplicationEvent.occurred.is_(True))
        .group_by(ComplicationEvent.complication_type)
        .all()
    )

    risk_rows = (
        db.query(RiskFactor.code, func.count(func.distinct(RiskFactor.surgery_id)))
        .filter(RiskFactor.surgery_id.in_(surgery_ids))
        .group_by(RiskFactor.code)
        .all()
    )
    risk_stats = build_risk_factor_stats(
        {code: int(count) for code, count in risk_rows},
        total_surgeries=total,
        catalog=RISK_FACTOR_CATALOG,
        top_n=top_risk_n,
    )

    return DashboardStats(
        total_surgeries=total,
        total_complications=int(complication_count),
        complication_rate_pct=rate,
        total_pcr=int(pcr_count),
        monthly_labels=[r.ym for r in monthly_rows],
        monthly_surgeries=[int(r.total) for r in monthly_rows],
        monthly_complications=[int(r.comps or 0) for r in monthly_rows],
        surgeon_labels=[r.full_name for r in surgeon_rows],
        surgeon_totals=[int(r.total) for r in surgeon_rows],
        surgeon_complications=[int(r.comps or 0) for r in surgeon_rows],
        stage_labels=[
            SURGICAL_STAGE_LABELS.get(code or "other", code or "Otra") for code, _ in stage_rows
        ],
        stage_counts=[int(count) for _, count in stage_rows],
        type_labels=[
            COMPLICATION_TYPE_LABELS.get(code or "other", code or "Otro") for code, _ in type_rows
        ],
        type_counts=[int(count) for _, count in type_rows],
        risk_labels=[r.label for r in risk_stats],
        risk_counts=[r.cases for r in risk_stats],
        risk_pct=[r.prevalence_pct for r in risk_stats],
    )
