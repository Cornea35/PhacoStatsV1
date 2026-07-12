"""User administration routes (admin only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.constants import ROLE_LABELS, UserRole
from app.database import get_db
from app.deps import flash, pop_flashes, require_roles
from app.models import Surgery, User
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

ManagerDep = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN)),
]


def _can_manage_target(manager: User, target: User) -> bool:
    return manager.role == UserRole.ADMIN.value


def _available_roles(manager: User) -> list[UserRole]:
    return list(UserRole)


def _users_queryset(db: Session, manager: User) -> list[User]:
    return db.query(User).order_by(User.role, User.username).all()


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
):
    users = _users_queryset(db, current)
    return templates.TemplateResponse(
        request,
        "users/list.html",
        {
            "user": current,
            "users": users,
            "role_labels": ROLE_LABELS,
            "manage_surgeons_only": current.role == UserRole.COORDINATOR.value,
            "flashes": pop_flashes(request),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_user_form(
    request: Request,
    current: ManagerDep,
):
    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": current,
            "roles": _available_roles(current),
            "role_labels": ROLE_LABELS,
            "edit_user": None,
            "flashes": pop_flashes(request),
        },
    )


@router.post("/new")
def create_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    username: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = UserRole.SURGEON.value,
):
    username = username.strip().lower()
    allowed = {r.value for r in _available_roles(current)}
    if role not in allowed:
        flash(request, "No tiene permiso para crear ese rol.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)
    if db.query(User).filter(User.username == username).first():
        flash(request, "El nombre de usuario ya existe.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)
    if len(password) < 6:
        flash(request, "La contraseña debe tener al menos 6 caracteres.", "danger")
        return RedirectResponse("/users/new", status_code=status.HTTP_303_SEE_OTHER)

    db.add(
        User(
            username=username,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role,
        )
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
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target):
        flash(request, "No puede editar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "users/form.html",
        {
            "user": current,
            "roles": _available_roles(current),
            "role_labels": ROLE_LABELS,
            "edit_user": target,
            "flashes": pop_flashes(request),
        },
    )


@router.post("/{user_id}/edit")
def edit_user_submit(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
    username: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()] = "",
    role: Annotated[str | None, Form()] = None,
    is_active: Annotated[str | None, Form()] = None,
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target):
        flash(request, "No puede editar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)

    username = username.strip().lower()
    existing = db.query(User).filter(User.username == username, User.id != target.id).first()
    if existing:
        flash(request, "El nombre de usuario ya existe.", "danger")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    target.username = username
    target.full_name = full_name.strip()

    allowed = {r.value for r in _available_roles(current)}
    effective_role = role or target.role
    if effective_role not in allowed:
        flash(request, "No tiene permiso para asignar ese rol.", "danger")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    if target.id == current.id and effective_role != UserRole.ADMIN.value and current.role == UserRole.ADMIN.value:
        flash(request, "No puede quitarse el rol de administrador.", "warning")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    target.role = effective_role
    target.is_active = is_active == "on"

    if password.strip():
        if len(password.strip()) < 6:
            flash(request, "La contraseña debe tener al menos 6 caracteres.", "danger")
            return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)
        target.password_hash = hash_password(password.strip())

    if target.id == current.id and not target.is_active:
        flash(request, "No puede desactivar su propia cuenta.", "warning")
        return RedirectResponse(f"/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    db.commit()
    flash(request, "Perfil actualizado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/toggle")
def toggle_user(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target):
        flash(request, "No puede modificar este usuario.", "danger")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
    if target.id == current.id:
        flash(request, "No puede desactivar su propia cuenta.", "warning")
        return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
    target.is_active = not target.is_active
    db.commit()
    flash(request, "Estado de usuario actualizado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{user_id}/delete")
def delete_user(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current: ManagerDep,
):
    target = db.get(User, user_id)
    if target is None or not _can_manage_target(current, target):
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

    db.delete(target)
    db.commit()
    flash(request, "Usuario eliminado.", "success")
    return RedirectResponse("/users", status_code=status.HTTP_303_SEE_OTHER)
