"""Bootstrap users only — no surgery / clinical demo data (publication build)."""

from sqlalchemy.orm import Session

from app.constants import DEFAULT_INSTITUTION_CODE, UserRole
from app.models import User
from app.security import hash_password


def seed_if_empty(db: Session) -> None:
    """Create initial accounts when the database has no users.

    Does **not** create surgeries, complications, follow-ups, or reinterventions.
    Change default passwords immediately after first login in production.
    """
    if db.query(User).first() is not None:
        return

    admin = User(
        username="admin",
        full_name="Administrador",
        password_hash=hash_password("admin123"),
        role=UserRole.ADMIN.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
    )
    coordinator = User(
        username="coord",
        full_name="Coordinadora",
        password_hash=hash_password("coord123"),
        role=UserRole.COORDINATOR.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
    )
    surgeon = User(
        username="cirujano1",
        full_name="Cirujano",
        password_hash=hash_password("cirujano123"),
        role=UserRole.SURGEON.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
    )
    db.add_all([admin, coordinator, surgeon])
    db.commit()
