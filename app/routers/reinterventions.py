"""Reintervention follow-up routes (admin, coordinator, surgeon)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.constants import (
    REINTERVENTION_REQUIRED_LABELS,
    REINTERVENTION_STATUS_LABELS,
    REINTERVENTION_TYPE_LABELS,
    RETINA_RELATED_LABELS,
    ReinterventionRequired,
    ReinterventionStatus,
    ReinterventionType,
    RetinaRelated,
    UserRole,
)
from app.database import get_db
from app.deps import flash, pop_flashes, require_roles
from app.models import User
from app.permissions import (
    TenantContext,
    assert_surgery_access,
    get_tenant_context,
    scope_center_id,
    scope_institution,
)
from app.services.reinterventions import (
    ReinterventionValidationError,
    create_reintervention,
    get_reintervention,
    list_reinterventions,
    update_reintervention,
    void_reintervention,
)
from app.services.surgeries import get_surgery_detail
from app.templating import templates

router = APIRouter(prefix="/reinterventions", tags=["reinterventions"])

OpsDep = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.GENERAL_ADMIN,
            UserRole.CENTER_ADMIN,
            UserRole.COORDINATOR,
            UserRole.SURGEON,
        )
    ),
]


def _form_labels() -> dict:
    return {
        "required_options": ReinterventionRequired,
        "required_labels": REINTERVENTION_REQUIRED_LABELS,
        "status_options": ReinterventionStatus,
        "status_labels": REINTERVENTION_STATUS_LABELS,
        "type_options": ReinterventionType,
        "type_labels": REINTERVENTION_TYPE_LABELS,
        "retina_options": RetinaRelated,
        "retina_labels": RETINA_RELATED_LABELS,
    }


def _list_scope(current: User, ctx: TenantContext) -> tuple[str | None, int | None, int | None]:
    """Return (institution_id, center_id, surgeon_id) filters for list views."""
    inst = scope_institution(ctx)
    center_id = scope_center_id(ctx)
    if current.role == UserRole.SURGEON.value:
        return inst, center_id, current.id
    return inst, center_id, None


@router.get("", response_class=HTMLResponse)
def reinterventions_list(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    status_filter: Annotated[str, Query(alias="status")] = "",
):
    inst, center_id, surgeon_id = _list_scope(current, ctx)
    items = list_reinterventions(
        db,
        institution_id=inst,
        center_id=center_id,
        surgeon_id=surgeon_id,
        status=status_filter or None,
        pending_only=False,
    )
    return templates.TemplateResponse(
        request,
        "reinterventions/list.html",
        {
            "user": current,
            "items": items,
            "flashes": pop_flashes(request),
            "status_filter": status_filter,
            **_form_labels(),
            "page_title": "Reintervenciones",
        },
    )


@router.get("/pending", response_class=HTMLResponse)
def reinterventions_pending(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    inst, center_id, surgeon_id = _list_scope(current, ctx)
    items = list_reinterventions(
        db,
        institution_id=inst,
        center_id=center_id,
        surgeon_id=surgeon_id,
        pending_only=True,
    )
    return templates.TemplateResponse(
        request,
        "reinterventions/list.html",
        {
            "user": current,
            "items": items,
            "flashes": pop_flashes(request),
            "status_filter": "pending",
            **_form_labels(),
            "page_title": "Pendientes de reintervención",
        },
    )


@router.get("/new", response_class=HTMLResponse)
def reintervention_new_form(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
    surgery_id: Annotated[int | None, Query()] = None,
):
    surgery = get_surgery_detail(db, surgery_id) if surgery_id else None
    if surgery_id and surgery is None:
        flash(request, "Cirugía no encontrada.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    if surgery:
        assert_surgery_access(current, surgery)
    elif current.role == UserRole.SURGEON.value:
        flash(request, "Indique la cirugía para registrar el seguimiento.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "reinterventions/form.html",
        {
            "user": current,
            "surgery": surgery,
            "follow_up": None,
            "flashes": pop_flashes(request),
            **_form_labels(),
        },
    )


@router.post("/new")
def reintervention_create(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
    surgery_id: Annotated[int, Form()],
    reintervention_required: Annotated[str, Form()],
    status_value: Annotated[str, Form(alias="status")],
    reintervention_type: Annotated[str, Form()] = "unspecified",
    retina_related: Annotated[str, Form()] = "unknown",
    reintervention_date: Annotated[date | None, Form()] = None,
    notes: Annotated[str, Form()] = "",
):
    surgery = get_surgery_detail(db, surgery_id)
    if surgery is None:
        flash(request, "Cirugía no encontrada.", "danger")
        return RedirectResponse("/surgeries", status_code=status.HTTP_303_SEE_OTHER)
    assert_surgery_access(current, surgery)
    try:
        create_reintervention(
            db,
            surgery,
            actor=current,
            reintervention_required=reintervention_required,
            reintervention_date=reintervention_date,
            reintervention_type=reintervention_type,
            retina_related=retina_related,
            status=status_value,
            notes=notes,
        )
    except ReinterventionValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            f"/reinterventions/new?surgery_id={surgery_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Seguimiento de reintervención registrado.", "success")
    return RedirectResponse(f"/surgeries/{surgery_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{follow_up_id}/edit", response_class=HTMLResponse)
def reintervention_edit_form(
    follow_up_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
):
    fu = get_reintervention(db, follow_up_id)
    if fu is None or fu.is_voided:
        flash(request, "Seguimiento no encontrado.", "danger")
        return RedirectResponse("/reinterventions", status_code=status.HTTP_303_SEE_OTHER)
    assert_surgery_access(current, fu.surgery)
    return templates.TemplateResponse(
        request,
        "reinterventions/form.html",
        {
            "user": current,
            "surgery": fu.surgery,
            "follow_up": fu,
            "flashes": pop_flashes(request),
            **_form_labels(),
        },
    )


@router.post("/{follow_up_id}/edit")
def reintervention_edit_submit(
    follow_up_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
    reintervention_required: Annotated[str, Form()],
    status_value: Annotated[str, Form(alias="status")],
    reintervention_type: Annotated[str, Form()] = "unspecified",
    retina_related: Annotated[str, Form()] = "unknown",
    reintervention_date: Annotated[date | None, Form()] = None,
    notes: Annotated[str, Form()] = "",
):
    fu = get_reintervention(db, follow_up_id)
    if fu is None:
        flash(request, "Seguimiento no encontrado.", "danger")
        return RedirectResponse("/reinterventions", status_code=status.HTTP_303_SEE_OTHER)
    assert_surgery_access(current, fu.surgery)
    try:
        update_reintervention(
            db,
            fu,
            actor=current,
            reintervention_required=reintervention_required,
            reintervention_date=reintervention_date,
            reintervention_type=reintervention_type,
            retina_related=retina_related,
            status=status_value,
            notes=notes,
        )
    except ReinterventionValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            f"/reinterventions/{follow_up_id}/edit",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Seguimiento actualizado.", "success")
    return RedirectResponse(f"/surgeries/{fu.surgery_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{follow_up_id}/void")
def reintervention_void(
    follow_up_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: OpsDep,
    void_reason: Annotated[str, Form()] = "",
):
    fu = get_reintervention(db, follow_up_id)
    if fu is None:
        flash(request, "Seguimiento no encontrado.", "danger")
        return RedirectResponse("/reinterventions", status_code=status.HTTP_303_SEE_OTHER)
    assert_surgery_access(current, fu.surgery)
    try:
        void_reintervention(db, fu, actor=current, void_reason=void_reason)
    except ReinterventionValidationError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            f"/reinterventions/{follow_up_id}/edit",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Seguimiento anulado (conservado en auditoría).", "success")
    return RedirectResponse(f"/surgeries/{fu.surgery_id}", status_code=status.HTTP_303_SEE_OTHER)
