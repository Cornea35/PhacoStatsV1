"""Surgery create/update helpers and complication validation rules."""

from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.constants import (
    DEFAULT_INSTITUTION_CODE,
    IOL_TYPE_OPTIONS,
    RISK_FACTOR_CATALOG,
    ComplicationType,
    IOLPosition,
    SurgicalStage,
)
from app.models import ComplicationEvent, RiskFactor, Surgery, User


class SurgeryValidationError(ValueError):
    """Raised when surgery / complication form data is invalid."""


def _normalize_risk_codes(risk_codes: list[str]) -> list[str]:
    return sorted({code for code in risk_codes if code in RISK_FACTOR_CATALOG})


def _parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.lower() in {"1", "true", "on", "yes", "si", "sí"}


def build_complication_event(
    *,
    occurred: bool,
    complication_type: str | None,
    surgical_stage: str | None,
    vitreous_loss: str | None,
    anterior_vitrectomy: str | None,
    fragments_to_posterior: str | None,
    retina_intervention: str | None,
    iol_position: str | None,
    capsular_tension_ring: str | None,
    segment_ring_suture: str | None,
    f2_assistant_help: str | None,
) -> ComplicationEvent:
    if not occurred:
        return ComplicationEvent(occurred=False)

    if not complication_type or complication_type not in {c.value for c in ComplicationType}:
        raise SurgeryValidationError("Si hubo complicación, indique el tipo.")
    if not surgical_stage or surgical_stage not in {s.value for s in SurgicalStage}:
        raise SurgeryValidationError("Si hubo complicación, la etapa quirúrgica es obligatoria.")
    if not iol_position or iol_position not in {p.value for p in IOLPosition}:
        raise SurgeryValidationError("Si hubo complicación, la posición final del LIO es obligatoria.")

    flags = {
        "pérdida vítrea": _parse_bool(vitreous_loss),
        "vitrectomía anterior": _parse_bool(anterior_vitrectomy),
        "fragmentos al segmento posterior": _parse_bool(fragments_to_posterior),
        "intervención por retina": _parse_bool(retina_intervention),
        "anillo de tensión capsular": _parse_bool(capsular_tension_ring),
        "sutura de segmento/anillo": _parse_bool(segment_ring_suture),
        "ayuda de F2 o adscrito": _parse_bool(f2_assistant_help),
    }
    missing = [name for name, value in flags.items() if value is None]
    if missing:
        raise SurgeryValidationError(
            "Si hubo complicación, complete: " + ", ".join(missing) + "."
        )

    return ComplicationEvent(
        occurred=True,
        complication_type=complication_type,
        surgical_stage=surgical_stage,
        vitreous_loss=flags["pérdida vítrea"],
        anterior_vitrectomy=flags["vitrectomía anterior"],
        fragments_to_posterior=flags["fragmentos al segmento posterior"],
        retina_intervention=flags["intervención por retina"],
        iol_position=iol_position,
        capsular_tension_ring=flags["anillo de tensión capsular"],
        segment_ring_suture=flags["sutura de segmento/anillo"],
        f2_assistant_help=flags["ayuda de F2 o adscrito"],
    )


def _apply_complication(surgery: Surgery, event: ComplicationEvent) -> None:
    if surgery.complication is None:
        surgery.complication = event
        return
    surgery.complication.occurred = event.occurred
    surgery.complication.complication_type = event.complication_type
    surgery.complication.surgical_stage = event.surgical_stage
    surgery.complication.vitreous_loss = event.vitreous_loss
    surgery.complication.anterior_vitrectomy = event.anterior_vitrectomy
    surgery.complication.fragments_to_posterior = event.fragments_to_posterior
    surgery.complication.retina_intervention = event.retina_intervention
    surgery.complication.iol_position = event.iol_position
    surgery.complication.capsular_tension_ring = event.capsular_tension_ring
    surgery.complication.segment_ring_suture = event.segment_ring_suture
    surgery.complication.f2_assistant_help = event.f2_assistant_help


def _normalize_iol_type(iol_type: str | None) -> str | None:
    if not iol_type:
        return None
    code = iol_type.strip().lower()
    if code not in IOL_TYPE_OPTIONS:
        raise SurgeryValidationError("Tipo de LIO no válido.")
    return code


