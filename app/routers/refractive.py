"""Refractive results page and exports (separate from operational dashboard)."""

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.constants import DEFAULT_INSTITUTION_CODE, IOL_TYPE_OPTIONS, EyeSide, UserRole
from app.database import get_db
from app.deps import pop_flashes, require_roles
from app.models import User
from app.permissions import TenantContext, get_tenant_context, scope_center_id, scope_institution
from app.services.date_range import Period, current_and_previous_month, resolve_date_range
from app.services.refractive import (
    RefractiveResults,
    VisitWindow,
    compute_refractive_results,
    list_active_surgeons,
)
from app.statistics.refractive_export import (
    export_refractive_csv,
    export_refractive_pdf,
    export_refractive_xlsx,
)
from app.templating import templates

router = APIRouter(prefix="/refractive", tags=["refractive"])

StaffUser = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.SURGEON,
            UserRole.GENERAL_ADMIN,
            UserRole.CENTER_ADMIN,
            UserRole.SUPERVISOR,
        )
    ),
]


def _optional_int(value: str | int | None) -> int | None:
    """Coerce query ints; empty strings become None (avoids FastAPI 422)."""
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


def _refractive_for_request(
    db: Session,
    current: User,
    *,
    period: Period,
    month: str | None,
    date_from: date | None,
    date_to: date | None,
    rx_window: VisitWindow,
    rx_iol: str | None,
    rx_eye: str | None,
    rx_surgeon: int | None,
    rx_institution: str | None,
    rx_from: date | None,
    rx_to: date | None,
    institution_id: str | None = None,
    center_id: int | None = None,
) -> tuple[RefractiveResults, date | None, date | None, Period, str | None, str]:
    surgeon_id = current.id if current.role == UserRole.SURGEON.value else None
    resolved_from, resolved_to, period, month_value, range_label = resolve_date_range(
        period=period,
        month=month,
        date_from=date_from,
        date_to=date_to,
    )
    rx_surgeon_id = surgeon_id
    if current.role != UserRole.SURGEON.value and rx_surgeon is not None:
        rx_surgeon_id = rx_surgeon
    # Session center scope wins; optional rx_institution only when viewing all centers
    effective_inst = institution_id
    effective_center = center_id
    if effective_center is None and effective_inst is None and rx_institution:
        effective_inst = rx_institution
    refractive = compute_refractive_results(
        db,
        surgeon_id=rx_surgeon_id,
        institution_id=effective_inst,
        center_id=effective_center,
        eye=rx_eye or None,
        iol_type=rx_iol or None,
        visit_window=rx_window,
        date_from=rx_from if rx_window == "custom" else None,
        date_to=rx_to if rx_window == "custom" else None,
        surgery_date_from=resolved_from,
        surgery_date_to=resolved_to,
    )
    return refractive, resolved_from, resolved_to, period, month_value, range_label


def _common_query(
    *,
    period: Period = "all",
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    rx_window: VisitWindow = "last_visit",
    rx_iol: str | None = None,
    rx_eye: str | None = None,
    rx_surgeon: str | None = None,
    rx_institution: str | None = None,
    rx_from: date | None = None,
    rx_to: date | None = None,
) -> dict:
    return {
        "period": period,
        "month": month,
        "date_from": date_from,
        "date_to": date_to,
        "rx_window": rx_window,
        "rx_iol": rx_iol,
        "rx_eye": rx_eye,
        "rx_surgeon": _optional_int(rx_surgeon),
        "rx_institution": rx_institution,
        "rx_from": rx_from,
        "rx_to": rx_to,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def refractive_results_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffUser,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    rx_window: Annotated[VisitWindow, Query()] = "last_visit",
    rx_iol: Annotated[str | None, Query()] = None,
    rx_eye: Annotated[str | None, Query()] = None,
    rx_surgeon: Annotated[str | None, Query()] = None,
    rx_institution: Annotated[str | None, Query()] = None,
    rx_from: Annotated[date | None, Query()] = None,
    rx_to: Annotated[date | None, Query()] = None,
):
    selected_surgeon = _optional_int(rx_surgeon)
    surgeon_id = current.id if current.role == UserRole.SURGEON.value else None
    refractive, resolved_from, resolved_to, period, month_value, range_label = _refractive_for_request(
        db,
        current,
        period=period,
        month=month,
        date_from=date_from,
        date_to=date_to,
        rx_window=rx_window,
        rx_iol=rx_iol,
        rx_eye=rx_eye,
        rx_surgeon=selected_surgeon,
        rx_institution=rx_institution,
        rx_from=rx_from,
        rx_to=rx_to,
        institution_id=scope_institution(ctx),
        center_id=scope_center_id(ctx),
    )
    refractive_payload = refractive.to_dict()
    refractive_payload.pop("rows", None)
    current_month, prev_month = current_and_previous_month()
    scoped_inst = scope_institution(ctx) or rx_institution or DEFAULT_INSTITUTION_CODE
    surgeons = (
        list_active_surgeons(db, institution_id=scope_institution(ctx))
        if current.role != UserRole.SURGEON.value
        else []
    )

    return templates.TemplateResponse(
        request,
        "refractive/results.html",
        {
            "user": current,
            "refractive": refractive,
            "refractive_json": json.dumps(refractive_payload),
            "flashes": pop_flashes(request),
            "scoped": surgeon_id is not None,
            "period": period,
            "month_value": month_value or current_month,
            "date_from_value": (
                resolved_from.isoformat()
                if resolved_from and period == "custom"
                else (date_from.isoformat() if date_from else "")
            ),
            "date_to_value": (
                resolved_to.isoformat()
                if resolved_to and period == "custom"
                else (date_to.isoformat() if date_to else "")
            ),
            "range_label": range_label,
            "current_month": current_month,
            "prev_month": prev_month,
            "iol_types": IOL_TYPE_OPTIONS,
            "eyes": EyeSide,
            "surgeons": surgeons,
            "rx_window": rx_window,
            "rx_iol": rx_iol or "",
            "rx_eye": rx_eye or "",
            "rx_surgeon": selected_surgeon or "",
            "rx_institution": scoped_inst,
            "rx_from": rx_from.isoformat() if rx_from else "",
            "rx_to": rx_to.isoformat() if rx_to else "",
            "default_institution": DEFAULT_INSTITUTION_CODE,
        },
    )


