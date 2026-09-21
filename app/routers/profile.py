"""Simple profile page (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.constants import ROLE_LABELS
from app.deps import pop_flashes, require_roles
from app.models import User
from app.constants import UserRole
from app.permissions import TenantContext, get_tenant_context
from app.templating import templates

router = APIRouter(tags=["profile"])

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


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    current: StaffDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": current,
            "role_label": ROLE_LABELS.get(current.role, current.role),
            "flashes": pop_flashes(request),
        },
    )
