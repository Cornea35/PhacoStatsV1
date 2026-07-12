"""Operational dashboard for coordinators (counts only, no surgeon comparisons)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.constants import ReinterventionStatus
from app.models import ComplicationEvent, ReinterventionFollowUp, Surgery


@dataclass
class OpsDashboardStats:
    total_surgeries: int
    with_complication: int
    without_complication: int
    reintervention_pending: int
    reintervention_scheduled: int
    reintervention_completed: int
    incomplete_records: int
    pending_tasks: list[dict]


def compute_ops_dashboard(
    db: Session,
    *,
    institution_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> OpsDashboardStats:
    q = db.query(Surgery)
    if institution_id:
        q = q.filter(Surgery.institution_id == institution_id)
    if date_from is not None:
        q = q.filter(Surgery.surgery_date >= date_from)
    if date_to is not None:
        q = q.filter(Surgery.surgery_date <= date_to)

    surgery_ids = [row[0] for row in q.with_entities(Surgery.id).all()]
    total = len(surgery_ids)
    if total == 0:
        return OpsDashboardStats(
            total_surgeries=0,
            with_complication=0,
            without_complication=0,
            reintervention_pending=0,
            reintervention_scheduled=0,
            reintervention_completed=0,
            incomplete_records=0,
            pending_tasks=[],
        )

    with_comp = (
        db.query(func.count(ComplicationEvent.id))
        .filter(
            ComplicationEvent.surgery_id.in_(surgery_ids),
            ComplicationEvent.occurred.is_(True),
        )
        .scalar()
        or 0
    )
    without_comp = total - int(with_comp)

    def _count_status(status: str) -> int:
        return (
            db.query(func.count(ReinterventionFollowUp.id))
            .join(Surgery, Surgery.id == ReinterventionFollowUp.surgery_id)
            .filter(
                ReinterventionFollowUp.surgery_id.in_(surgery_ids),
                ReinterventionFollowUp.is_voided.is_(False),
                ReinterventionFollowUp.status == status,
            )
            .scalar()
            or 0
        )

    pending = int(_count_status(ReinterventionStatus.PENDING.value))
    scheduled = int(_count_status(ReinterventionStatus.SCHEDULED.value))
    completed = int(_count_status(ReinterventionStatus.COMPLETED.value))

    # Incomplete: required=yes or pending status without date/notes, or surgery with complication and no reintervention record
    incomplete = (
        db.query(func.count(ReinterventionFollowUp.id))
        .filter(
            ReinterventionFollowUp.surgery_id.in_(surgery_ids),
            ReinterventionFollowUp.is_voided.is_(False),
            ReinterventionFollowUp.status.in_(
                [ReinterventionStatus.PENDING.value, ReinterventionStatus.SCHEDULED.value]
            ),
            ReinterventionFollowUp.notes.is_(None),
        )
        .scalar()
        or 0
    )

    task_rows = (
        db.query(ReinterventionFollowUp)
        .options(
            joinedload(ReinterventionFollowUp.surgery).joinedload(Surgery.surgeon),
        )
        .filter(
            ReinterventionFollowUp.surgery_id.in_(surgery_ids),
            ReinterventionFollowUp.is_voided.is_(False),
            ReinterventionFollowUp.status.in_(
                [ReinterventionStatus.PENDING.value, ReinterventionStatus.SCHEDULED.value]
            ),
        )
        .order_by(ReinterventionFollowUp.created_at.asc())
        .limit(25)
        .all()
    )
    pending_tasks = [
        {
            "id": fu.id,
            "case_code": fu.surgery.case_code,
            "surgeon": fu.surgery.surgeon.full_name if fu.surgery.surgeon else "—",
            "status": fu.status,
            "surgery_id": fu.surgery_id,
        }
        for fu in task_rows
    ]

    return OpsDashboardStats(
        total_surgeries=total,
        with_complication=int(with_comp),
        without_complication=without_comp,
        reintervention_pending=pending,
        reintervention_scheduled=scheduled,
        reintervention_completed=completed,
        incomplete_records=int(incomplete),
        pending_tasks=pending_tasks,
    )
