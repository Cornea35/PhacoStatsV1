"""Follow-up CRUD and refractive evaluation. No patient PII."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.clinical.astigmatism import (
    ORIENTATION_LABELS,
    CylinderConventionError,
    require_negative_cylinder,
)
from app.clinical.refractive import evaluate_refraction
from app.clinical.visual_acuity import normalize_snellen, snellen_to_logmar
from app.constants import (
    DEFAULT_INSTITUTION_CODE,
    IOL_TYPE_OPTIONS,
    VISIT_TYPE_LABELS,
    VisitType,
)
from app.models import FollowUp, FollowUpRevision, Surgery, User


class FollowUpValidationError(ValueError):
    """Invalid follow-up form / clinical data."""


def postoperative_days(visit_date: date, surgery_date: date) -> int:
    days = (visit_date - surgery_date).days
    if days < 0:
        raise FollowUpValidationError(
            "La fecha de visita no puede ser anterior a la cirugía."
        )
    return days


def _snapshot(fu: FollowUp) -> str:
    payload: dict[str, Any] = {
        "visit_date": fu.visit_date.isoformat(),
        "visit_type": fu.visit_type,
        "postoperative_days": fu.postoperative_days,
        "udva_snellen": fu.udva_snellen,
        "udva_logmar": fu.udva_logmar,
        "cdva_snellen": fu.cdva_snellen,
        "cdva_logmar": fu.cdva_logmar,
        "sphere": fu.sphere,
        "cylinder": fu.cylinder,
        "axis": fu.axis,
        "spherical_equivalent": fu.spherical_equivalent,
        "residual_astigmatism": fu.residual_astigmatism,
        "astigmatism_orientation": fu.astigmatism_orientation,
        "spherical_equivalent_stars": fu.spherical_equivalent_stars,
        "astigmatism_stars": fu.astigmatism_stars,
        "overall_refractive_stars": fu.overall_refractive_stars,
        "notes": fu.notes,
        "is_voided": fu.is_voided,
    }
    return json.dumps(payload, ensure_ascii=False)


def _add_revision(
    db: Session,
    follow_up: FollowUp,
    *,
    action: str,
    changed_by: User,
) -> None:
    db.add(
        FollowUpRevision(
            follow_up=follow_up,
            action=action,
            snapshot_json=_snapshot(follow_up),
            changed_by_id=changed_by.id,
        )
    )


def _parse_axis(cylinder: float, axis_raw: str | float | None) -> float | None:
    if abs(cylinder) < 1e-9:
        return None
    if axis_raw is None or axis_raw == "":
        raise FollowUpValidationError("El eje es obligatorio si el cilindro ≠ 0.")
    try:
        axis = float(axis_raw)
    except (TypeError, ValueError) as exc:
        raise FollowUpValidationError("Eje inválido.") from exc
    if not (0 <= axis <= 180):
        raise FollowUpValidationError("El eje debe estar entre 0 y 180.")
    return axis


def build_follow_up_fields(
    *,
    surgery: Surgery,
    visit_date: date,
    visit_type: str,
    sphere: float,
    cylinder: float,
    axis: float | None,
    udva_snellen: str | None,
    cdva_snellen: str | None,
    notes: str | None,
    institution_id: str | None = None,
) -> dict[str, Any]:
    if visit_type not in VISIT_TYPE_LABELS:
        raise FollowUpValidationError("Tipo de visita no válido.")

    try:
        cylinder = require_negative_cylinder(float(cylinder))
    except CylinderConventionError as exc:
        raise FollowUpValidationError(str(exc)) from exc

    axis_val = _parse_axis(cylinder, axis)
    try:
        result = evaluate_refraction(sphere, cylinder, axis_val)
    except ValueError as exc:
        raise FollowUpValidationError(str(exc)) from exc

    udva_n = normalize_snellen(udva_snellen)
    cdva_n = normalize_snellen(cdva_snellen)
    return {
        "surgery_id": surgery.id,
        "institution_id": (institution_id or surgery.institution_id or DEFAULT_INSTITUTION_CODE),
        "visit_date": visit_date,
        "visit_type": visit_type,
        "postoperative_days": postoperative_days(visit_date, surgery.surgery_date),
        "udva_snellen": udva_n,
        "udva_logmar": snellen_to_logmar(udva_n),
        "cdva_snellen": cdva_n,
        "cdva_logmar": snellen_to_logmar(cdva_n),
        "sphere": float(sphere),
        "cylinder": float(cylinder),
        "axis": axis_val,
        "spherical_equivalent": result.spherical_equivalent,
        "residual_astigmatism": result.residual_astigmatism,
        "astigmatism_orientation": result.astigmatism_orientation,
        "spherical_equivalent_stars": result.spherical_equivalent_stars,
        "astigmatism_stars": result.astigmatism_stars,
        "overall_refractive_stars": result.overall_refractive_stars,
        "notes": (notes or "").strip() or None,
    }


def create_follow_up(
    db: Session,
    surgery: Surgery,
    *,
    created_by: User,
    visit_date: date,
    visit_type: str,
    sphere: float,
    cylinder: float,
    axis: float | None,
    udva_snellen: str | None = None,
    cdva_snellen: str | None = None,
    notes: str | None = None,
) -> FollowUp:
    fields = build_follow_up_fields(
        surgery=surgery,
        visit_date=visit_date,
        visit_type=visit_type,
        sphere=sphere,
        cylinder=cylinder,
        axis=axis,
        udva_snellen=udva_snellen,
        cdva_snellen=cdva_snellen,
        notes=notes,
    )
    fu = FollowUp(**fields, created_by_id=created_by.id, is_voided=False)
    db.add(fu)
    db.flush()
    _add_revision(db, fu, action="created", changed_by=created_by)
    db.commit()
    db.refresh(fu)
    return fu


def update_follow_up(
    db: Session,
    follow_up: FollowUp,
    surgery: Surgery,
    *,
    changed_by: User,
    visit_date: date,
    visit_type: str,
    sphere: float,
    cylinder: float,
    axis: float | None,
    udva_snellen: str | None = None,
    cdva_snellen: str | None = None,
    notes: str | None = None,
) -> FollowUp:
    if follow_up.is_voided:
        raise FollowUpValidationError("No se puede editar una visita anulada.")
    fields = build_follow_up_fields(
        surgery=surgery,
        visit_date=visit_date,
        visit_type=visit_type,
        sphere=sphere,
        cylinder=cylinder,
        axis=axis,
        udva_snellen=udva_snellen,
        cdva_snellen=cdva_snellen,
        notes=notes,
    )
    for key, value in fields.items():
        setattr(follow_up, key, value)
    _add_revision(db, follow_up, action="updated", changed_by=changed_by)
    db.commit()
    db.refresh(follow_up)
    return follow_up


def void_follow_up(
    db: Session,
    follow_up: FollowUp,
    *,
    changed_by: User,
) -> FollowUp:
    if follow_up.is_voided:
        raise FollowUpValidationError("La visita ya está anulada.")
    follow_up.is_voided = True
    _add_revision(db, follow_up, action="voided", changed_by=changed_by)
    db.commit()
    db.refresh(follow_up)
    return follow_up


def get_follow_up(db: Session, follow_up_id: int) -> FollowUp | None:
    return (
        db.query(FollowUp)
        .options(
            joinedload(FollowUp.surgery).joinedload(Surgery.surgeon),
            joinedload(FollowUp.revisions).joinedload(FollowUpRevision.changed_by),
            joinedload(FollowUp.created_by),
        )
        .filter(FollowUp.id == follow_up_id)
        .first()
    )


def list_follow_ups_for_surgery(db: Session, surgery_id: int) -> list[FollowUp]:
    return (
        db.query(FollowUp)
        .options(
            joinedload(FollowUp.created_by),
            joinedload(FollowUp.revisions).joinedload(FollowUpRevision.changed_by),
        )
        .filter(FollowUp.surgery_id == surgery_id)
        .order_by(FollowUp.visit_date.desc(), FollowUp.id.desc())
        .all()
    )


def preview_refraction(sphere: float, cylinder: float, axis: float | None) -> dict[str, Any]:
    """API helper for live form preview (mirrors server rules)."""
    cylinder = require_negative_cylinder(cylinder)
    result = evaluate_refraction(sphere, cylinder, axis)
    return {
        "spherical_equivalent": result.spherical_equivalent,
        "residual_astigmatism": result.residual_astigmatism,
        "cylinder": cylinder,
        "astigmatism_orientation": result.astigmatism_orientation,
        "orientation_label": ORIENTATION_LABELS.get(
            result.astigmatism_orientation, result.astigmatism_orientation
        ),
        "spherical_equivalent_stars": result.spherical_equivalent_stars,
        "astigmatism_stars": result.astigmatism_stars,
        "overall_refractive_stars": result.overall_refractive_stars,
        "j0": result.j0,
        "j45": result.j45,
        "double_angle_x": result.double_angle_x,
        "double_angle_y": result.double_angle_y,
    }


# Re-exports for templates / routers
__all__ = [
    "FollowUpValidationError",
    "VisitType",
    "VISIT_TYPE_LABELS",
    "IOL_TYPE_OPTIONS",
    "create_follow_up",
    "update_follow_up",
    "void_follow_up",
    "get_follow_up",
    "list_follow_ups_for_surgery",
    "preview_refraction",
    "postoperative_days",
    "build_follow_up_fields",
]
