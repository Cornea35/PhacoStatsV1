"""Post-operative reintervention module tests (admin/coordinator)."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ComplicationEvent, ReinterventionFollowUp, Surgery, User
from app.services.reinterventions import ReinterventionValidationError, create_reintervention
from tests.conftest import login


def _surgery(db_session: Session, seed_users: dict[str, User], *, institution_id: str = "CODET") -> Surgery:
    surgery = Surgery(
        case_code="CASE-POSTOP",
        surgery_date=date(2026, 4, 1),
        eye="OD",
        technique="Phacoemulsification",
        institution_id=institution_id,
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(surgery)
    db_session.commit()
    db_session.refresh(surgery)
    return surgery


def test_admin_can_save_reintervention(client: TestClient, db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    login(client, "admin", "admin123")
    response = client.post(
        "/reinterventions/new",
        data={
            "surgery_id": str(surgery.id),
            "reintervention_required": "yes",
            "status": "completed",
            "reintervention_type": "anterior_vitrectomy",
            "retina_related": "no",
            "reintervention_date": "2026-04-10",
            "notes": "Vitrectomía anterior sintética de demostración.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    fu = db_session.query(ReinterventionFollowUp).filter_by(surgery_id=surgery.id).first()
    assert fu is not None
    assert fu.reintervention_required == "yes"
    assert "Vitrectomía" in (fu.notes or "")
    assert fu.revisions


def test_coordinator_can_save_reintervention(client: TestClient, db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    login(client, "coord", "coord123")
    detail = client.get(f"/surgeries/{surgery.id}")
    assert detail.status_code == 200
    assert "Detalle administrativo mínimo" in detail.text
    assert "RCP" not in detail.text or "Hubo complicación" in detail.text

    response = client.post(
        "/reinterventions/new",
        data={
            "surgery_id": str(surgery.id),
            "reintervention_required": "yes",
            "status": "completed",
            "reintervention_type": "iol_reposition",
            "retina_related": "no",
            "reintervention_date": "2026-04-12",
            "notes": "Reposición de LIO realizada en quirófano.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    fu = db_session.query(ReinterventionFollowUp).filter_by(surgery_id=surgery.id).first()
    assert fu is not None
    assert "Reposición de LIO" in (fu.notes or "")


def test_surgeon_can_save_own_reintervention(client: TestClient, db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    login(client, "surgeon", "surgeon123")
    detail = client.get(f"/surgeries/{surgery.id}")
    assert detail.status_code == 200
    assert "Registrar / actualizar reintervención" in detail.text

    response = client.post(
        "/reinterventions/new",
        data={
            "surgery_id": str(surgery.id),
            "reintervention_required": "yes",
            "status": "completed",
            "reintervention_type": "other",
            "retina_related": "unknown",
            "reintervention_date": "2026-04-12",
            "notes": "Seguimiento del cirujano titular.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    fu = db_session.query(ReinterventionFollowUp).filter_by(surgery_id=surgery.id).first()
    assert fu is not None
    assert "cirujano titular" in (fu.notes or "")


def test_surgeon_cannot_save_others_reintervention(
    client: TestClient, db_session: Session, seed_users
):
    other = Surgery(
        case_code="CASE-OTHER-REINT",
        surgery_date=date(2026, 4, 2),
        eye="OS",
        technique="Phacoemulsification",
        institution_id="CODET",
        surgeon_id=seed_users["surgeon2"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    login(client, "surgeon", "surgeon123")
    response = client.post(
        "/reinterventions/new",
        data={
            "surgery_id": str(other.id),
            "reintervention_required": "yes",
            "status": "completed",
            "reintervention_type": "other",
            "retina_related": "unknown",
            "reintervention_date": "2026-04-12",
            "notes": "No debería guardarse",
        },
    )
    assert response.status_code == 403


def test_reintervention_requires_date_when_completed(db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    try:
        create_reintervention(
            db_session,
            surgery,
            actor=seed_users["coord"],
            reintervention_required="yes",
            reintervention_date=None,
            reintervention_type="unspecified",
            retina_related="unknown",
            status="completed",
            notes="nota",
        )
        assert False, "Expected ReinterventionValidationError"
    except ReinterventionValidationError:
        pass
