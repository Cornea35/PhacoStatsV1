"""Safe additive migration to multi-center tenancy (idempotent)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.constants import (
    CENTER_CODE_UANL,
    DEFAULT_INSTITUTION_CODE,
    UserRole,
)
from app.database import Base, engine
from app.models import (
    Center,
    CenterBranding,
    CenterMembership,
    User,
)
from app.security import hash_password


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column in cols:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} {ddl}"))


def ensure_multicenter_columns() -> None:
    """Additive user/profile columns compatible with SQLite and Postgres."""
    _add_column_if_missing("users", "email", "ADD COLUMN email VARCHAR(180)")
    _add_column_if_missing("users", "specialty", "ADD COLUMN specialty VARCHAR(120)")
    _add_column_if_missing("users", "training_level", "ADD COLUMN training_level VARCHAR(32)")
    _add_column_if_missing("users", "professional_id", "ADD COLUMN professional_id VARCHAR(64)")
    _add_column_if_missing(
        "users",
        "account_status",
        "ADD COLUMN account_status VARCHAR(32) NOT NULL DEFAULT 'active'",
    )
    _add_column_if_missing("surgeries", "center_id", "ADD COLUMN center_id INTEGER")
    _add_column_if_missing("follow_ups", "center_id", "ADD COLUMN center_id INTEGER")


def _branding(
    *,
    short_name: str,
    full_name: str,
    primary: str,
    secondary: str,
    accent: str,
    placeholder: str | None = None,
    logo_path: str | None = None,
) -> CenterBranding:
    return CenterBranding(
        short_name=short_name,
        full_name=full_name,
        primary_color=primary,
        secondary_color=secondary,
        accent_color=accent,
        text_color="#1a1a1a",
        show_powered_by=True,
        placeholder_label=placeholder if not logo_path else None,
        logo_path=logo_path,
    )


UANL_OFFICIAL_LOGO = "img/hu_uanl_logo.png"


def ensure_default_centers(db: Session) -> dict[str, Center]:
    """Create CODET + HU UANL centers if missing. Returns code→Center map."""
    Base.metadata.create_all(bind=engine)
    ensure_multicenter_columns()

    by_code: dict[str, Center] = {c.code: c for c in db.query(Center).all()}

    if DEFAULT_INSTITUTION_CODE not in by_code:
        codet = Center(
            code=DEFAULT_INSTITUTION_CODE,
            short_name="CODET Vision Institute",
            full_name="CODET Vision Institute",
            is_active=True,
            branding=_branding(
                short_name="CODET Vision Institute",
                full_name="CODET Vision Institute",
                primary="#0b5ea8",
                secondary="#084a86",
                accent="#5aa6e8",
            ),
        )
        db.add(codet)
        db.flush()
        by_code[DEFAULT_INSTITUTION_CODE] = codet

    if CENTER_CODE_UANL not in by_code:
        uanl = Center(
            code=CENTER_CODE_UANL,
            short_name="Hospital Universitario UANL",
            full_name=(
                'Hospital Universitario "Dr. José Eleuterio González" '
                "– Universidad Autónoma de Nuevo León"
            ),
            is_active=True,
            branding=_branding(
                short_name="Hospital Universitario UANL",
                full_name=(
                    'Hospital Universitario "Dr. José Eleuterio González" '
                    "– Universidad Autónoma de Nuevo León"
                ),
                primary="#7a0019",
                secondary="#4a000f",
                accent="#c9a227",
                logo_path=UANL_OFFICIAL_LOGO,
            ),
        )
        db.add(uanl)
        db.flush()
        by_code[CENTER_CODE_UANL] = uanl
    else:
        # Idempotent: attach official logo if the center still uses placeholder only
        uanl = by_code[CENTER_CODE_UANL]
        branding = uanl.branding
        if branding is None:
            branding = _branding(
                short_name=uanl.short_name,
                full_name=uanl.full_name,
                primary="#7a0019",
                secondary="#4a000f",
                accent="#c9a227",
                logo_path=UANL_OFFICIAL_LOGO,
            )
            branding.center_id = uanl.id
            db.add(branding)
        elif not branding.logo_path:
            branding.logo_path = UANL_OFFICIAL_LOGO
            branding.placeholder_label = None

    db.commit()
    return {c.code: c for c in db.query(Center).all()}


def _normalize_legacy_role(role: str) -> str:
    if role in {"admin", "general_admin"}:
        return UserRole.GENERAL_ADMIN.value
    if role == "center_admin":
        return UserRole.CENTER_ADMIN.value
    if role == "supervisor":
        return UserRole.SUPERVISOR.value
    if role == "coordinator":
        return UserRole.COORDINATOR.value
    return UserRole.SURGEON.value


def migrate_users_and_cases_to_centers(db: Session) -> None:
    """Attach existing users/cases to CODET; create memberships; map admin→general_admin."""
    centers = ensure_default_centers(db)
    codet = centers[DEFAULT_INSTITUTION_CODE]

    for user in db.query(User).all():
        new_role = _normalize_legacy_role(user.role or UserRole.SURGEON.value)
        if user.role != new_role:
            user.role = new_role
        if not getattr(user, "account_status", None):
            user.account_status = "active"
        inst = (user.institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE
        center = centers.get(inst) or codet
        user.institution_id = center.code

        existing = (
            db.query(CenterMembership)
            .filter(
                CenterMembership.user_id == user.id,
                CenterMembership.center_id == center.id,
            )
            .first()
        )
        if existing is None:
            db.add(
                CenterMembership(
                    user_id=user.id,
                    center_id=center.id,
                    role=new_role,
                    is_active=True,
                )
            )
        else:
            existing.role = new_role
            existing.is_active = True

    from app.models import FollowUp, Surgery

    for surgery in db.query(Surgery).all():
        code = (surgery.institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE
        center = centers.get(code) or codet
        surgery.institution_id = center.code
        if getattr(surgery, "center_id", None) is None:
            surgery.center_id = center.id

    for fu in db.query(FollowUp).all():
        code = (fu.institution_id or DEFAULT_INSTITUTION_CODE).strip() or DEFAULT_INSTITUTION_CODE
        center = centers.get(code) or codet
        fu.institution_id = center.code
        if getattr(fu, "center_id", None) is None:
            fu.center_id = center.id

    db.commit()
