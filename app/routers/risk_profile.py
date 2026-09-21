"""Surgical Risk Profile routes (admin analytics + surgeon self view)."""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.constants import UserRole
from app.database import get_db
from app.deps import pop_flashes, require_roles
from app.models import User
from app.permissions import TenantContext, get_tenant_context, scope_center_id, scope_institution
from app.services.branding import get_theme_for_center
from app.services.date_range import Period, resolve_date_range
from app.services.surgical_risk import build_surgical_risk_profile
from app.templating import templates

router = APIRouter(tags=["surgical-risk"])


def _profile_payload(profile):
    def pct(x):
        return None if x is None else round(100 * x, 2)

    return {
        "surgeon_name": profile.surgeon_name,
        "period_label": profile.period_label,
        "model_version": profile.model_version,
        "is_preliminary": profile.is_preliminary,
        "n_cases": profile.n_cases,
        "n_events": profile.n_events,
        "observed_pct": pct(profile.observed_rate),
        "expected_pct": pct(profile.expected_rate),
        "oe_ratio": None if profile.oe_ratio is None else round(profile.oe_ratio, 2),
        "oe_ci": None
        if not profile.oe_ci
        else (round(profile.oe_ci[0], 2), round(profile.oe_ci[1], 2)),
        "center_avg_pct": pct(profile.center_avg_rate),
        "top_factors": [
            {
                "label": f.label,
                "n_cases": f.n_cases,
                "n_events": f.n_events,
                "observed_pct": pct(f.observed_rate),
                "adjusted_pct": pct(f.adjusted_risk),
                "ci": None
                if f.ci_low is None
                else (pct(f.ci_low), pct(f.ci_high)),
                "delta_pct": pct(f.delta_vs_center),
                "sufficient": f.sufficient,
                "status": f.status,
            }
            for f in profile.top_factors
        ],
        "combinations": [
            {
                "label": f.label,
                "n_cases": f.n_cases,
                "n_events": f.n_events,
                "observed_pct": pct(f.observed_rate),
                "adjusted_pct": pct(f.adjusted_risk),
                "sufficient": f.sufficient,
                "status": f.status,
            }
            for f in profile.combinations
        ],
        "better_than_expected": profile.better_than_expected,
        "most_frequent_complication": profile.most_frequent_complication,
        "most_vulnerable_stage": profile.most_vulnerable_stage,
        "recommendations": profile.recommendations,
        "trend": profile.trend,
        "notes": profile.notes,
    }


@router.get("/admin/risk-profile", response_class=HTMLResponse)
def admin_risk_profile(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[
        User,
        Depends(require_roles(UserRole.GENERAL_ADMIN, UserRole.CENTER_ADMIN)),
    ],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    surgeon_id: Annotated[int | None, Query()] = None,
):
    resolved_from, resolved_to, period, month_value, range_label = resolve_date_range(
        period=period, month=month, date_from=date_from, date_to=date_to
    )
    center_id = scope_center_id(ctx)
    institution_code = None if center_id is not None else scope_institution(ctx)

    surgeon_name = "Todos los cirujanos"
    sid = surgeon_id
    if sid:
        u = db.get(User, sid)
        surgeon_name = u.full_name if u else f"Cirujano {sid}"

    profile = build_surgical_risk_profile(
        db,
        center_id=center_id,
        institution_code=institution_code,
        surgeon_id=sid,
        surgeon_name=surgeon_name,
        date_from=resolved_from,
        date_to=resolved_to,
        period_label=range_label,
    )
    theme = get_theme_for_center(db, ctx.center_id)
    surgeons = (
        db.query(User)
        .filter(User.role == UserRole.SURGEON.value, User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/risk_profile.html",
        {
            "user": current,
            "profile": profile,
            "payload": _profile_payload(profile),
            "payload_json": json.dumps(_profile_payload(profile)),
            "surgeons": surgeons,
            "filter_surgeon_id": sid,
            "period": period,
            "month_value": month_value,
            "range_label": range_label,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
            "self_view": False,
        },
    )


@router.get("/my/risk-profile", response_class=HTMLResponse)
def my_risk_profile(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.SURGEON))],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    period: Annotated[Period, Query()] = "all",
    month: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    resolved_from, resolved_to, period, month_value, range_label = resolve_date_range(
        period=period, month=month, date_from=date_from, date_to=date_to
    )
    profile = build_surgical_risk_profile(
        db,
        center_id=ctx.center_id,
        surgeon_id=current.id,
        surgeon_name=current.full_name,
        date_from=resolved_from,
        date_to=resolved_to,
        period_label=range_label,
    )
    theme = get_theme_for_center(db, ctx.center_id)
    return templates.TemplateResponse(
        request,
        "admin/risk_profile.html",
        {
            "user": current,
            "profile": profile,
            "payload": _profile_payload(profile),
            "payload_json": json.dumps(_profile_payload(profile)),
            "surgeons": [],
            "filter_surgeon_id": current.id,
            "period": period,
            "month_value": month_value,
            "range_label": range_label,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
            "self_view": True,
        },
    )
