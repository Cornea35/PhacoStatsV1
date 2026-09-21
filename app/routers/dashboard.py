"""Operational / clinical dashboard routes."""

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.constants import REINTERVENTION_STATUS_LABELS, UserRole
from app.database import get_db
from app.deps import pop_flashes, require_roles
from app.models import User
from app.permissions import (
    TenantContext,
    get_tenant_context,
    is_coordinator,
    scope_center_id,
    scope_institution,
)
from app.services.dashboard import compute_dashboard
from app.services.date_range import Period, current_and_previous_month, resolve_date_range
from app.services.ops_dashboard import compute_ops_dashboard
from app.services.refractive import list_active_surgeons
from app.templating import templates

router = APIRouter(tags=["dashboard"])

StaffUser = Annotated[
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


def _optional_int(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffUser,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    surgeon_id: Annotated[str | None, Query()] = None,
):
    selected_surgeon_id = _optional_int(surgeon_id)
    resolved_from, resolved_to, period, month_value, range_label = resolve_date_range(
        period=period,
        month=month,
        date_from=date_from,
        date_to=date_to,
    )
    current_month, prev_month = current_and_previous_month()
    range_ctx = {
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
    }
    inst = scope_institution(ctx)
    center_id = scope_center_id(ctx)

    if is_coordinator(current):
        ops = compute_ops_dashboard(
            db,
            institution_id=inst,
            center_id=center_id,
            date_from=resolved_from,
            date_to=resolved_to,
        )
        return templates.TemplateResponse(
            request,
            "dashboard_ops.html",
            {
                "user": current,
                "ops": ops,
                "status_labels": REINTERVENTION_STATUS_LABELS,
                "flashes": pop_flashes(request),
                **range_ctx,
            },
        )

    is_admin = current.role in {
        UserRole.GENERAL_ADMIN.value,
        UserRole.CENTER_ADMIN.value,
    }
    surgeons = list_active_surgeons(db) if is_admin else []
    filter_surgeon_id: int | None = None
    filter_surgeon_name: str | None = None

    if current.role == UserRole.SURGEON.value:
        scoped_surgeon_id = current.id
    elif is_admin and selected_surgeon_id is not None:
        match = next((s for s in surgeons if s.id == selected_surgeon_id), None)
        if match is not None:
            scoped_surgeon_id = match.id
            filter_surgeon_id = match.id
            filter_surgeon_name = match.full_name
        else:
            scoped_surgeon_id = None
    else:
        scoped_surgeon_id = None

    stats = compute_dashboard(
        db,
        surgeon_id=scoped_surgeon_id,
        institution_id=inst,
        center_id=center_id,
        date_from=resolved_from,
        date_to=resolved_to,
    )
    chart_payload = {
        "monthly": {
            "labels": stats.monthly_labels,
            "surgeries": stats.monthly_surgeries,
            "complications": stats.monthly_complications,
        },
        "surgeons": {
            "labels": stats.surgeon_labels,
            "totals": stats.surgeon_totals,
            "complications": stats.surgeon_complications,
        },
        "stages": {
            "labels": stats.stage_labels,
            "counts": stats.stage_counts,
        },
        "types": {
            "labels": stats.type_labels,
            "counts": stats.type_counts,
        },
        "risks": {
            "labels": stats.risk_labels,
            "counts": stats.risk_counts,
            "pct": stats.risk_pct,
        },
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": current,
            "stats": stats,
            "chart_json": json.dumps(chart_payload),
            "flashes": pop_flashes(request),
            "scoped": scoped_surgeon_id is not None,
            "is_admin": is_admin,
            "surgeons": surgeons,
            "filter_surgeon_id": filter_surgeon_id,
            "filter_surgeon_name": filter_surgeon_name,
            **range_ctx,
        },
    )


@router.get("/dashboard/refractive/export.xlsx")
@router.get("/dashboard/refractive/export.csv")
@router.get("/dashboard/refractive/export.pdf")
def legacy_refractive_export_redirect(request: Request):
    target = request.url.path.replace("/dashboard/refractive/", "/refractive/")
    qs = request.url.query
    url = f"{target}?{qs}" if qs else target
    return RedirectResponse(url, status_code=307)
