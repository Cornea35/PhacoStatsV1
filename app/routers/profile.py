"""Simple profile page (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.constants import ROLE_LABELS
from app.deps import get_current_user, pop_flashes
from app.models import User

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    current: Annotated[User, Depends(get_current_user)],
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
