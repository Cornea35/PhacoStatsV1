"""Shared Jinja templates with center-switcher context for all pages."""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates


def _branding_context(request: Request) -> dict:
    return {
        "theme": getattr(request.state, "theme", None),
        "brand_css": getattr(request.state, "brand_css", "") or "",
        "switchable_centers": getattr(request.state, "switchable_centers", None) or [],
        "can_switch_center": bool(getattr(request.state, "can_switch_center", False)),
        "active_center": getattr(request.state, "active_center", None),
        "view_all_centers": bool(getattr(request.state, "view_all_centers", False)),
    }


templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[_branding_context],
)
