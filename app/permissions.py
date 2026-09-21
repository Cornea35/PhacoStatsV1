"""Centralized role-based permission matrix (membership-aware)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.constants import DEFAULT_INSTITUTION_CODE, UserRole
from app.database import get_db
from app.deps import get_current_user
from app.models import Center, CenterMembership, SupervisorAssignment, User


class Permission(str, Enum):
    VIEW_CLINICAL_DASHBOARD = "view_clinical_dashboard"
    VIEW_OPS_DASHBOARD = "view_ops_dashboard"
    VIEW_SURGEON_STATS = "view_surgeon_stats"
    VIEW_REFRACTIVE = "view_refractive"
    VIEW_ADMIN_ANALYTICS = "view_admin_analytics"
    VIEW_SURGICAL_RISK = "view_surgical_risk"
    VIEW_OWN_RISK_PROFILE = "view_own_risk_profile"
    MANAGE_USERS = "manage_users"
    MANAGE_CENTER_USERS = "manage_center_users"
    APPROVE_REGISTRATIONS = "approve_registrations"
    MANAGE_CENTERS = "manage_centers"
    MANAGE_BRANDING = "manage_branding"
    SWITCH_CENTER = "switch_center"
    VIEW_AUDIT_LOG = "view_audit_log"
    CREATE_SURGERY = "create_surgery"
    EDIT_SURGERY = "edit_surgery"
    VIEW_SURGERY_CLINICAL_DETAIL = "view_surgery_clinical_detail"
    VIEW_SURGERY_OPS_DETAIL = "view_surgery_ops_detail"
    MANAGE_FOLLOWUPS = "manage_followups"
    MANAGE_REINTERVENTION = "manage_reintervention"
    EXPORT_OPS = "export_ops"
    EXPORT_CLINICAL = "export_clinical"
    VIEW_ASSIGNED_SURGEONS = "view_assigned_surgeons"
    COMPARE_CENTERS = "compare_centers"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    UserRole.GENERAL_ADMIN.value: frozenset(Permission),
    UserRole.CENTER_ADMIN.value: frozenset(
        {
            Permission.VIEW_CLINICAL_DASHBOARD,
            Permission.VIEW_SURGEON_STATS,
            Permission.VIEW_REFRACTIVE,
            Permission.VIEW_ADMIN_ANALYTICS,
            Permission.VIEW_SURGICAL_RISK,
            Permission.MANAGE_CENTER_USERS,
            Permission.APPROVE_REGISTRATIONS,
            Permission.MANAGE_BRANDING,
            Permission.CREATE_SURGERY,
            Permission.EDIT_SURGERY,
            Permission.VIEW_SURGERY_CLINICAL_DETAIL,
            Permission.MANAGE_FOLLOWUPS,
            Permission.MANAGE_REINTERVENTION,
            Permission.EXPORT_CLINICAL,
            Permission.EXPORT_OPS,
        }
    ),
    UserRole.SURGEON.value: frozenset(
        {
            Permission.VIEW_CLINICAL_DASHBOARD,
            Permission.VIEW_SURGEON_STATS,
            Permission.VIEW_REFRACTIVE,
            Permission.VIEW_OWN_RISK_PROFILE,
            Permission.CREATE_SURGERY,
            Permission.EDIT_SURGERY,
            Permission.VIEW_SURGERY_CLINICAL_DETAIL,
            Permission.MANAGE_FOLLOWUPS,
            Permission.MANAGE_REINTERVENTION,
            Permission.EXPORT_CLINICAL,
        }
    ),
    UserRole.SUPERVISOR.value: frozenset(
        {
            Permission.VIEW_CLINICAL_DASHBOARD,
            Permission.VIEW_SURGEON_STATS,
            Permission.VIEW_REFRACTIVE,
            Permission.VIEW_SURGICAL_RISK,
            Permission.VIEW_ASSIGNED_SURGEONS,
            Permission.VIEW_SURGERY_CLINICAL_DETAIL,
            Permission.EXPORT_CLINICAL,
        }
    ),
    UserRole.COORDINATOR.value: frozenset(
        {
            Permission.VIEW_OPS_DASHBOARD,
            Permission.VIEW_SURGERY_OPS_DETAIL,
            Permission.CREATE_SURGERY,
            Permission.EDIT_SURGERY,
            Permission.MANAGE_FOLLOWUPS,
            Permission.MANAGE_REINTERVENTION,
            Permission.EXPORT_OPS,
        }
    ),
}


@dataclass
class TenantContext:
    user: User
    role: str
    center: Center | None
    center_id: int | None
    institution_code: str | None
    membership: CenterMembership | None
    view_all: bool = False

    @property
    def is_general_admin(self) -> bool:
        return self.role == UserRole.GENERAL_ADMIN.value

    def has(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())


SESSION_CENTER_KEY = "active_center_id"
SESSION_CENTER_ALL = "all"


def normalize_role(role: str | None) -> str:
    if role in {"admin", "general_admin"}:
        return UserRole.GENERAL_ADMIN.value
    if role in ROLE_PERMISSIONS:
        return role or UserRole.SURGEON.value
    return UserRole.SURGEON.value


def has_permission(user: User, permission: Permission, role: str | None = None) -> bool:
    r = normalize_role(role or user.role)
    return permission in ROLE_PERMISSIONS.get(r, frozenset())


def require_permission(permission: Permission):
    def dependency(ctx: Annotated[TenantContext, Depends(get_tenant_context)]) -> User:
        if not ctx.has(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción.",
            )
        return ctx.user

    return dependency


def require_roles(*roles: UserRole):
    """Compatibility wrapper: allow listed roles on the active membership."""
    allowed = {normalize_role(r.value) for r in roles}

    def dependency(ctx: Annotated[TenantContext, Depends(get_tenant_context)]) -> User:
        if ctx.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción.",
            )
        # Keep denormalized fields in sync for templates that still read user.role
        ctx.user.role = ctx.role
        if ctx.institution_code:
            ctx.user.institution_id = ctx.institution_code
        elif ctx.is_general_admin and ctx.view_all:
            # Preserve last known code on user row; scope uses ctx
            pass
        return ctx.user

    return dependency


def institution_scope(user: User) -> str | None:
    """Legacy helper for non-ctx callers.

    general_admin without an explicit per-request scope → all centers (None).
    Prefer scope_institution(ctx) in new code.
    """
    if normalize_role(user.role) == UserRole.GENERAL_ADMIN.value:
        # Populated by get_tenant_context / middleware for active center views
        scoped = getattr(user, "_active_institution_code", None)
        if scoped == SESSION_CENTER_ALL:
            return None
        if scoped:
            return scoped
        return None
    return (user.institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE


def scope_institution(ctx: TenantContext) -> str | None:
    """Institution code filter: None means all centers."""
    if ctx.view_all:
        return None
    return ctx.institution_code


def scope_center_id(ctx: TenantContext) -> int | None:
    """Center id filter: None means all centers."""
    if ctx.view_all:
        return None
    return ctx.center_id


def center_scope_id(ctx: TenantContext) -> int | None:
    return scope_center_id(ctx)


def attach_tenant_ui_state(request: Request, db: Session, ctx: TenantContext) -> None:
    """Populate request.state for Jinja branding / center switcher on every page."""
    from app.services.branding import get_theme_for_center, list_active_centers

    theme = get_theme_for_center(db, ctx.center_id)
    request.state.theme = theme
    request.state.brand_css = theme.css_variables() if theme else ""
    request.state.active_center = ctx.center
    request.state.view_all_centers = bool(ctx.view_all)
    can_switch = ctx.has(Permission.SWITCH_CENTER) or ctx.is_general_admin
    request.state.can_switch_center = can_switch
    request.state.switchable_centers = list_active_centers(db) if can_switch else []


def is_coordinator(user: User) -> bool:
    return normalize_role(user.role) == UserRole.COORDINATOR.value


def assert_surgery_institution_access(user: User, surgery_institution_id: str) -> None:
    scope = institution_scope(user)
    if scope is None:
        return
    if (surgery_institution_id or DEFAULT_INSTITUTION_CODE) != scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene acceso a datos de otra institución.",
        )


def assert_center_access(ctx: TenantContext, center_id: int | None) -> None:
    if ctx.is_general_admin:
        if ctx.view_all:
            return
        if center_id is None or ctx.center_id == center_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cambie al centro correspondiente para ver estos datos.",
        )
    if center_id is None or ctx.center_id != center_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene acceso a datos de otro centro.",
        )


def assert_surgery_access(user: User, surgery) -> None:
    assert_surgery_institution_access(user, surgery.institution_id)
    role = normalize_role(user.role)
    if role == UserRole.SURGEON.value and surgery.surgeon_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puede gestionar casos de otros cirujanos.",
        )


def assigned_surgeon_ids(db: Session, ctx: TenantContext) -> list[int] | None:
    """For supervisors: list of surgeon user ids; None = not restricted that way."""
    if ctx.role != UserRole.SUPERVISOR.value or ctx.center_id is None:
        return None
    rows = (
        db.query(SupervisorAssignment.surgeon_user_id)
        .filter(
            SupervisorAssignment.center_id == ctx.center_id,
            SupervisorAssignment.supervisor_user_id == ctx.user.id,
        )
        .all()
    )
    return [r[0] for r in rows]


def get_tenant_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TenantContext:
    if getattr(user, "account_status", "active") not in {None, "active"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta aún no está activa.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta suspendida.")

    role = normalize_role(user.role)
    memberships = (
        db.query(CenterMembership)
        .filter(CenterMembership.user_id == user.id, CenterMembership.is_active.is_(True))
        .all()
    )

    active_raw = request.session.get(SESSION_CENTER_KEY)
    membership = None
    center = None

    if role == UserRole.GENERAL_ADMIN.value:
        view_all = active_raw in {SESSION_CENTER_ALL, "0", 0}
        if view_all:
            user._active_institution_code = SESSION_CENTER_ALL  # type: ignore[attr-defined]
            ctx = TenantContext(
                user=user,
                role=role,
                center=None,
                center_id=None,
                institution_code=None,
                membership=None,
                view_all=True,
            )
            attach_tenant_ui_state(request, db, ctx)
            return ctx
        if active_raw not in {None, ""}:
            try:
                center = db.get(Center, int(active_raw))
            except (TypeError, ValueError):
                center = None
        if center is None and memberships:
            center = db.get(Center, memberships[0].center_id)
        if center is None:
            center = db.query(Center).filter(Center.code == DEFAULT_INSTITUTION_CODE).first()
        if center:
            request.session[SESSION_CENTER_KEY] = center.id
            user.institution_id = center.code
            user._active_institution_code = center.code  # type: ignore[attr-defined]
        ctx = TenantContext(
            user=user,
            role=role,
            center=center,
            center_id=center.id if center else None,
            institution_code=center.code if center else DEFAULT_INSTITUTION_CODE,
            membership=None,
            view_all=False,
        )
        attach_tenant_ui_state(request, db, ctx)
        return ctx

    if active_raw not in {None, "", SESSION_CENTER_ALL}:
        try:
            membership = next(
                (m for m in memberships if m.center_id == int(active_raw)),
                None,
            )
        except (TypeError, ValueError):
            membership = None
    if membership is None and memberships:
        membership = memberships[0]
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene membresía activa en ningún centro.",
        )

    center = db.get(Center, membership.center_id)
    role = normalize_role(membership.role)
    user.role = role
    if center:
        user.institution_id = center.code
        user._active_institution_code = center.code  # type: ignore[attr-defined]
        request.session[SESSION_CENTER_KEY] = center.id

    ctx = TenantContext(
        user=user,
        role=role,
        center=center,
        center_id=membership.center_id,
        institution_code=center.code if center else user.institution_id,
        membership=membership,
        view_all=False,
    )
    attach_tenant_ui_state(request, db, ctx)
    return ctx
