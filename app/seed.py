"""Bootstrap users + multi-center defaults (publication build)."""

from sqlalchemy.orm import Session

from app.constants import DEFAULT_INSTITUTION_CODE, UserRole
from app.migrations.multicenter import ensure_default_centers, migrate_users_and_cases_to_centers
from app.models import CenterMembership, User
from app.security import hash_password


def seed_if_empty(db: Session) -> None:
    """Create initial accounts when the database has no users.

    Does **not** create surgeries. Ensures CODET + HU_UANL centers exist.
    Change default passwords immediately after first login in production.
    """
    ensure_default_centers(db)
    if db.query(User).first() is not None:
        migrate_users_and_cases_to_centers(db)
        return

    centers = ensure_default_centers(db)
    codet = centers[DEFAULT_INSTITUTION_CODE]

    admin = User(
        username="admin",
        full_name="Administrador general",
        password_hash=hash_password("admin123"),
        role=UserRole.GENERAL_ADMIN.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
        account_status="active",
        email="admin@phacostats.local",
    )
    coordinator = User(
        username="coord",
        full_name="Coordinadora",
        password_hash=hash_password("coord123"),
        role=UserRole.COORDINATOR.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
        account_status="active",
        email="coord@phacostats.local",
    )
    surgeon = User(
        username="cirujano1",
        full_name="Cirujano",
        password_hash=hash_password("cirujano123"),
        role=UserRole.SURGEON.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
        account_status="active",
        email="cirujano1@phacostats.local",
    )
    db.add_all([admin, coordinator, surgeon])
    db.flush()
    for user, role in (
        (admin, UserRole.GENERAL_ADMIN.value),
        (coordinator, UserRole.COORDINATOR.value),
        (surgeon, UserRole.SURGEON.value),
    ):
        db.add(
            CenterMembership(
                user_id=user.id,
                center_id=codet.id,
                role=role,
                is_active=True,
            )
        )
    db.commit()