def create_surgery(
    db: Session,
    *,
    case_code: str,
    surgery_date: date,
    eye: str,
    technique: str,
    notes: str | None,
    surgeon_id: int,
    created_by: User,
    risk_codes: list[str],
    complication: ComplicationEvent,
    iol_type: str | None = None,
    institution_id: str | None = None,
) -> Surgery:
    case_code = case_code.strip().upper()
    if not case_code:
        raise SurgeryValidationError("El código de caso es obligatorio.")
    if db.query(Surgery).filter(Surgery.case_code == case_code).first():
        raise SurgeryValidationError(f"El código {case_code} ya existe.")

    surgeon = db.get(User, surgeon_id)
    if surgeon is None or surgeon.role != "surgeon" or not surgeon.is_active:
        raise SurgeryValidationError("Seleccione un cirujano activo válido.")

    surgery = Surgery(
        case_code=case_code,
        surgery_date=surgery_date,
        eye=eye,
        technique=technique.strip() or "Phacoemulsification",
        iol_type=_normalize_iol_type(iol_type),
        institution_id=(institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE,
        notes=notes.strip() if notes else None,
        surgeon_id=surgeon_id,
        created_by_id=created_by.id,
        risk_factors=[RiskFactor(code=code) for code in _normalize_risk_codes(risk_codes)],
        complication=complication,
    )
    db.add(surgery)
    db.commit()
    db.refresh(surgery)
    return surgery


def update_surgery(
    db: Session,
    surgery: Surgery,
    *,
    case_code: str,
    surgery_date: date,
    eye: str,
    technique: str,
    notes: str | None,
    surgeon_id: int,
    risk_codes: list[str],
    complication: ComplicationEvent,
    iol_type: str | None = None,
    institution_id: str | None = None,
) -> Surgery:
    case_code = case_code.strip().upper()
    existing = (
        db.query(Surgery)
        .filter(Surgery.case_code == case_code, Surgery.id != surgery.id)
        .first()
    )
    if existing:
        raise SurgeryValidationError(f"El código {case_code} ya existe.")

    surgeon = db.get(User, surgeon_id)
    if surgeon is None or surgeon.role != "surgeon" or not surgeon.is_active:
        raise SurgeryValidationError("Seleccione un cirujano activo válido.")

    surgery.case_code = case_code
    surgery.surgery_date = surgery_date
    surgery.eye = eye
    surgery.technique = technique.strip() or "Phacoemulsification"
    surgery.iol_type = _normalize_iol_type(iol_type)
    if institution_id is not None:
        surgery.institution_id = institution_id.strip() or DEFAULT_INSTITUTION_CODE
    surgery.notes = notes.strip() if notes else None
    surgery.surgeon_id = surgeon_id

    surgery.risk_factors.clear()
    for code in _normalize_risk_codes(risk_codes):
        surgery.risk_factors.append(RiskFactor(code=code))

    _apply_complication(surgery, complication)

    db.commit()
    db.refresh(surgery)
    return surgery


def update_postop_followup(
    db: Session,
    surgery: Surgery,
    *,
    reintervention_needed: bool,
    procedure_notes: str | None,
) -> Surgery:
    """Record reintervention flag and procedure note (admin / coordinator)."""
    surgery.reintervention_needed = reintervention_needed
    note = (procedure_notes or "").strip()
    if reintervention_needed and not note:
        raise SurgeryValidationError(
            "Si hubo reintervención, indique la nota del procedimiento realizado."
        )
    surgery.reintervention_procedure_notes = note or None
    db.commit()
    db.refresh(surgery)
    return surgery


def get_surgery_detail(db: Session, surgery_id: int) -> Surgery | None:
    return (
        db.query(Surgery)
        .options(
            joinedload(Surgery.surgeon),
            joinedload(Surgery.risk_factors),
            joinedload(Surgery.complication),
            joinedload(Surgery.follow_ups),
            joinedload(Surgery.reintervention_follow_ups),
        )
        .filter(Surgery.id == surgery_id)
        .first()
    )


def list_surgeries(
    db: Session,
    *,
    surgeon_id: int | None = None,
    institution_id: str | None = None,
    case_code: str | None = None,
    complication: str | None = None,
    reintervention: str | None = None,
    followup_pending: bool = False,
    eye: str | None = None,
    technique: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    filter_surgeon_id: int | None = None,
) -> list[Surgery]:
    """List surgeries with optional filters (role scoping via surgeon_id / institution_id).

    complication / reintervention: None|"all" (no filter), "yes", "no".
    case_code: partial match on anonymous case code (case-insensitive).
    """
    from app.constants import ReinterventionStatus
    from app.models import ReinterventionFollowUp

    q = (
        db.query(Surgery)
        .options(
            joinedload(Surgery.surgeon),
            joinedload(Surgery.complication),
            joinedload(Surgery.reintervention_follow_ups),
        )
        .order_by(Surgery.surgery_date.desc(), Surgery.id.desc())
    )
    if surgeon_id is not None:
        q = q.filter(Surgery.surgeon_id == surgeon_id)
    if filter_surgeon_id is not None:
        q = q.filter(Surgery.surgeon_id == filter_surgeon_id)
    if institution_id:
        q = q.filter(Surgery.institution_id == institution_id)
    if date_from is not None:
        q = q.filter(Surgery.surgery_date >= date_from)
    if date_to is not None:
        q = q.filter(Surgery.surgery_date <= date_to)
    if eye:
        q = q.filter(Surgery.eye == eye)
    if technique:
        q = q.filter(Surgery.technique.contains(technique.strip()))

    needle = (case_code or "").strip().upper()
    if needle:
        q = q.filter(Surgery.case_code.contains(needle))

    comp = (complication or "").strip().lower()
    if comp in {"yes", "si", "sí", "1", "true"}:
        q = q.filter(Surgery.complication.has(ComplicationEvent.occurred.is_(True)))
    elif comp in {"no", "0", "false"}:
        q = q.filter(
            ~Surgery.complication.has(ComplicationEvent.occurred.is_(True)),
        )

    reint = (reintervention or "").strip().lower()
    if reint in {"yes", "si", "sí", "1", "true"}:
        q = q.filter(Surgery.reintervention_needed.is_(True))
    elif reint in {"no", "0", "false"}:
        q = q.filter(Surgery.reintervention_needed.is_(False))

    if followup_pending:
        pending_ids = [
            row[0]
            for row in db.query(ReinterventionFollowUp.surgery_id)
            .filter(
                ReinterventionFollowUp.is_voided.is_(False),
                ReinterventionFollowUp.status.in_(
                    [
                        ReinterventionStatus.PENDING.value,
                        ReinterventionStatus.SCHEDULED.value,
                    ]
                ),
            )
            .distinct()
            .all()
        ]
        if not pending_ids:
            return []
        q = q.filter(Surgery.id.in_(pending_ids))

    return q.all()
