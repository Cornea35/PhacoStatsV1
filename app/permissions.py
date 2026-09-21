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

    @property
    def is_general_admin(self) -> bool:
        return self.role == UserRole.GENERAL_ADMIN.value

    def has(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())


SESSION_CENTER_KEY = "active_center_id"


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
        return ctx.user

    return dependency


def institution_scope(user: User) -> str | None:
    """Legacy helper: general_admin → None (all); others → institution code."""
    if normalize_role(user.role) == UserRole.GENERAL_ADMIN.value:
        return None
    return (user.institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE


def center_scope_id(ctx: TenantContext) -> int | None:
    """None = all centers (general admin); else forced center id."""
    if ctx.is_general_admin:
        return None
    return ctx.center_id


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
        return
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

    active_center_id = request.session.get(SESSION_CENTER_KEY)
    membership = None
    center = None

    if role == UserRole.GENERAL_ADMIN.value:
        if active_center_id:
            center = db.get(Center, int(active_center_id))
        if center is None and memberships:
            center = db.get(Center, memberships[0].center_id)
        if center is None:
            center = db.query(Center).filter(Center.code == DEFAULT_INSTITUTION_CODE).first()
        return TenantContext(
            user=user,
            role=role,
            center=center,
            center_id=center.id if center else None,
            institution_code=center.code if center else DEFAULT_INSTITUTION_CODE,
            membership=None,
        )

    if active_center_id:
        membership = next((m for m in memberships if m.center_id == int(active_center_id)), None)
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
        request.session[SESSION_CENTER_KEY] = center.id

    return TenantContext(
        user=user,
        role=role,
        center=center,
        center_id=membership.center_id,
        institution_code=center.code if center else user.institution_id,
        membership=membership,
    )
