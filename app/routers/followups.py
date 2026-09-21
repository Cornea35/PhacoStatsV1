"""Follow-up visit routes nested under surgeries."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.constants import VISIT_TYPE_LABELS, VisitType, UserRole
from app.database import get_db
from app.deps import flash, pop_flashes, require_roles
from app.models import User
from app.services.followups import (
    FollowUpValidationError,
    create_follow_up,
    get_follow_up,
    preview_refraction,
    update_follow_up,
    void_follow_up,
)
from app.services.surgeries import get_surgery_detail
from app.templating import templates

router = APIRouter(prefix="/surgeries", tags=["followups"])

StaffDep = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.SURGEON,
            UserRole.GENERAL_ADMIN,
            UserRole.CENTER_ADMIN,
        )
    ),
]


def _can_access(surgery, current: User) -> bool:
    if current.role == UserRole.SURGEON.value and surgery.surgeon_id != current.id:
        return False
    return True


def _parse_float(raw: str | None, field: str) -> float:
    if raw is None or str(raw).strip() == "":
        raise FollowUpValidationError(f"{field} es obligatorio.")
    try:
        return float(raw)
    except ValueError as exc:
        raise FollowUpValidationError(f"{field} inválido.") from exc


@router.get("/api/refraction-preview")
def refraction_preview(
    current: StaffDep,
    sphere: float = 0.0,
    cylinder: float = 0.0,
    axis: float | None = None,
):
    try:
        if abs(cylinder) < 1e-9:
            axis = None
        data = preview_refraction(sphere, cylinder, axis)
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.get("/{surgery_id}/follow-ups/new", response_class=HTMLResponse)
def followup_new_form(
    surgery_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
):
    surgery = get_surgery_detail(db, surgery_id)
    if surgery is None or not _can_access(surgery, current):
        flash(request, "Cirugía no encontrada o sin acceso.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "followups/form.html",
        {
            "user": current,
            "surgery": surgery,
            "follow_up": None,
            "visit_types": VisitType,
            "visit_labels": VISIT_TYPE_LABELS,
            "flashes": pop_flashes(request),
        },
    )


@router.post("/{surgery_id}/follow-ups/new")
def followup_create(
    surgery_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
    visit_date: Annotated[date, Form()],
    visit_type: Annotated[str, Form()],
    sphere: Annotated[str, Form()],
    cylinder: Annotated[str, Form()],
    axis: Annotated[str, Form()] = "",
    udva_snellen: Annotated[str, Form()] = "",
    cdva_snellen: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    surgery = get_surgery_detail(db, surgery_id)
    if surgery is None or not _can_access(surgery, current):
        flash(request, "Cirugía no encontrada o sin acceso.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    try:
        create_follow_up(
            db,
            surgery,
            created_by=current,
            visit_date=visit_date,
            visit_type=visit_type,
            sphere=_parse_float(sphere, "Esfera"),
            cylinder=_parse_float(cylinder, "Cilindro"),
            axis=float(axis) if axis.strip() else None,
            udva_snellen=udva_snellen or None,
            cdva_snellen=cdva_snellen or None,
            notes=notes or None,
        )
    except FollowUpValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            f"/surgeries/{surgery_id}/follow-ups/new",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Visita de seguimiento registrada.", "success")
    return RedirectResponse(f"/surgeries/{surgery_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{surgery_id}/follow-ups/{follow_up_id}/edit", response_class=HTMLResponse)
def followup_edit_form(
    surgery_id: int,
    follow_up_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
):
    surgery = get_surgery_detail(db, surgery_id)
    fu = get_follow_up(db, follow_up_id)
    if surgery is None or fu is None or fu.surgery_id != surgery_id or not _can_access(surgery, current):
        flash(request, "Visita no encontrada o sin acceso.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "followups/form.html",
        {
            "user": current,
            "surgery": surgery,
            "follow_up": fu,
            "visit_types": VisitType,
            "visit_labels": VISIT_TYPE_LABELS,
            "flashes": pop_flashes(request),
        },
    )


@router.post("/{surgery_id}/follow-ups/{follow_up_id}/edit")
def followup_edit_submit(
    surgery_id: int,
    follow_up_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
    visit_date: Annotated[date, Form()],
    visit_type: Annotated[str, Form()],
    sphere: Annotated[str, Form()],
    cylinder: Annotated[str, Form()],
    axis: Annotated[str, Form()] = "",
    udva_snellen: Annotated[str, Form()] = "",
    cdva_snellen: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    surgery = get_surgery_detail(db, surgery_id)
    fu = get_follow_up(db, follow_up_id)
    if surgery is None or fu is None or fu.surgery_id != surgery_id or not _can_access(surgery, current):
        flash(request, "Visita no encontrada o sin acceso.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    try:
        update_follow_up(
            db,
            fu,
            surgery,
            changed_by=current,
            visit_date=visit_date,
            visit_type=visit_type,
            sphere=_parse_float(sphere, "Esfera"),
            cylinder=_parse_float(cylinder, "Cilindro"),
            axis=float(axis) if axis.strip() else None,
            udva_snellen=udva_snellen or None,
            cdva_snellen=cdva_snellen or None,
            notes=notes or None,
        )
    except FollowUpValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            f"/surgeries/{surgery_id}/follow-ups/{follow_up_id}/edit",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Visita actualizada.", "success")
    return RedirectResponse(f"/surgeries/{surgery_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{surgery_id}/follow-ups/{follow_up_id}/void")
def followup_void(
    surgery_id: int,
    follow_up_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffDep,
):
    surgery = get_surgery_detail(db, surgery_id)
    fu = get_follow_up(db, follow_up_id)
    if surgery is None or fu is None or fu.surgery_id != surgery_id or not _can_access(surgery, current):
        flash(request, "Visita no encontrada o sin acceso.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    try:
        void_follow_up(db, fu, changed_by=current)
    except FollowUpValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(f"/surgeries/{surgery_id}", status_code=status.HTTP_303_SEE_OTHER)
    flash(request, "Visita anulada.", "success")
    return RedirectResponse(f"/surgeries/{surgery_id}", status_code=status.HTTP_303_SEE_OTHER)
