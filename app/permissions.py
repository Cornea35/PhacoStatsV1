"""Centralized role-based permission matrix for PhacoStats."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.constants import DEFAULT_INSTITUTION_CODE, UserRole
from app.deps import get_current_user
from app.models import User


class Permission(str, Enum):
    VIEW_CLINICAL_DASHBOARD = "view_clinical_dashboard"
    VIEW_OPS_DASHBOARD = "view_ops_dashboard"
    VIEW_SURGEON_STATS = "view_surgeon_stats"
    VIEW_REFRACTIVE = "view_refractive"
    VIEW_ADMIN_ANALYTICS = "view_admin_analytics"
    MANAGE_USERS = "manage_users"
    CREATE_SURGERY = "create_surgery"
    EDIT_SURGERY = "edit_surgery"
    VIEW_SURGERY_CLINICAL_DETAIL = "view_surgery_clinical_detail"
    VIEW_SURGERY_OPS_DETAIL = "view_surgery_ops_detail"
    MANAGE_FOLLOWUPS = "manage_followups"
    MANAGE_REINTERVENTION = "manage_reintervention"
    EXPORT_OPS = "export_ops"
    EXPORT_CLINICAL = "export_clinical"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    UserRole.ADMIN.value: frozenset(Permission),
    UserRole.SURGEON.value: frozenset(
        {
            Permission.VIEW_CLINICAL_DASHBOARD,
            Permission.VIEW_SURGEON_STATS,
            Permission.VIEW_REFRACTIVE,
            Permission.CREATE_SURGERY,
            Permission.EDIT_SURGERY,
            Permission.VIEW_SURGERY_CLINICAL_DETAIL,
            Permission.MANAGE_FOLLOWUPS,
            Permission.MANAGE_REINTERVENTION,
            Permission.EXPORT_CLINICAL,
        }
    ),
    UserRole.COORDINATOR.value: frozenset(
        {
            Permission.VIEW_OPS_DASHBOARD,
            Permission.VIEW_SURGERY_OPS_DETAIL,
            Permission.MANAGE_REINTERVENTION,
            Permission.EXPORT_OPS,
        }
    ),
}


def has_permission(user: User, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def require_permission(permission: Permission):
    """FastAPI dependency: raise 403 if current user lacks permission."""

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción.",
            )
        return user

    return dependency


def institution_scope(user: User) -> str | None:
    """Return institution filter for queries.

    Admin: None (all institutions).
    Surgeon / coordinator: their institution_id (default CODET).
    """
    if user.role == UserRole.ADMIN.value:
        return None
    return (user.institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE


def is_coordinator(user: User) -> bool:
    return user.role == UserRole.COORDINATOR.value


def assert_surgery_institution_access(user: User, surgery_institution_id: str) -> None:
    """Raise 403 if user cannot access surgery institution."""
    scope = institution_scope(user)
    if scope is None:
        return
    if (surgery_institution_id or DEFAULT_INSTITUTION_CODE) != scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene acceso a datos de otra institución.",
        )


def assert_surgery_access(user: User, surgery) -> None:
    """Institution scope + surgeons may only access their own cases."""
    assert_surgery_institution_access(user, surgery.institution_id)
    if user.role == UserRole.SURGEON.value and surgery.surgeon_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puede gestionar reintervenciones de otros cirujanos.",
        )
