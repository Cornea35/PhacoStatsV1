"""Publication seed must not create surgeries."""

from sqlalchemy.orm import Session

from app.models import Surgery, User
from app.seed import seed_if_empty


def test_seed_if_empty_creates_users_without_surgeries(db_session: Session):
    assert db_session.query(User).count() == 0
    seed_if_empty(db_session)
    assert db_session.query(User).count() == 3
    assert db_session.query(Surgery).count() == 0
    # Idempotent
    seed_if_empty(db_session)
    assert db_session.query(User).count() == 3
    assert db_session.query(Surgery).count() == 0
