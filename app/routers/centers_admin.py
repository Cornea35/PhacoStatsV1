"""General admin: centers, branding upload, audit; center admin: registrations."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.constants import ASSIGNABLE_CENTER_ROLES, ROLE_LABELS, UserRole
from app.database import get_db
from app.deps import flash, pop_flashes, require_roles
from app.models import (
    AuditLog,
    Center,
    CenterBranding,
    CenterMembership,
    RegistrationRequest,
    User,
)
from app.permissions import SESSION_CENTER_ALL, SESSION_CENTER_KEY, TenantContext, get_tenant_context, normalize_role
from app.security import hash_password
from app.services.audit import write_audit
from app.services.branding import get_theme_for_center, list_active_centers, theme_from_branding
from app.templating import templates

router = APIRouter(tags=["centers-admin"])
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"


def _safe_next_url(next_url: str | None) -> str:
    if not next_url:
        return "/dashboard"
    candidate = next_url.strip()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return "/dashboard"


def _save_upload(file: UploadFile | None, prefix: str) -> str | None:
    if file is None or not file.filename:
        return None
    ext = Path(file.filename).suffix.lower()
    if ext not in {".png", ".svg", ".jpg", ".jpeg", ".webp"}:
        return None
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{uuid.uuid4().hex[:10]}{ext}"
    dest = UPLOAD_DIR / name
    dest.write_bytes(file.file.read())
    return name


@router.get("/admin/centers", response_class=HTMLResponse)
def list_centers(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.GENERAL_ADMIN))],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    centers = db.query(Center).order_by(Center.short_name).all()
    return templates.TemplateResponse(
        request,
        "admin/centers.html",
        {
            "user": current,
            "centers": centers,
            "theme": get_theme_for_center(db, ctx.center_id),
            "brand_css": get_theme_for_center(db, ctx.center_id).css_variables(),
            "flashes": pop_flashes(request),
        },
    )


@router.post("/admin/centers/new")
def create_center(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.GENERAL_ADMIN))],
    code: Annotated[str, Form()],
    short_name: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    primary_color: Annotated[str, Form()] = "#0b5ea8",
    secondary_color: Annotated[str, Form()] = "#084a86",
    accent_color: Annotated[str, Form()] = "#c9a227",
):
    code_n = re.sub(r"[^A-Za-z0-9_]", "", code.strip().upper())[:32]
    if not code_n or db.query(Center).filter(Center.code == code_n).first():
        flash(request, "Código de centro inválido o duplicado.", "danger")
        return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)
    center = Center(
        code=code_n,
        short_name=short_name.strip(),
        full_name=full_name.strip(),
        is_active=True,
        branding=CenterBranding(
            short_name=short_name.strip(),
            full_name=full_name.strip(),
            primary_color=primary_color,
            secondary_color=secondary_color,
            accent_color=accent_color,
            placeholder=short_name.strip(),
            show_powered_by=True,
        ),
    )
    db.add(center)
    db.flush()
    write_audit(
        db,
        action="center_created",
        entity_type="center",
        entity_id=center.id,
        actor_user_id=current.id,
        center_id=center.id,
        after={"code": code_n, "short_name": short_name},
    )
    db.commit()
    flash(request, "Centro creado.", "success")
    return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/centers/{center_id}/branding")
async def update_branding(
    center_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.GENERAL_ADMIN))],
    short_name: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    primary_color: Annotated[str, Form()],
    secondary_color: Annotated[str, Form()],
    accent_color: Annotated[str, Form()],
    show_powered_by: Annotated[str | None, Form()] = None,
    logo: UploadFile | None = File(None),
    logo_dark: UploadFile | None = File(None),
):
    center = db.get(Center, center_id)
    if not center:
        flash(request, "Centro no encontrado.", "danger")
        return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)
    branding = center.branding or CenterBranding(center_id=center.id)
    before = {"primary": branding.primary_color, "short_name": branding.short_name}
    branding.short_name = short_name.strip()
    branding.full_name = full_name.strip()
    branding.primary_color = primary_color
    branding.secondary_color = secondary_color
    branding.accent_color = accent_color
    branding.show_powered_by = show_powered_by == "on"
    logo_path = _save_upload(logo, f"logo_{center.code}")
    dark_path = _save_upload(logo_dark, f"logo_dark_{center.code}")
    if logo_path:
        branding.logo_path = logo_path
        branding.placeholder_label = None
    if dark_path:
        branding.logo_dark_path = dark_path
    if center.branding is None:
        db.add(branding)
    center.short_name = short_name.strip()
    center.full_name = full_name.strip()
    write_audit(
        db,
        action="branding_updated",
        entity_type="center_branding",
        entity_id=center.id,
        actor_user_id=current.id,
        center_id=center.id,
        before=before,
        after={"primary": primary_color, "short_name": short_name},
    )
    db.commit()
    flash(request, "Identidad visual actualizada.", "success")
    return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/centers/{center_id}/admins")
def create_center_admin(
    center_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.GENERAL_ADMIN))],
    username: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
):
    center = db.get(Center, center_id)
    if not center:
        flash(request, "Centro no encontrado.", "danger")
        return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)
    uname = username.strip().lower()
    if db.query(User).filter(User.username == uname).first():
        flash(request, "Usuario ya existe.", "danger")
        return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)
    user = User(
        username=uname,
        email=email.strip().lower() or None,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=UserRole.CENTER_ADMIN.value,
        institution_id=center.code,
        account_status="active",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        CenterMembership(
            user_id=user.id,
            center_id=center.id,
            role=UserRole.CENTER_ADMIN.value,
            is_active=True,
        )
    )
    write_audit(
        db,
        action="center_admin_created",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current.id,
        center_id=center.id,
        after={"username": uname, "role": "center_admin"},
    )
    db.commit()
    flash(request, "Administrador de centro creado.", "success")
    return RedirectResponse("/admin/centers", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/active-center")
def switch_active_center(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.GENERAL_ADMIN))],
    center_id: Annotated[str, Form()],
    next: Annotated[str | None, Form()] = None,
):
    redirect_to = _safe_next_url(next)
    raw = (center_id or "").strip().lower()
    if raw in {SESSION_CENTER_ALL, "0", ""}:
        request.session[SESSION_CENTER_KEY] = SESSION_CENTER_ALL
        write_audit(
            db,
            action="switch_active_center",
            entity_type="center",
            entity_id=None,
            actor_user_id=current.id,
            center_id=None,
            after={"mode": "all"},
        )
        db.commit()
        flash(request, "Vista: todos los centros", "success")
        return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)

    try:
        cid = int(raw)
    except (TypeError, ValueError):
        flash(request, "Centro no válido.", "danger")
        return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)

    center = db.get(Center, cid)
    if not center:
        flash(request, "Centro no encontrado.", "danger")
        return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)
    request.session[SESSION_CENTER_KEY] = center.id
    write_audit(
        db,
        action="switch_active_center",
        entity_type="center",
        entity_id=center.id,
        actor_user_id=current.id,
        center_id=center.id,
    )
    db.commit()
    flash(request, f"Centro activo: {center.short_name}", "success")
    return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/audit", response_class=HTMLResponse)
def audit_log_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[User, Depends(require_roles(UserRole.GENERAL_ADMIN))],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    theme = get_theme_for_center(db, ctx.center_id)
    return templates.TemplateResponse(
        request,
        "admin/audit.html",
        {
            "user": current,
            "rows": rows,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
        },
    )


@router.get("/admin/registrations", response_class=HTMLResponse)
def registrations_list(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[
        User,
        Depends(require_roles(UserRole.GENERAL_ADMIN, UserRole.CENTER_ADMIN)),
    ],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    q = db.query(RegistrationRequest).filter(RegistrationRequest.status == "pending")
    if not ctx.is_general_admin:
        q = q.filter(RegistrationRequest.center_id == ctx.center_id)
    rows = q.order_by(RegistrationRequest.created_at.desc()).all()
    theme = get_theme_for_center(db, ctx.center_id)
    return templates.TemplateResponse(
        request,
        "admin/registrations.html",
        {
            "user": current,
            "rows": rows,
            "assignable_roles": ASSIGNABLE_CENTER_ROLES,
            "role_labels": ROLE_LABELS,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
        },
    )


@router.post("/admin/registrations/{req_id}/decide")
def decide_registration(
    req_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[
        User,
        Depends(require_roles(UserRole.GENERAL_ADMIN, UserRole.CENTER_ADMIN)),
    ],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    decision: Annotated[str, Form()],
    role: Annotated[str, Form()] = UserRole.SURGEON.value,
    reason: Annotated[str, Form()] = "",
):
    req = db.get(RegistrationRequest, req_id)
    if req is None:
        flash(request, "Solicitud no encontrada.", "danger")
        return RedirectResponse("/admin/registrations", status_code=status.HTTP_303_SEE_OTHER)
    if not ctx.is_general_admin and req.center_id != ctx.center_id:
        flash(request, "No puede gestionar solicitudes de otro centro.", "danger")
        return RedirectResponse("/admin/registrations", status_code=status.HTTP_303_SEE_OTHER)

    if decision == "reject":
        req.status = "rejected"
        req.decided_at = datetime.now(timezone.utc)
        req.decided_by_id = current.id
        req.decision_reason = reason.strip() or None
        write_audit(
            db,
            action="registration_rejected",
            entity_type="registration_request",
            entity_id=req.id,
            actor_user_id=current.id,
            center_id=req.center_id,
            after={"reason": reason},
        )
        db.commit()
        flash(request, "Solicitud rechazada.", "info")
        return RedirectResponse("/admin/registrations", status_code=status.HTTP_303_SEE_OTHER)

    role_n = normalize_role(role)
    if role_n not in ASSIGNABLE_CENTER_ROLES:
        flash(request, "No puede asignar ese rol.", "danger")
        return RedirectResponse("/admin/registrations", status_code=status.HTTP_303_SEE_OTHER)

    center = db.get(Center, req.center_id)
    user = User(
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        password_hash=req.password_hash,
        role=role_n,
        institution_id=center.code if center else "CODET",
        specialty=req.specialty,
        training_level=req.training_level,
        professional_id=req.professional_id,
        account_status="active",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        CenterMembership(
            user_id=user.id,
            center_id=req.center_id,
            role=role_n,
            is_active=True,
        )
    )
    req.status = "active"
    req.decided_at = datetime.now(timezone.utc)
    req.decided_by_id = current.id
    req.created_user_id = user.id
    write_audit(
        db,
        action="registration_approved",
        entity_type="registration_request",
        entity_id=req.id,
        actor_user_id=current.id,
        center_id=req.center_id,
        after={"user_id": user.id, "role": role_n},
    )
    db.commit()
    flash(request, "Solicitud aprobada y usuario activado.", "success")
    return RedirectResponse("/admin/registrations", status_code=status.HTTP_303_SEE_OTHER)
