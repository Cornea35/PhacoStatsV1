"""Surgery CRUD routes with role-aware list/detail."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.constants import (
    COMPLICATION_TYPE_LABELS,
    IOL_POSITION_LABELS,
    IOL_TYPE_OPTIONS,
    RISK_FACTOR_CATALOG,
    SURGICAL_STAGE_LABELS,
    VISIT_TYPE_LABELS,
    ComplicationType,
    EyeSide,
    IOLPosition,
    SurgicalStage,
    UserRole,
)
from app.clinical.refraction import ORIENTATION_LABELS
from app.database import get_db
from app.deps import flash, pop_flashes, require_roles
from app.models import User
from app.permissions import (
    Permission,
    assert_surgery_institution_access,
    get_tenant_context,
    has_permission,
    institution_scope,
    is_coordinator,
    require_permission,
    scope_center_id,
    scope_institution,
    TenantContext,
)
from app.services.followups import list_follow_ups_for_surgery
from app.services.ops_export import export_ops_xlsx
from app.services.reinterventions import list_for_surgery, ops_status_label
from app.services.surgeries import (
    SurgeryValidationError,
    build_complication_event,
    create_surgery,
    get_surgery_detail,
    list_surgeries,
    update_surgery,
)
from app.templating import templates

router = APIRouter(prefix="/surgeries", tags=["surgeries"])

StaffDep = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.SURGEON,
            UserRole.COORDINATOR,
            UserRole.GENERAL_ADMIN,
            UserRole.CENTER_ADMIN,
            UserRole.SUPERVISOR,
        )
    ),
]
ClinicalWriteDep = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.SURGEON,
            UserRole.COORDINATOR,
            UserRole.CENTER_ADMIN,
            UserRole.GENERAL_ADMIN,
        )
    ),
]


def _surgeons(
    db: Session,
    *,
    institution_id: str | None = None,
    include_user_id: int | None = None,
) -> list[User]:
    q = db.query(User).filter(User.role == UserRole.SURGEON.value)
    if include_user_id is not None:
        q = q.filter((User.is_active.is_(True)) | (User.id == include_user_id))
    else:
        q = q.filter(User.is_active.is_(True))
    if institution_id:
        q = q.filter(User.institution_id == institution_id)
    return q.order_by(User.full_name).all()


def _optional_form_int(value: str | int | None) -> int | None:
    """Coerce form ints; empty strings become None (avoids FastAPI 422)."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _form_context(current: User, db: Session, surgery=None, selected_risks: list[str] | None = None):
    include_id = surgery.surgeon_id if surgery is not None else None
    return {
        "user": current,
        "surgeons": _surgeons(db, include_user_id=include_id),
        "eyes": EyeSide,
        "risk_catalog": RISK_FACTOR_CATALOG,
        "complication_types": ComplicationType,
        "complication_labels": COMPLICATION_TYPE_LABELS,
        "stages": SurgicalStage,
        "stage_labels": SURGICAL_STAGE_LABELS,
        "iol_positions": IOLPosition,
        "iol_labels": IOL_POSITION_LABELS,
        "iol_types": IOL_TYPE_OPTIONS,
        "surgery": surgery,
        "selected_risks": selected_risks or [],
        "can_edit_surgery": has_permission(current, Permission.EDIT_SURGERY),
    }


def _parse_complication_form(
    *,
    complication_occurred: str | None,
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
):
    return build_complication_event(
        occurred=complication_occurred == "on",
        complication_type=complication_type,
        surgical_stage=surgical_stage,
        vitreous_loss=vitreous_loss,
        anterior_vitrectomy=anterior_vitrectomy,
        fragments_to_posterior=fragments_to_posterior,
        retina_intervention=retina_intervention,
        iol_position=iol_position,
        capsular_tension_ring=capsular_tension_ring,
        segment_ring_suture=segment_ring_suture,
        f2_assistant_help=f2_assistant_help,
    )


