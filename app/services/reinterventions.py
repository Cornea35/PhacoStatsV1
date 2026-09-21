"""Reintervention follow-up service (ops tracking + audit)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.constants import (
    DEFAULT_INSTITUTION_CODE,
    ReinterventionRequired,
    ReinterventionStatus,
    ReinterventionType,
    RetinaRelated,
)
from app.models import ReinterventionFollowUp, ReinterventionRevision, Surgery, User


class ReinterventionValidationError(ValueError):
    """Invalid reintervention form data."""


def _snapshot(fu: ReinterventionFollowUp) -> dict[str, Any]:
    return {
        "id": fu.id,
        "surgery_id": fu.surgery_id,
        "reintervention_required": fu.reintervention_required,
        "reintervention_date": fu.reintervention_date.isoformat() if fu.reintervention_date else None,
        "reintervention_type": fu.reintervention_type,
        "retina_related": fu.retina_related,
        "status": fu.status,
        "notes": fu.notes,
        "is_voided": fu.is_voided,
        "void_reason": fu.void_reason,
    }


def _add_revision(
    db: Session,
    fu: ReinterventionFollowUp,
    *,
    action: str,
    changed_by_id: int,
    previous: dict[str, Any] | None,
    new: dict[str, Any],
) -> None:
    db.add(
        ReinterventionRevision(
            follow_up_id=fu.id,
            action=action,
            previous_json=json.dumps(previous, ensure_ascii=False) if previous else None,
            new_json=json.dumps(new, ensure_ascii=False),
            changed_by_id=changed_by_id,
        )
    )


def _validate_payload(
    *,
    surgery: Surgery,
    reintervention_required: str,
    reintervention_date: date | None,
    reintervention_type: str,
    retina_related: str,
    status: str,
    notes: str | None,
) -> None:
    if reintervention_required not in {r.value for r in ReinterventionRequired}:
        raise ReinterventionValidationError("Valor inválido para reintervención requerida.")
    if status not in {s.value for s in ReinterventionStatus}:
        raise ReinterventionValidationError("Estado de seguimiento inválido.")
    if reintervention_type not in {t.value for t in ReinterventionType}:
        raise ReinterventionValidationError("Tipo de reintervención inválido.")
    if retina_related not in {r.value for r in RetinaRelated}:
        raise ReinterventionValidationError("Valor inválido para relación con retina.")

    if reintervention_required == ReinterventionRequired.NO.value:
        # date may be null
        pass
    if status == ReinterventionStatus.COMPLETED.value and reintervention_date is None:
        raise ReinterventionValidationError(
            "Si el estado es Completada, indique la fecha de reintervención."
        )
    if reintervention_date is not None and reintervention_date < surgery.surgery_date:
        raise ReinterventionValidationError(
            "La fecha de reintervención no puede ser anterior a la cirugía."
        )
    if reintervention_required == ReinterventionRequired.YES.value and not (notes or "").strip():
        # Encourage a note when required=yes, but allow pending/scheduled without long notes
        if status == ReinterventionStatus.COMPLETED.value and not (notes or "").strip():
            raise ReinterventionValidationError(
                "Indique notas administrativas del procedimiento realizado."
            )


def _sync_surgery_legacy(surgery: Surgery, active: ReinterventionFollowUp | None) -> None:
    """Keep legacy Surgery.reintervention_* columns in sync for older filters."""
    if active is None:
        surgery.reintervention_needed = False
        surgery.reintervention_procedure_notes = None
        return
    surgery.reintervention_needed = active.reintervention_required == ReinterventionRequired.YES.value
    surgery.reintervention_procedure_notes = active.notes


def create_reintervention(
    db: Session,
    surgery: Surgery,
    *,
    actor: User,
    reintervention_required: str,
    reintervention_date: date | None,
    reintervention_type: str,
    retina_related: str,
    status: str,
    notes: str | None,
) -> ReinterventionFollowUp:
    _validate_payload(
        surgery=surgery,
        reintervention_required=reintervention_required,
        reintervention_date=reintervention_date,
        reintervention_type=reintervention_type,
        retina_related=retina_related,
        status=status,
        notes=notes,
    )
    fu = ReinterventionFollowUp(
        surgery_id=surgery.id,
        reintervention_required=reintervention_required,
        reintervention_date=reintervention_date,
        reintervention_type=reintervention_type or ReinterventionType.UNSPECIFIED.value,
        retina_related=retina_related or RetinaRelated.UNKNOWN.value,
        status=status,
        notes=(notes or "").strip() or None,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    db.add(fu)
    db.flush()
    snap = _snapshot(fu)
    _add_revision(db, fu, action="created", changed_by_id=actor.id, previous=None, new=snap)
    _sync_surgery_legacy(surgery, fu)
    db.commit()
    db.refresh(fu)
    return fu


def update_reintervention(
    db: Session,
    fu: ReinterventionFollowUp,
    *,
    actor: User,
    reintervention_required: str,
    reintervention_date: date | None,
    reintervention_type: str,
    retina_related: str,
    status: str,
    notes: str | None,
) -> ReinterventionFollowUp:
    if fu.is_voided:
        raise ReinterventionValidationError("No se puede editar un seguimiento anulado.")
    surgery = fu.surgery
    _validate_payload(
        surgery=surgery,
        reintervention_required=reintervention_required,
        reintervention_date=reintervention_date,
        reintervention_type=reintervention_type,
        retina_related=retina_related,
        status=status,
        notes=notes,
    )
    previous = _snapshot(fu)
    fu.reintervention_required = reintervention_required
    fu.reintervention_date = reintervention_date
    fu.reintervention_type = reintervention_type
    fu.retina_related = retina_related
    fu.status = status
    fu.notes = (notes or "").strip() or None
    fu.updated_by_user_id = actor.id
    new = _snapshot(fu)
    _add_revision(db, fu, action="updated", changed_by_id=actor.id, previous=previous, new=new)
    _sync_surgery_legacy(surgery, fu)
    db.commit()
    db.refresh(fu)
    return fu


def void_reintervention(
    db: Session,
    fu: ReinterventionFollowUp,
    *,
    actor: User,
    void_reason: str,
) -> ReinterventionFollowUp:
    reason = (void_reason or "").strip()
    if not reason:
        raise ReinterventionValidationError("Indique el motivo de anulación.")
    if fu.is_voided:
        raise ReinterventionValidationError("El seguimiento ya está anulado.")
    previous = _snapshot(fu)
    fu.is_voided = True
    fu.voided_at = datetime.now(timezone.utc)
    fu.voided_by_user_id = actor.id
    fu.void_reason = reason
    fu.updated_by_user_id = actor.id
    new = _snapshot(fu)
    _add_revision(db, fu, action="voided", changed_by_id=actor.id, previous=previous, new=new)
    # Re-sync legacy from latest non-voided
    active = (
        db.query(ReinterventionFollowUp)
        .filter(
            ReinterventionFollowUp.surgery_id == fu.surgery_id,
            ReinterventionFollowUp.is_voided.is_(False),
            ReinterventionFollowUp.id != fu.id,
        )
        .order_by(ReinterventionFollowUp.created_at.desc())
        .first()
    )
    _sync_surgery_legacy(fu.surgery, active)
    db.commit()
    db.refresh(fu)
    return fu


def get_reintervention(db: Session, follow_up_id: int) -> ReinterventionFollowUp | None:
    return (
        db.query(ReinterventionFollowUp)
        .options(
            joinedload(ReinterventionFollowUp.surgery).joinedload(Surgery.surgeon),
            joinedload(ReinterventionFollowUp.revisions),
            joinedload(ReinterventionFollowUp.created_by),
        )
        .filter(ReinterventionFollowUp.id == follow_up_id)
        .first()
    )


def list_reinterventions(
    db: Session,
    *,
    institution_id: str | None = None,
    center_id: int | None = None,
    surgeon_id: int | None = None,
    status: str | None = None,
    pending_only: bool = False,
    include_voided: bool = False,
) -> list[ReinterventionFollowUp]:
    q = (
        db.query(ReinterventionFollowUp)
        .join(Surgery, Surgery.id == ReinterventionFollowUp.surgery_id)
        .options(
            joinedload(ReinterventionFollowUp.surgery).joinedload(Surgery.surgeon),
        )
        .order_by(ReinterventionFollowUp.created_at.desc())
    )
    if institution_id:
        q = q.filter(Surgery.institution_id == institution_id)
    elif center_id is not None:
        q = q.filter(Surgery.center_id == center_id)
    if surgeon_id is not None:
        q = q.filter(Surgery.surgeon_id == surgeon_id)
    if not include_voided:
        q = q.filter(ReinterventionFollowUp.is_voided.is_(False))
    if pending_only:
        q = q.filter(
            ReinterventionFollowUp.status.in_(
                [
                    ReinterventionStatus.PENDING.value,
                    ReinterventionStatus.SCHEDULED.value,
                ]
            )
        )
    elif status:
        q = q.filter(ReinterventionFollowUp.status == status)
    return q.all()


def list_for_surgery(db: Session, surgery_id: int, *, include_voided: bool = True) -> list[ReinterventionFollowUp]:
    q = (
        db.query(ReinterventionFollowUp)
        .options(joinedload(ReinterventionFollowUp.created_by), joinedload(ReinterventionFollowUp.revisions))
        .filter(ReinterventionFollowUp.surgery_id == surgery_id)
        .order_by(ReinterventionFollowUp.created_at.desc())
    )
    if not include_voided:
        q = q.filter(ReinterventionFollowUp.is_voided.is_(False))
    return q.all()


def migrate_legacy_reinterventions(db: Session) -> int:
    """Create follow-ups from Surgery.reintervention_needed when table is empty for those cases."""
    created = 0
    surgeries = (
        db.query(Surgery)
        .filter(Surgery.reintervention_needed.is_(True))
        .all()
    )
    for surgery in surgeries:
        exists = (
            db.query(ReinterventionFollowUp.id)
            .filter(ReinterventionFollowUp.surgery_id == surgery.id)
            .first()
        )
        if exists:
            continue
        notes = surgery.reintervention_procedure_notes
        status = (
            ReinterventionStatus.COMPLETED.value
            if notes
            else ReinterventionStatus.PENDING.value
        )
        fu = ReinterventionFollowUp(
            surgery_id=surgery.id,
            reintervention_required=ReinterventionRequired.YES.value,
            reintervention_date=None if status == ReinterventionStatus.PENDING.value else surgery.surgery_date,
            reintervention_type=ReinterventionType.UNSPECIFIED.value,
            retina_related=RetinaRelated.UNKNOWN.value,
            status=status,
            notes=notes,
            created_by_user_id=surgery.created_by_id,
            updated_by_user_id=surgery.created_by_id,
        )
        db.add(fu)
        db.flush()
        _add_revision(
            db,
            fu,
            action="created",
            changed_by_id=surgery.created_by_id,
            previous=None,
            new=_snapshot(fu),
        )
        created += 1
    if created:
        db.commit()
    return created


def latest_active_for_surgery(surgery: Surgery) -> ReinterventionFollowUp | None:
    for fu in surgery.reintervention_follow_ups or []:
        if not fu.is_voided:
            return fu
    return None


def ops_status_label(surgery: Surgery) -> str:
    """Display label for list: Pendiente / No necesaria / Programada / Completada."""
    active = latest_active_for_surgery(surgery)
    if active is None:
        if surgery.reintervention_needed:
            return "Pendiente"
        return "No necesaria"
    if active.reintervention_required == ReinterventionRequired.NO.value:
        return "No necesaria"
    from app.constants import REINTERVENTION_STATUS_LABELS

    return REINTERVENTION_STATUS_LABELS.get(active.status, active.status)
