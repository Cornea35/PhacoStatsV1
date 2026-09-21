"""User administration routes (general_admin + center_admin)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.constants import ASSIGNABLE_CENTER_ROLES, ROLE_LABELS, UserRole
from app.database import get_db
from app.deps import flash, pop_flashes, require_roles
from app.models import CenterMembership, Surgery, User
from app.permissions import TenantContext, get_tenant_context, normalize_role
from app.security import hash_password
from app.services.audit import write_audit
from app.services.branding import get_theme_for_center

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

ManagerDep = Annotated[
    User,
    Depends(require_roles(UserRole.GENERAL_ADMIN, UserRole.CENTER_ADMIN)),
]


def _can_manage_target(manager: User, target: User, ctx: TenantContext) -> bool:
    role = normalize_role(manager.role)
    t_role = normalize_role(target.role)
    if role == UserRole.GENERAL_ADMIN.value:
        return True
    if role != UserRole.CENTER_ADMIN.value:
        return False
    if t_role in {UserRole.GENERAL_ADMIN.value, UserRole.CENTER_ADMIN.value}:
        return False
    return target.institution_id == ctx.institution_code


def _available_roles(manager: User) -> list[str]:
    if normalize_role(manager.role) == UserRole.GENERAL_ADMIN.value:
        return [
            UserRole.SURGEON.value,
            UserRole.SUPERVISOR.value,
            UserRole.COORDINATOR.value,
            UserRole.CENTER_ADMIN.value,
        ]
    return list(ASSIGNABLE_CENTER_ROLES)


def _users_queryset(db: Session, ctx: TenantContext) -> list[User]:
    q = db.query(User).order_by(User.role, User.username)
    if not ctx.is_general_admin:
        q = q.filter(User.institution_id == ctx.institution_code)
    return q.all()


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    users = _users_queryset(db, ctx)
    theme = get_theme_for_center(db, ctx.center_id)
    return templates.TemplateResponse(
        request,
        "users/list.html",
        {
            "user": current,
            "users": users,
            "role_labels": ROLE_LABELS,
            "manage_surgeons_only": not ctx.is_general_admin,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_user_form(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    theme = get_theme_for_center(db, ctx.center_id)
    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": current,
            "roles": _available_roles(current),
            "role_labels": ROLE_LABELS,
            "edit_user": None,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
        },
    )


@router.post("/new")
def create_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    username: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = UserRole.SURGEON.value,
):
    username = username.strip().lower()
    allowed = set(_available_roles(current))
    role_n = normalize_role(role)
    if role_n not in allowed:
        flash(request, "No tiene permiso para crear ese rol.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)
    if not ctx.is_general_admin and role_n not in ASSIGNABLE_CENTER_ROLES:
        flash(request, "No puede crear administradores.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)
    if db.query(User).filter(User.username == username).first():
        flash(request, "El nombre de usuario ya existe.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)
    if len(password) < 6:
        flash(request, "La contraseña debe tener al menos 6 caracteres.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)

    user = User(
        username=username,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role_n,
        institution_id=ctx.institution_code or current.institution_id,
        account_status="active",
    )
    db.add(user)
    db.flush()
    if ctx.center_id:
        db.add(
            CenterMembership(
                user_id=user.id,
                center_id=ctx.center_id,
                role=role_n,
                is_active=True,
            )
        )
    write_audit(
        db,
        action="user_created",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current.id,
        center_id=ctx.center_id,
        after={"username": username, "role": role_n},
    )
    db.commit()
    flash(request, "Usuario creado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{user_id}/edit", response_class=HTMLResponse)
def edit_user_form(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target, ctx):
        flash(request, "No puede editar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
    theme = get_theme_for_center(db, ctx.center_id)
    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": current,
            "roles": _available_roles(current),
            "role_labels": ROLE_LABELS,
            "edit_user": target,
            "theme": theme,
            "brand_css": theme.css_variables(),
            "flashes": pop_flashes(request),
        },
    )


@router.post("/{user_id}/edit")
def edit_user_submit(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    username: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()] = "",
    role: Annotated[str | None, Form()] = None,
    is_active: Annotated[str | None, Form()] = None,
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target, ctx):
        flash(request, "No puede editar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)

    username = username.strip().lower()
    existing = db.query(User).filter(User.username == username, User.id != target.id).first()
    if existing:
        flash(request, "El nombre de usuario ya existe.", "danger")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    before = {"role": target.role, "username": target.username}
    target.username = username
    target.full_name = full_name.strip()

    allowed = set(_available_roles(current))
    effective_role = normalize_role(role or target.role)
    if effective_role not in allowed and effective_role != normalize_role(target.role):
        flash(request, "No tiene permiso para asignar ese rol.", "danger")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)
    if not ctx.is_general_admin and effective_role not in ASSIGNABLE_CENTER_ROLES:
        flash(request, "No puede asignar roles de administrador.", "danger")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    if target.id == current.id and normalize_role(current.role) == UserRole.GENERAL_ADMIN.value:
        if effective_role != UserRole.GENERAL_ADMIN.value:
            flash(request, "No puede quitarse el rol de administrador general.", "warning")
            return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    target.role = effective_role
    target.is_active = is_active == "on"
    if not target.is_active:
        target.account_status = "suspended"
    elif target.account_status == "suspended":
        target.account_status = "active"

    if password.strip():
        if len(password.strip()) < 6:
            flash(request, "La contraseña debe tener al menos 6 caracteres.", "danger")
            return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)
        target.password_hash = hash_password(password.strip())

    if target.id == current.id and not target.is_active:
        flash(request, "No puede desactivar su propia cuenta.", "warning")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    if ctx.center_id:
        mem = (
            db.query(CenterMembership)
            .filter(
                CenterMembership.user_id == target.id,
                CenterMembership.center_id == ctx.center_id,
            )
            .first()
        )
        if mem:
            mem.role = effective_role
            mem.is_active = target.is_active

    write_audit(
        db,
        action="user_updated",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current.id,
        center_id=ctx.center_id,
        before=before,
        after={"role": target.role, "username": target.username},
    )
    db.commit()
    flash(request, "Perfil actualizado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/toggle")
def toggle_user(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target, ctx):
        flash(request, "No puede modificar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
    if target.id == current.id:
        flash(request, "No puede desactivar su propia cuenta.", "warning")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
    target.is_active = not target.is_active
    target.account_status = "active" if target.is_active else "suspended"
    write_audit(
        db,
        action="user_toggled",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current.id,
        center_id=ctx.center_id,
        after={"is_active": target.is_active},
    )
    db.commit()
    flash(request, "Estado de usuario actualizado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/delete")
def delete_user(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target, ctx):
        flash(request, "No puede eliminar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
    if target.id == current.id:
        flash(request, "No puede eliminar su propia cuenta.", "warning")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)

    surgery_count = db.query(Surgery).filter(Surgery.surgeon_id == target.id).count()
    created_count = db.query(Surgery).filter(Surgery.created_by_id == target.id).count()
    if surgery_count or created_count:
        flash(
            request,
            "No se puede eliminar: el usuario tiene cirugías asociadas. "
            "Desactívelo en su lugar.",
            "warning",
        )
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)

    write_audit(
        db,
        action="user_deleted",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current.id,
        center_id=ctx.center_id,
        before={"username": target.username},
    )
    db.delete(target)
    db.commit()
    flash(request, "Usuario eliminado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
