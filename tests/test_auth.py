"""Authentication and user-management authorization tests."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from tests.conftest import login


def test_login_success(client: TestClient):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_login_failure(client: TestClient):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_requires_auth(client: TestClient):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_users_forbidden_for_surgeon(client: TestClient):
    login(client, "surgeon", "surgeon123")
    response = client.get("/users")
    assert response.status_code == 403


def test_users_forbidden_for_coordinator(client: TestClient):
    login(client, "coord", "coord123")
    response = client.get("/users")
    assert response.status_code == 403


def test_admin_can_list_users(client: TestClient):
    login(client, "admin", "admin123")
    response = client.get("/users")
    assert response.status_code == 200
    assert "Admin Test" in response.text


def test_admin_can_create_user(client: TestClient):
    login(client, "admin", "admin123")
    response = client.post(
        "/users/new",
        data={
            "username": "nuevo",
            "full_name": "Nuevo Cirujano",
            "password": "secret1",
            "role": "surgeon",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/users"


def test_admin_can_edit_surgeon(client: TestClient, db_session: Session, seed_users):
    target = seed_users["surgeon"]
    login(client, "admin", "admin123")
    response = client.post(
        f"/users/{target.id}/edit",
        data={
            "username": "surgeon",
            "full_name": "Surgeon Edited",
            "password": "",
            "role": "surgeon",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(target)
    assert target.full_name == "Surgeon Edited"


def test_admin_can_delete_surgeon_without_cases(client: TestClient, db_session: Session, seed_users):
    spare = User(
        username="spare_surgeon",
        full_name="Spare",
        password_hash=seed_users["surgeon"].password_hash,
        role="surgeon",
        institution_id="CODET",
    )
    db_session.add(spare)
    db_session.commit()
    db_session.refresh(spare)

    login(client, "admin", "admin123")
    response = client.post(f"/users/{spare.id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(User, spare.id) is None
