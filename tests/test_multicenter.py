"""Multi-center tenancy, registration, branding, and risk profile tests."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.constants import CENTER_CODE_UANL, DEFAULT_INSTITUTION_CODE, UserRole
from app.models import (
    Center,
    CenterMembership,
    ComplicationEvent,
    RegistrationRequest,
    RiskFactor,
    Surgery,
    User,
)
from app.security import hash_password
from app.services.surgical_risk import build_surgical_risk_profile
from tests.conftest import login


def test_login_page_lists_centers_and_branding(client: TestClient):
    page = client.get("/login")
    assert page.status_code == 200
    assert "PhacoStats" in page.text
    assert "Created by Dr. Erik Navas" in page.text
    assert "CODET" in page.text or "CODET Vision" in page.text
    assert "Hospital Universitario UANL" in page.text
    assert "Crear cuenta" in page.text
    assert "Recuperar contraseña" in page.text


def test_center_branding_api_switches_theme(client: TestClient):
    codet = client.get(f"/api/centers/{DEFAULT_INSTITUTION_CODE}/branding")
    assert codet.status_code == 200
    assert codet.json()["primary"]
    uanl = client.get(f"/api/centers/{CENTER_CODE_UANL}/branding")
    assert uanl.status_code == 200
    assert uanl.json()["short_name"].startswith("Hospital Universitario")
    assert uanl.json()["primary"] != codet.json()["primary"] or uanl.json()["accent"]
    assert uanl.json()["logo_url"]
    assert "hu_uanl_logo" in uanl.json()["logo_url"]
    logo = client.get(uanl.json()["logo_url"])
    assert logo.status_code == 200
    assert logo.headers["content-type"].startswith("image/")


def test_register_without_role_and_pending_blocks_login(
    client: TestClient,
    db_session: Session,
):
    page = client.get("/register")
    assert page.status_code == 200
    assert "role" not in page.text.lower() or "No seleccione rol" in page.text

    resp = client.post(
        "/register",
        data={
            "full_name": "Nuevo Usuario",
            "email": "nuevo@test.local",
            "password": "secret12",
            "center_code": DEFAULT_INSTITUTION_CODE,
            "specialty": "Oftalmología",
            "training_level": "r3",
            "professional_id": "",
            "privacy_accepted": "on",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    req = db_session.query(RegistrationRequest).filter_by(email="nuevo@test.local").one()
    assert req.status == "pending"

    denied = client.post(
        "/login",
        data={
            "username": "nuevo@test.local",
            "password": "secret12",
            "center_code": DEFAULT_INSTITUTION_CODE,
        },
        follow_redirects=False,
    )
    assert denied.status_code == 303
    # Still on login — no session cookie for clinical access
    dash = client.get("/dashboard", follow_redirects=False)
    assert dash.status_code in {303, 401, 403} or dash.headers.get("location", "").endswith("/login")


def test_center_admin_approves_and_cannot_create_admin(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    centers = {c.code: c for c in db_session.query(Center).all()}
    ca = User(
        username="cadmin",
        full_name="Center Admin",
        password_hash=hash_password("cadmin123"),
        role=UserRole.CENTER_ADMIN.value,
        institution_id=DEFAULT_INSTITUTION_CODE,
        account_status="active",
        email="cadmin@test.local",
    )
    db_session.add(ca)
    db_session.flush()
    db_session.add(
        CenterMembership(
            user_id=ca.id,
            center_id=centers[DEFAULT_INSTITUTION_CODE].id,
            role=UserRole.CENTER_ADMIN.value,
            is_active=True,
        )
    )
    req = RegistrationRequest(
        center_id=centers[DEFAULT_INSTITUTION_CODE].id,
        full_name="Pendiente",
        email="pend@test.local",
        username="pendiente1",
        password_hash=hash_password("secret12"),
        privacy_accepted=True,
        status="pending",
        training_level="fellow",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    login(client, "cadmin", "cadmin123")
    approved = client.post(
        f"/admin/registrations/{req.id}/decide",
        data={"decision": "approve", "role": "surgeon", "reason": ""},
        follow_redirects=False,
    )
    assert approved.status_code == 303
    db_session.refresh(req)
    assert req.status == "active"
    user = db_session.query(User).filter_by(email="pend@test.local").one()
    assert user.role == UserRole.SURGEON.value

    blocked = client.post(
        f"/admin/registrations/{req.id}/decide",
        data={"decision": "approve", "role": "center_admin", "reason": ""},
        follow_redirects=False,
    )
    # already active; create path for new role assignment via users
    create_admin = client.post(
        "/users/new",
        data={
            "username": "hackeradmin",
            "full_name": "Nope",
            "password": "secret12",
            "role": "center_admin",
        },
        follow_redirects=False,
    )
    assert create_admin.status_code == 303
    assert db_session.query(User).filter_by(username="hackeradmin").first() is None


def test_general_admin_creates_center_admin(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    login(client, "admin", "admin123")
    centers = {c.code: c for c in db_session.query(Center).all()}
    uanl = centers[CENTER_CODE_UANL]
    resp = client.post(
        f"/admin/centers/{uanl.id}/admins",
        data={
            "username": "uanl_admin",
            "full_name": "Admin UANL",
            "password": "secret12",
            "email": "uanl@test.local",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    user = db_session.query(User).filter_by(username="uanl_admin").one()
    assert user.role == UserRole.CENTER_ADMIN.value
    assert user.institution_id == CENTER_CODE_UANL


def test_center_isolation(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    centers = {c.code: c for c in db_session.query(Center).all()}
    other_surgeon = User(
        username="other_surg",
        full_name="Other",
        password_hash=hash_password("secret12"),
        role=UserRole.SURGEON.value,
        institution_id=CENTER_CODE_UANL,
        account_status="active",
    )
    other_coord = User(
        username="other_coord",
        full_name="Other Coord",
        password_hash=hash_password("secret12"),
        role=UserRole.COORDINATOR.value,
        institution_id=CENTER_CODE_UANL,
        account_status="active",
    )
    db_session.add_all([other_surgeon, other_coord])
    db_session.flush()
    for u, role in (
        (other_surgeon, UserRole.SURGEON.value),
        (other_coord, UserRole.COORDINATOR.value),
    ):
        db_session.add(
            CenterMembership(
                user_id=u.id,
                center_id=centers[CENTER_CODE_UANL].id,
                role=role,
                is_active=True,
            )
        )
    foreign = Surgery(
        case_code="UANL-ONLY",
        surgery_date=date(2026, 1, 1),
        eye="OD",
        technique="Phaco",
        surgeon_id=other_surgeon.id,
        created_by_id=other_surgeon.id,
        institution_id=CENTER_CODE_UANL,
        center_id=centers[CENTER_CODE_UANL].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(foreign)
    db_session.commit()

    login(client, "coord", "coord123")
    assert client.get(f"/surgeries/{foreign.id}").status_code == 403

    login(client, "other_coord", "secret12", center_code=CENTER_CODE_UANL)
    page = client.get(f"/surgeries/{foreign.id}")
    assert page.status_code == 200
    assert "UANL-ONLY" in page.text


def test_footer_identity(client: TestClient):
    login(client, "admin", "admin123")
    page = client.get("/dashboard")
    assert "PhacoStats © 2026 Dr. Erik Navas" in page.text


def test_surgical_risk_insufficient_and_oe(
    db_session: Session,
    seed_users: dict[str, User],
):
    centers = {c.code: c for c in db_session.query(Center).all()}
    # Few cases → preliminary
    s = Surgery(
        case_code="RISK-1",
        surgery_date=date(2026, 2, 1),
        eye="OD",
        technique="Phaco",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        institution_id=DEFAULT_INSTITUTION_CODE,
        center_id=centers[DEFAULT_INSTITUTION_CODE].id,
        risk_factors=[RiskFactor(code="small_pupil"), RiskFactor(code="dense_cataract")],
        complication=ComplicationEvent(occurred=True, complication_type="pcr"),
    )
    db_session.add(s)
    db_session.commit()
    profile = build_surgical_risk_profile(
        db_session,
        center_id=centers[DEFAULT_INSTITUTION_CODE].id,
        surgeon_id=seed_users["surgeon"].id,
        surgeon_name="Surgeon Test",
    )
    assert profile.is_preliminary is True
    assert profile.n_cases == 1
    assert any(c.status == "insufficient" for c in profile.combinations)


def test_coordinator_can_create_surgery_form(client: TestClient):
    login(client, "coord", "coord123")
    assert client.get("/surgeries/new").status_code == 200


def test_general_admin_center_switcher_filters_dashboard(
    client: TestClient,
    db_session: Session,
    seed_users: dict,
):
    from app.constants import CENTER_CODE_UANL

    centers = {c.code: c for c in db_session.query(Center).all()}
    uanl = centers[CENTER_CODE_UANL]
    codet = centers[DEFAULT_INSTITUTION_CODE]

    db_session.add_all(
        [
            Surgery(
                case_code="SW-CODET",
                surgery_date=date(2026, 3, 1),
                eye="OD",
                technique="Phaco",
                surgeon_id=seed_users["surgeon"].id,
                created_by_id=seed_users["admin"].id,
                institution_id=DEFAULT_INSTITUTION_CODE,
                center_id=codet.id,
            ),
            Surgery(
                case_code="SW-UANL",
                surgery_date=date(2026, 3, 2),
                eye="OS",
                technique="Phaco",
                surgeon_id=seed_users["surgeon"].id,
                created_by_id=seed_users["admin"].id,
                institution_id=CENTER_CODE_UANL,
                center_id=uanl.id,
            ),
        ]
    )
    db_session.commit()

    login(client, "admin", "admin123")
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert 'name="center_id"' in dash.text
    assert "Todos" in dash.text

    switched = client.post(
        "/admin/active-center",
        data={"center_id": str(uanl.id), "next": "/surgeries"},
        follow_redirects=False,
    )
    assert switched.status_code == 303
    assert switched.headers["location"] == "/surgeries"

    surgeries = client.get("/surgeries")
    assert surgeries.status_code == 200
    assert "SW-UANL" in surgeries.text
    assert "SW-CODET" not in surgeries.text

    all_centers = client.post(
        "/admin/active-center",
        data={"center_id": "all", "next": "/surgeries"},
        follow_redirects=False,
    )
    assert all_centers.status_code == 303
    listed = client.get("/surgeries")
    assert "SW-UANL" in listed.text
    assert "SW-CODET" in listed.text
