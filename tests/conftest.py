"""Shared pytest fixtures for PhacoStats (synthetic data only)."""

from __future__ import annotations

import os
from collections.abc import Generator

# Skip demo seeding against the file DB when TestClient runs app lifespan.
os.environ["PHACOSTATS_TESTING"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants import DEFAULT_INSTITUTION_CODE, UserRole
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def seed_users(db_session: Session) -> dict[str, User]:
    users = {
        "admin": User(
            username="admin",
            full_name="Admin Test",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN.value,
            institution_id=DEFAULT_INSTITUTION_CODE,
        ),
        "coord": User(
            username="coord",
            full_name="Coord Test",
            password_hash=hash_password("coord123"),
            role=UserRole.COORDINATOR.value,
            institution_id=DEFAULT_INSTITUTION_CODE,
        ),
        "surgeon": User(
            username="surgeon",
            full_name="Surgeon Test",
            password_hash=hash_password("surgeon123"),
            role=UserRole.SURGEON.value,
            institution_id=DEFAULT_INSTITUTION_CODE,
        ),
        "surgeon2": User(
            username="surgeon2",
            full_name="Surgeon Two",
            password_hash=hash_password("surgeon123"),
            role=UserRole.SURGEON.value,
            institution_id=DEFAULT_INSTITUTION_CODE,
        ),
    }
    db_session.add_all(users.values())
    db_session.commit()
    for u in users.values():
        db_session.refresh(u)
    return users


@pytest.fixture()
def client(db_session: Session, seed_users: dict[str, User]) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