@router.get("/export.xlsx")
def surgeries_ops_export(
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_permission(Permission.EXPORT_OPS))],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    content = export_ops_xlsx(
        db,
        institution_id=scope_institution(ctx) or institution_scope(current),
    )
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="phacostats_ops_export.xlsx"'},
    )


@router.get("", response_class=HTMLResponse)
def surgeries_list(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    q: Annotated[str | None, Query(description="Código de cirugía")] = None,
    complication: Annotated[str, Query()] = "all",
    reintervention: Annotated[str, Query()] = "all",
    followup_pending: Annotated[str, Query()] = "",
    eye: Annotated[str, Query()] = "",
    technique: Annotated[str, Query()] = "",
    surgeon_id: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    own_surgeon = current.id if current.role == UserRole.SURGEON.value else None
    inst = scope_institution(ctx)
    center_id = scope_center_id(ctx)
    case_q = (q or "").strip() or None
    comp = complication if complication in {"all", "yes", "no"} else "all"
    reint = reintervention if reintervention in {"all", "yes", "no"} else "all"
    pending = followup_pending in {"1", "on", "yes", "true"}
    eye_f = eye if eye in {e.value for e in EyeSide} else None
    tech = (technique or "").strip() or None
    filter_surgeon = None if own_surgeon else _optional_form_int(surgeon_id)

    items = list_surgeries(
        db,
        surgeon_id=own_surgeon,
        institution_id=inst,
        center_id=center_id,
        case_code=case_q,
        complication=None if comp == "all" else comp,
        reintervention=None if reint == "all" else reint,
        followup_pending=pending,
        eye=eye_f,
        technique=tech,
        date_from=date_from,
        date_to=date_to,
        filter_surgeon_id=filter_surgeon,
    )
    filters_active = bool(
        case_q
        or comp != "all"
        or reint != "all"
        or pending
        or eye_f
        or tech
        or filter_surgeon
        or date_from
        or date_to
    )

    if is_coordinator(current):
        return templates.TemplateResponse(
            request,
            "surgeries/list_coordinator.html",
            {
                "user": current,
                "surgeries": items,
                "ops_status_label": ops_status_label,
                "flashes": pop_flashes(request),
                "filter_q": case_q or "",
                "filter_complication": comp,
                "filter_reintervention": reint,
                "filter_followup_pending": pending,
                "filter_eye": eye_f or "",
                "filter_technique": tech or "",
                "filter_surgeon_id": filter_surgeon or "",
                "filter_date_from": date_from.isoformat() if date_from else "",
                "filter_date_to": date_to.isoformat() if date_to else "",
                "surgeons": _surgeons(db, institution_id=inst),
                "eyes": EyeSide,
                "filters_active": filters_active,
                "result_count": len(items),
            },
        )

    return templates.TemplateResponse(
        request,
        "surgeries/list.html",
        {
            "user": current,
            "surgeries": items,
            "complication_labels": COMPLICATION_TYPE_LABELS,
            "flashes": pop_flashes(request),
            "filter_q": case_q or "",
            "filter_complication": comp,
            "filter_reintervention": reint,
            "filters_active": filters_active,
            "result_count": len(items),
            "scoped": own_surgeon is not None,
            "can_edit_surgery": has_permission(current, Permission.EDIT_SURGERY),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def surgery_new_form(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ClinicalWriteDep,
):
    ctx = _form_context(current, db)
    ctx["flashes"] = pop_flashes(request)
    return templates.TemplateResponse(request, "surgeries/form.html", ctx)


@router.post("/new")
def surgery_create(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ClinicalWriteDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    case_code: Annotated[str, Form()],
    surgery_date: Annotated[date, Form()],
    eye: Annotated[str, Form()],
    technique: Annotated[str, Form()] = "Phacoemulsification",
    notes: Annotated[str, Form()] = "",
    surgeon_id: Annotated[str | None, Form()] = None,
    iol_type: Annotated[str, Form()] = "",
    risk_codes: Annotated[list[str], Form()] = [],
    complication_occurred: Annotated[str | None, Form()] = None,
    complication_type: Annotated[str | None, Form()] = None,
    surgical_stage: Annotated[str | None, Form()] = None,
    vitreous_loss: Annotated[str | None, Form()] = None,
    anterior_vitrectomy: Annotated[str | None, Form()] = None,
    fragments_to_posterior: Annotated[str | None, Form()] = None,
    retina_intervention: Annotated[str | None, Form()] = None,
    iol_position: Annotated[str | None, Form()] = None,
    capsular_tension_ring: Annotated[str | None, Form()] = None,
    segment_ring_suture: Annotated[str | None, Form()] = None,
    f2_assistant_help: Annotated[str | None, Form()] = None,
):
    resolved_surgeon_id = (
        current.id if current.role == UserRole.SURGEON.value else _optional_form_int(surgeon_id)
    )
    if resolved_surgeon_id is None:
        flash(request, "Debe indicar un cirujano.", "danger")
        return RedirectResponse("/surgeries/new", status_code=status.HTTP_303_SEE_OTHER)

    try:
        complication = _parse_complication_form(
            complication_occurred=complication_occurred,
            complication_type=complication_type,
            surgical_stage=surgical_stage,
            vitreous_loss=vitreous_loss,
            anterior_vitrectomy=anterior_vitrectomy,
            fragments_to_posterior=fragments_to_posterior,
            retina_intervention=retina_intervention,
            iol_position=iol_position,
            capsular_tension_ring=capsular_tension_ring,
            segment_ring_suture=segment_ring_suture,
            f2_assistant_help=f2_assistant_help,
        )
        create_surgery(
            db,
            case_code=case_code,
            surgery_date=surgery_date,
            eye=eye,
            technique=technique,
            notes=notes,
            surgeon_id=resolved_surgeon_id,
            created_by=current,
            risk_codes=list(risk_codes or []),
            complication=complication,
            iol_type=iol_type or None,
            institution_id=ctx.institution_code or current.institution_id,
            center_id=ctx.center_id,
        )
    except SurgeryValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse("/surgeries/new", status_code=status.HTTP_303_SEE_OTHER)

    flash(request, "Cirugía registrada (datos anónimos).", "success")
    return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{surgery_id}", response_class=HTMLResponse)
def surgery_detail(
    surgery_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
):
    surgery = get_surgery_detail(db, surgery_id)
    if surgery is None:
        flash(request, "Cirugía no encontrada.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    if current.role == UserRole.SURGEON.value and surgery.surgeon_id != current.id:
        flash(request, "No puede ver cirugías de otros cirujanos.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    assert_surgery_institution_access(current, surgery.institution_id)

    if is_coordinator(current):
        return templates.TemplateResponse(
            request,
            "surgeries/detail_coordinator.html",
            {
                "user": current,
                "surgery": surgery,
                "reinterventions": list_for_surgery(db, surgery.id),
                "ops_status_label": ops_status_label(surgery),
                "flashes": pop_flashes(request),
            },
        )

    return templates.TemplateResponse(
        request,
        "surgeries/detail.html",
        {
            "user": current,
            "surgery": surgery,
            "follow_ups": list_follow_ups_for_surgery(db, surgery.id),
            "reinterventions": list_for_surgery(db, surgery.id),
            "risk_catalog": RISK_FACTOR_CATALOG,
            "complication_labels": COMPLICATION_TYPE_LABELS,
            "stage_labels": SURGICAL_STAGE_LABELS,
            "iol_labels": IOL_POSITION_LABELS,
            "iol_types": IOL_TYPE_OPTIONS,
            "visit_labels": VISIT_TYPE_LABELS,
            "orientation_labels": ORIENTATION_LABELS,
            "flashes": pop_flashes(request),
            "can_edit_surgery": has_permission(current, Permission.EDIT_SURGERY),
            "can_manage_reintervention": has_permission(
                current, Permission.MANAGE_REINTERVENTION
            )
            or current.role
            in {
                UserRole.GENERAL_ADMIN.value,
                UserRole.CENTER_ADMIN.value,
                UserRole.SURGEON.value,
            },
        },
    )


@router.get("/{surgery_id}/edit", response_class=HTMLResponse)
def surgery_edit_form(
    surgery_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ClinicalWriteDep,
):
    surgery = get_surgery_detail(db, surgery_id)
    if surgery is None:
        flash(request, "Cirugía no encontrada.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    if current.role == UserRole.SURGEON.value and surgery.surgeon_id != current.id:
        flash(request, "No puede editar cirugías de otros cirujanos.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)

    ctx = _form_context(
        current,
        db,
        surgery=surgery,
        selected_risks=[rf.code for rf in surgery.risk_factors],
    )
    ctx["flashes"] = pop_flashes(request)
    return templates.TemplateResponse(request, "surgeries/form.html", ctx)


@router.post("/{surgery_id}/edit")
def surgery_edit_submit(
    surgery_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ClinicalWriteDep,
    case_code: Annotated[str, Form()],
    surgery_date: Annotated[date, Form()],
    eye: Annotated[str, Form()],
    technique: Annotated[str, Form()] = "Phacoemulsification",
    notes: Annotated[str, Form()] = "",
    surgeon_id: Annotated[str | None, Form()] = None,
    iol_type: Annotated[str, Form()] = "",
    risk_codes: Annotated[list[str], Form()] = [],
    complication_occurred: Annotated[str | None, Form()] = None,
    complication_type: Annotated[str | None, Form()] = None,
    surgical_stage: Annotated[str | None, Form()] = None,
    vitreous_loss: Annotated[str | None, Form()] = None,
    anterior_vitrectomy: Annotated[str | None, Form()] = None,
    fragments_to_posterior: Annotated[str | None, Form()] = None,
    retina_intervention: Annotated[str | None, Form()] = None,
    iol_position: Annotated[str | None, Form()] = None,
    capsular_tension_ring: Annotated[str | None, Form()] = None,
    segment_ring_suture: Annotated[str | None, Form()] = None,
    f2_assistant_help: Annotated[str | None, Form()] = None,
):
    surgery = get_surgery_detail(db, surgery_id)
    if surgery is None:
        flash(request, "Cirugía no encontrada.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    if current.role == UserRole.SURGEON.value and surgery.surgeon_id != current.id:
        flash(request, "No puede editar cirugías de otros cirujanos.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)

    resolved_surgeon_id = (
        current.id if current.role == UserRole.SURGEON.value else _optional_form_int(surgeon_id)
    )
    if resolved_surgeon_id is None:
        flash(request, "Debe indicar un cirujano.", "danger")
        return RedirectResponse(f"/surgeries/{surgery_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    try:
        complication = _parse_complication_form(
            complication_occurred=complication_occurred,
            complication_type=complication_type,
            surgical_stage=surgical_stage,
            vitreous_loss=vitreous_loss,
            anterior_vitrectomy=anterior_vitrectomy,
            fragments_to_posterior=fragments_to_posterior,
            retina_intervention=retina_intervention,
            iol_position=iol_position,
            capsular_tension_ring=capsular_tension_ring,
            segment_ring_suture=segment_ring_suture,
            f2_assistant_help=f2_assistant_help,
        )
        update_surgery(
            db,
            surgery,
            case_code=case_code,
            surgery_date=surgery_date,
            eye=eye,
            technique=technique,
            notes=notes,
            surgeon_id=resolved_surgeon_id,
            risk_codes=list(risk_codes or []),
            complication=complication,
            iol_type=iol_type or None,
        )
    except SurgeryValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(f"/surgeries/{surgery_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    flash(request, "Cirugía actualizada.", "success")
    return RedirectResponse(f"/surgeries/{surgery_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{surgery_id}/postop")
def surgery_postop_legacy_redirect(surgery_id: int):
    """Legacy endpoint: send users to the reintervention module."""
    return RedirectResponse(
        f"/reinterventions/new?surgery_id={surgery_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
