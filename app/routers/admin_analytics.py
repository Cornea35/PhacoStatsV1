"""Advanced Analytics routes (ADMIN only)."""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.constants import UserRole
from app.database import get_db
from app.deps import pop_flashes, require_roles
from app.models import User
from app.permissions import TenantContext, get_tenant_context, scope_center_id, scope_institution
from app.services.date_range import Period, current_and_previous_month, resolve_date_range
from app.statistics.analytics import build_advanced_analytics
from app.statistics.export import build_analytics_workbook
from app.templating import templates

router = APIRouter(prefix="/admin/analytics", tags=["advanced-analytics"])

AdminDep = Annotated[
    User,
    Depends(require_roles(UserRole.GENERAL_ADMIN, UserRole.CENTER_ADMIN)),
]


def _bundle(
    db: Session,
    *,
    period: Period,
    month: str | None,
    date_from: date | None,
    date_to: date | None,
    planned_cases: int,
    max_difference: int,
    institution_id: str | None,
    center_id: int | None,
):
    resolved_from, resolved_to, period, month_value, range_label = resolve_date_range(
        period=period,
        month=month,
        date_from=date_from,
        date_to=date_to,
    )
    bundle = build_advanced_analytics(
        db,
        date_from=resolved_from,
        date_to=resolved_to,
        planned_cases=planned_cases,
        max_difference=max_difference,
        institution_id=institution_id,
        center_id=center_id,
    )
    return bundle, resolved_from, resolved_to, period, month_value, range_label


@router.get("", response_class=HTMLResponse)
def advanced_analytics_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: AdminDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    planned_cases: Annotated[int, Query(ge=0, le=1000)] = 20,
    max_difference: Annotated[int, Query(ge=0, le=100)] = 3,
):
    inst = scope_institution(ctx)
    center_id = scope_center_id(ctx)
    bundle, resolved_from, resolved_to, period, month_value, range_label = _bundle(
        db,
        period=period,
        month=month,
        date_from=date_from,
        date_to=date_to,
        planned_cases=planned_cases,
        max_difference=max_difference,
        institution_id=inst,
        center_id=center_id,
    )
    current_month, prev_month = current_and_previous_month()
    chart_payload = {
        "distribution": {
            "labels": [row.surgeon_name for row in bundle.distribution],
            "cases": [row.suggested_cases for row in bundle.distribution],
        },
        "riskFactors": {
            "labels": [row.label for row in bundle.risk_factors],
            "counts": [row.cases for row in bundle.risk_factors],
            "cumulative": [row.cumulative_pct for row in bundle.risk_factors],
        },
        "reinterventionTypes": {
            "labels": [row.label for row in bundle.reintervention_types],
            "counts": [row.count for row in bundle.reintervention_types],
        },
    }
    return templates.TemplateResponse(
        request,
        "admin/analytics.html",
        {
            "user": current,
            "flashes": pop_flashes(request),
            "bundle": bundle,
            "summary": bundle.summary,
            "surgeon_rows": bundle.surgeon_rows,
            "distribution": bundle.distribution,
            "risk_factors": bundle.risk_factors,
            "reintervention_types": bundle.reintervention_types,
            "reintervention_total": sum(r.count for r in bundle.reintervention_types),
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
            "planned_cases": planned_cases,
            "max_difference": max_difference,
            "chart_json": json.dumps(chart_payload),
        },
    )


@router.get("/export")
def export_analytics_excel(
    db: Annotated[Session, Depends(get_db)],
    current: AdminDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    planned_cases: Annotated[int, Query(ge=0, le=1000)] = 20,
    max_difference: Annotated[int, Query(ge=0, le=100)] = 3,
):
    bundle, *_rest = _bundle(
        db,
        period=period,
        month=month,
        date_from=date_from,
        date_to=date_to,
        planned_cases=planned_cases,
        max_difference=max_difference,
        institution_id=scope_institution(ctx),
        center_id=scope_center_id(ctx),
    )
    payload = build_analytics_workbook(bundle)
    filename = "phacostats_advanced_analytics.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
