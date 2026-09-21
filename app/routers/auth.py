"""Auth: login with center branding, registration, password recovery."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import TRAINING_LEVEL_OPTIONS, UserRole
from app.database import get_db
from app.deps import flash, get_current_user_optional, pop_flashes
from app.migrations.multicenter import ensure_default_centers
from app.models import Center, CenterMembership, RegistrationRequest, User
from app.permissions import SESSION_CENTER_KEY, normalize_role
from app.security import create_session_token, hash_password, verify_password
from app.services.audit import write_audit
from app.services.branding import get_theme_for_code, list_active_centers, theme_from_branding

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()

# In-process reset tokens (MVP). Prefer center_admin reset in production.
_RESET_TOKENS: dict[str, tuple[int, datetime]] = {}


def _find_user(db: Session, login: str) -> User | None:
    key = login.strip().lower()
    return (
        db.query(User)
        .filter((User.username == key) | (User.email == key))
        .first()
    )


@router.get("/api/centers/{code}/branding")
def center_branding_api(code: str, db: Annotated[Session, Depends(get_db)]):
    ensure_default_centers(db)
    theme = get_theme_for_code(db, code)
    return JSONResponse(
        {
            "code": theme.code,
            "short_name": theme.short_name,
            "full_name": theme.full_name,
            "primary": theme.primary,
            "secondary": theme.secondary,
            "accent": theme.accent,
            "text": theme.text,
            "on_primary": theme.on_primary,
            "logo_url": theme.logo_url,
            "placeholder": theme.placeholder,
            "css": theme.css_variables(),
            "show_powered_by": theme.show_powered_by,
        }
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
    center: Annotated[str | None, Query()] = None,
):
    if user and (getattr(user, "account_status", "active") or "active") == "active":
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    ensure_default_centers(db)
    centers = list_active_centers(db)
    selected = center or (centers[0].code if centers else None)
    theme = get_theme_for_code(db, selected)
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "flashes": pop_flashes(request),
            "centers": centers,
            "selected_center": selected,
            "theme": theme,
            "brand_css": theme.css_variables(),
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    center_code: Annotated[str, Form()] = "",
):
    ensure_default_centers(db)
    user = _find_user(db, username)
    if user is None or not verify_password(password, user.password_hash):
        flash(request, "Usuario o contraseña incorrectos.", "danger")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    status_acc = getattr(user, "account_status", "active") or "active"
    if status_acc == "pending":
        flash(
            request,
            "Tu solicitud fue enviada al administrador de tu centro. "
            "Recibirás una notificación cuando tu cuenta sea aprobada.",
            "warning",
        )
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if status_acc != "active" or not user.is_active:
        flash(request, "Cuenta no activa. Contacte al administrador de su centro.", "danger")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    role = normalize_role(user.role)
    center = None
    if center_code:
        center = (
            db.query(Center)
            .filter(Center.code == center_code.strip(), Center.is_active.is_(True))
            .first()
        )
    if role != UserRole.GENERAL_ADMIN.value:
        memberships = (
            db.query(CenterMembership)
            .filter(CenterMembership.user_id == user.id, CenterMembership.is_active.is_(True))
            .all()
        )
        if not memberships:
            flash(request, "No tiene membresía activa en ningún centro.", "danger")
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if center is None:
            center = db.get(Center, memberships[0].center_id)
        mem = next((m for m in memberships if m.center_id == center.id), None) if center else None
        if mem is None:
            flash(request, "No pertenece al centro seleccionado.", "danger")
            qs = f"?center={center_code}" if center_code else ""
            return RedirectResponse(f"/login{qs}", status_code=status.HTTP_303_SEE_OTHER)
        user.role = normalize_role(mem.role)
        user.institution_id = center.code
    else:
        if center is None:
            center = db.query(Center).filter(Center.code == user.institution_id).first()
        write_audit(
            db,
            action="admin_center_access",
            entity_type="center",
            entity_id=center.id if center else None,
            actor_user_id=user.id,
            center_id=center.id if center else None,
            after={"center": center.code if center else None},
        )

    db.commit()

    token = create_session_token(user.id)
    redirect = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        max_age=settings.session_max_age_seconds,
        samesite="lax",
    )
    # SessionMiddleware may not see request.session mutation after RedirectResponse;
    # set via request before returning.
    if center:
        request.session[SESSION_CENTER_KEY] = center.id
    flash(request, f"Bienvenido/a, {user.full_name}.", "success")
    return redirect


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    center: Annotated[str | None, Query()] = None,
):
    ensure_default_centers(db)
    centers = list_active_centers(db)
    selected = center or (centers[0].code if centers else None)
    theme = get_theme_for_code(db, selected)
    return templates.TemplateResponse(
        request,
        "auth/register.html",
        {
            "flashes": pop_flashes(request),
            "centers": centers,
            "selected_center": selected,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "training_levels": TRAINING_LEVEL_OPTIONS,
        },
    )


@router.post("/register")
def register_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    full_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    center_code: Annotated[str, Form()],
    specialty: Annotated[str, Form()] = "",
    training_level: Annotated[str, Form()] = "na",
    professional_id: Annotated[str, Form()] = "",
    privacy_accepted: Annotated[str | None, Form()] = None,
):
    ensure_default_centers(db)
    if privacy_accepted != "on":
        flash(request, "Debe aceptar el aviso de privacidad.", "danger")
        return RedirectResponse("/register", status_code=status.HTTP_303_SEE_OTHER)
    if len(password) < 6:
        flash(request, "La contraseña debe tener al menos 6 caracteres.", "danger")
        return RedirectResponse("/register", status_code=status.HTTP_303_SEE_OTHER)

    center = (
        db.query(Center)
        .filter(Center.code == center_code.strip(), Center.is_active.is_(True))
        .first()
    )
    if center is None:
        flash(request, "Seleccione un centro válido.", "danger")
        return RedirectResponse("/register", status_code=status.HTTP_303_SEE_OTHER)

    email_n = email.strip().lower()
    username = email_n.split("@")[0][:60]
    base = username
    i = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base}{i}"
        i += 1
    if db.query(User).filter(User.email == email_n).first():
        flash(request, "Ya existe una cuenta con ese correo.", "danger")
        return RedirectResponse("/register", status_code=status.HTTP_303_SEE_OTHER)
    if (
        db.query(RegistrationRequest)
        .filter(
            RegistrationRequest.email == email_n,
            RegistrationRequest.status == "pending",
        )
        .first()
    ):
        flash(request, "Ya hay una solicitud pendiente con ese correo.", "warning")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    req = RegistrationRequest(
        center_id=center.id,
        full_name=full_name.strip(),
        email=email_n,
        username=username,
        password_hash=hash_password(password),
        specialty=specialty.strip() or None,
        training_level=training_level or None,
        professional_id=professional_id.strip() or None,
        privacy_accepted=True,
        status="pending",
    )
    db.add(req)
    db.flush()
    write_audit(
        db,
        action="registration_submitted",
        entity_type="registration_request",
        entity_id=req.id,
        center_id=center.id,
        after={"email": email_n, "center": center.code},
    )
    db.commit()
    flash(
        request,
        "Tu solicitud fue enviada al administrador de tu centro. "
        "Recibirás una notificación cuando tu cuenta sea aprobada.",
        "success",
    )
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recover", response_class=HTMLResponse)
def recover_page(request: Request, db: Annotated[Session, Depends(get_db)]):
    ensure_default_centers(db)
    theme = get_theme_for_code(db, None)
    return templates.TemplateResponse(
        request,
        "auth/recover.html",
        {"flashes": pop_flashes(request), "theme": theme, "brand_css": theme.css_variables()},
    )


@router.post("/recover")
def recover_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    email: Annotated[str, Form()],
):
    user = _find_user(db, email)
    # Always show same message (no account enumeration)
    msg = (
        "Si la cuenta existe, el administrador de su centro puede restablecer el acceso. "
        "En entorno local de desarrollo se genera un enlace de un solo uso."
    )
    if user and settings.debug:
        token = secrets.token_urlsafe(24)
        _RESET_TOKENS[token] = (user.id, datetime.now(timezone.utc) + timedelta(hours=1))
        flash(request, f"{msg} Enlace local: /recover/{token}", "info")
    else:
        flash(request, msg, "info")
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recover/{token}", response_class=HTMLResponse)
def recover_token_page(token: str, request: Request):
    return templates.TemplateResponse(
        request,
        "auth/recover_reset.html",
        {"flashes": pop_flashes(request), "token": token},
    )


@router.post("/recover/{token}")
def recover_token_submit(
    token: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    password: Annotated[str, Form()],
):
    entry = _RESET_TOKENS.get(token)
    if not entry or entry[1] < datetime.now(timezone.utc):
        flash(request, "Enlace inválido o expirado.", "danger")
        return RedirectResponse("/recover", status_code=status.HTTP_303_SEE_OTHER)
    if len(password) < 6:
        flash(request, "La contraseña debe tener al menos 6 caracteres.", "danger")
        return RedirectResponse(f"/recover/{token}", status_code=status.HTTP_303_SEE_OTHER)
    user = db.get(User, entry[0])
    if user:
        user.password_hash = hash_password(password)
        write_audit(
            db,
            action="password_reset",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
        )
        db.commit()
    _RESET_TOKENS.pop(token, None)
    flash(request, "Contraseña actualizada. Ya puede iniciar sesión.", "success")
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    redirect = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(settings.session_cookie_name)
    request.session.pop(SESSION_CENTER_KEY, None)
    flash(request, "Sesión cerrada.", "info")
    return redirect