def _export_results(
    db: Session,
    current: User,
    ctx: TenantContext,
    **kwargs,
) -> RefractiveResults:
    refractive, *_ = _refractive_for_request(
        db,
        current,
        institution_id=scope_institution(ctx),
        center_id=scope_center_id(ctx),
        **kwargs,
    )
    return refractive


@router.get("/export.xlsx")
def export_xlsx(
    db: Annotated[Session, Depends(get_db)],
    current: StaffUser,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    rx_window: Annotated[VisitWindow, Query()] = "last_visit",
    rx_iol: Annotated[str | None, Query()] = None,
    rx_eye: Annotated[str | None, Query()] = None,
    rx_surgeon: Annotated[str | None, Query()] = None,
    rx_institution: Annotated[str | None, Query()] = None,
    rx_from: Annotated[date | None, Query()] = None,
    rx_to: Annotated[date | None, Query()] = None,
):
    results = _export_results(
        db,
        current,
        ctx,
        **_common_query(
            period=period,
            month=month,
            date_from=date_from,
            date_to=date_to,
            rx_window=rx_window,
            rx_iol=rx_iol,
            rx_eye=rx_eye,
            rx_surgeon=rx_surgeon,
            rx_institution=rx_institution,
            rx_from=rx_from,
            rx_to=rx_to,
        ),
    )
    return Response(
        content=export_refractive_xlsx(results),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=phacostats_refractive.xlsx"},
    )


@router.get("/export.csv")
def export_csv(
    db: Annotated[Session, Depends(get_db)],
    current: StaffUser,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    rx_window: Annotated[VisitWindow, Query()] = "last_visit",
    rx_iol: Annotated[str | None, Query()] = None,
    rx_eye: Annotated[str | None, Query()] = None,
    rx_surgeon: Annotated[str | None, Query()] = None,
    rx_institution: Annotated[str | None, Query()] = None,
    rx_from: Annotated[date | None, Query()] = None,
    rx_to: Annotated[date | None, Query()] = None,
):
    results = _export_results(
        db,
        current,
        ctx,
        **_common_query(
            period=period,
            month=month,
            date_from=date_from,
            date_to=date_to,
            rx_window=rx_window,
            rx_iol=rx_iol,
            rx_eye=rx_eye,
            rx_surgeon=rx_surgeon,
            rx_institution=rx_institution,
            rx_from=rx_from,
            rx_to=rx_to,
        ),
    )
    return Response(
        content=export_refractive_csv(results),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=phacostats_refractive.csv"},
    )


@router.get("/export.pdf")
def export_pdf(
    db: Annotated[Session, Depends(get_db)],
    current: StaffUser,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    rx_window: Annotated[VisitWindow, Query()] = "last_visit",
    rx_iol: Annotated[str | None, Query()] = None,
    rx_eye: Annotated[str | None, Query()] = None,
    rx_surgeon: Annotated[str | None, Query()] = None,
    rx_institution: Annotated[str | None, Query()] = None,
    rx_from: Annotated[date | None, Query()] = None,
    rx_to: Annotated[date | None, Query()] = None,
):
    results = _export_results(
        db,
        current,
        ctx,
        **_common_query(
            period=period,
            month=month,
            date_from=date_from,
            date_to=date_to,
            rx_window=rx_window,
            rx_iol=rx_iol,
            rx_eye=rx_eye,
            rx_surgeon=rx_surgeon,
            rx_institution=rx_institution,
            rx_from=rx_from,
            rx_to=rx_to,
        ),
    )
    return Response(
        content=export_refractive_pdf(results),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=phacostats_refractive.pdf"},
    )
