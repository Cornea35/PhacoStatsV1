"""Operational / clinical dashboard routes."""

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.constants import REINTERVENTION_STATUS_LABELS, UserRole
from app.database import get_db
from app.deps import pop_flashes, require_roles
from app.models import User
from app.permissions import institution_scope, is_coordinator
from app.services.dashboard import compute_dashboard
from app.services.date_range import Period, current_and_previous_month, resolve_date_range
from app.services.ops_dashboard import compute_ops_dashboard

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

StaffUser = Annotated[
    User,
    Depends(require_roles(UserRole.SURGEON, UserRole.COORDINATOR, UserRole.ADMIN)),
]


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: StaffUser,
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
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

    if is_coordinator(current):
        ops = compute_ops_dashboard(
            db,
            institution_id=institution_scope(current),
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

    surgeon_id = current.id if current.role == UserRole.SURGEON.value else None
    stats = compute_dashboard(
        db,
        surgeon_id=surgeon_id,
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
            "scoped": surgeon_id is not None,
            "is_admin": current.role == UserRole.ADMIN.value,
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
