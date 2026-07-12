"""Coordinator role lockdown: ops access only, no clinical metrics."""

from datetime import date

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from io import BytesIO
from sqlalchemy.orm import Session

from app.constants import DEFAULT_INSTITUTION_CODE
from app.models import ComplicationEvent, ReinterventionFollowUp, Surgery, User
from app.permissions import Permission, has_permission
from app.services.ops_export import OPS_HEADERS
from tests.conftest import login


def _case(
    db: Session,
    seed_users: dict[str, User],
    *,
    code: str,
    institution_id: str = DEFAULT_INSTITUTION_CODE,
    complication: bool = False,
    surgeon_key: str = "surgeon",
) -> Surgery:
    s = Surgery(
        case_code=code,
        surgery_date=date(2026, 6, 1),
        eye="OD",
        technique="Phacoemulsification",
        institution_id=institution_id,
        surgeon_id=seed_users[surgeon_key].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(
            occurred=complication,
            complication_type="pcr" if complication else None,
            surgical_stage="cortex_removal" if complication else None,
            vitreous_loss=True if complication else None,
            anterior_vitrectomy=True if complication else None,
            fragments_to_posterior=False if complication else None,
            retina_intervention=False if complication else None,
            iol_position="bag" if complication else None,
            capsular_tension_ring=False if complication else None,
            segment_ring_suture=False if complication else None,
            f2_assistant_help=False if complication else None,
        ),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_coordinator_can_login(client: TestClient):
    login(client, "coord", "coord123")
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Inicio operativo" in page.text
    assert "Por cirujano" not in page.text
    assert "Factores de riesgo" not in page.text


def test_coordinator_sees_institution_surgeries_yes_no_complication(
    client: TestClient, db_session: Session, seed_users
):
    _case(db_session, seed_users, code="COORD-A1", complication=True)
    _case(db_session, seed_users, code="COORD-A2", complication=False)
    login(client, "coord", "coord123")
    page = client.get("/surgeries")
    assert page.status_code == 200
    assert "COORD-A1" in page.text
    assert "COORD-A2" in page.text
    # Complication only as Sí/No — no RCP type label in list
    assert "RCP (ruptura" not in page.text
    detail = client.get("/surgeries/" + str(
        db_session.query(Surgery).filter_by(case_code="COORD-A1").first().id
    ))
    assert "Hubo complicación" in detail.text
    assert "Sí" in detail.text
    assert "vitreous" not in detail.text.lower()
    assert "Aspiración de corteza" not in detail.text


def test_coordinator_reintervention_crud_and_audit(
    client: TestClient, db_session: Session, seed_users
):
    surgery = _case(db_session, seed_users, code="COORD-R1")
    login(client, "coord", "coord123")
    created = client.post(
        "/reinterventions/new",
        data={
            "surgery_id": str(surgery.id),
            "reintervention_required": "yes",
            "status": "scheduled",
            "reintervention_type": "ac_wash",
            "retina_related": "no",
            "reintervention_date": "2026-06-15",
            "notes": "Programada lavado CA",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    fu = db_session.query(ReinterventionFollowUp).filter_by(surgery_id=surgery.id).first()
    assert fu is not None
    assert any(r.action == "created" for r in fu.revisions)

    edited = client.post(
        f"/reinterventions/{fu.id}/edit",
        data={
            "reintervention_required": "yes",
            "status": "completed",
            "reintervention_type": "ac_wash",
            "retina_related": "no",
            "reintervention_date": "2026-06-16",
            "notes": "Completado lavado CA",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 303
    db_session.refresh(fu)
    assert fu.status == "completed"
    assert any(r.action == "updated" for r in fu.revisions)

    voided = client.post(
        f"/reinterventions/{fu.id}/void",
        data={"void_reason": "Error de captura"},
        follow_redirects=False,
    )
    assert voided.status_code == 303
    db_session.refresh(fu)
    assert fu.is_voided is True
    assert any(r.action == "voided" for r in fu.revisions)


def test_coordinator_blocked_from_clinical_routes(client: TestClient, db_session: Session, seed_users):
    surgery = _case(db_session, seed_users, code="COORD-B1")
    login(client, "coord", "coord123")
    assert client.get("/refractive").status_code == 403
    assert client.get("/admin/analytics").status_code == 403
    assert client.get("/admin/analytics/export").status_code == 403
    assert client.get("/users").status_code == 403
    assert client.get("/surgeries/new").status_code == 403
    assert client.get(f"/surgeries/{surgery.id}/edit").status_code == 403
    assert client.get(f"/surgeries/{surgery.id}/follow-ups/new").status_code == 403
    dash = client.get("/dashboard")
    assert "odds" not in dash.text.lower()
    assert "OR" not in dash.text or "operativo" in dash.text.lower()


def test_coordinator_cannot_see_other_institution(
    client: TestClient, db_session: Session, seed_users
):
    local = _case(db_session, seed_users, code="CODET-1", institution_id="CODET")
    other = _case(db_session, seed_users, code="OTHER-1", institution_id="OTHER")
    login(client, "coord", "coord123")
    listing = client.get("/surgeries")
    assert "CODET-1" in listing.text
    assert "OTHER-1" not in listing.text
    assert client.get(f"/surgeries/{other.id}").status_code == 403
    # Direct create on other institution surgery should 403
    resp = client.post(
        "/reinterventions/new",
        data={
            "surgery_id": str(other.id),
            "reintervention_required": "no",
            "status": "cancelled",
            "reintervention_type": "unspecified",
            "retina_related": "unknown",
            "notes": "x",
        },
    )
    assert resp.status_code == 403
    assert client.get(f"/surgeries/{local.id}").status_code == 200


def test_coordinator_export_columns_only(client: TestClient, db_session: Session, seed_users):
    _case(db_session, seed_users, code="EXP-1", complication=True)
    login(client, "coord", "coord123")
    resp = client.get("/surgeries/export.xlsx")
    assert resp.status_code == 200
    wb = load_workbook(BytesIO(resp.content))
    headers = [c.value for c in wb.active[1]]
    assert headers == OPS_HEADERS
    forbidden_tokens = {"odds ratio", "p-value", "estrellas", "spherical", "j0", "j45"}
    joined = " ".join(str(h).lower() for h in headers)
    for word in forbidden_tokens:
        assert word not in joined


def test_admin_and_surgeon_permissions_intact(client: TestClient, seed_users):
    assert has_permission(seed_users["admin"], Permission.VIEW_ADMIN_ANALYTICS)
    assert has_permission(seed_users["admin"], Permission.VIEW_REFRACTIVE)
    assert has_permission(seed_users["surgeon"], Permission.VIEW_REFRACTIVE)
    assert has_permission(seed_users["surgeon"], Permission.CREATE_SURGERY)
    assert has_permission(seed_users["surgeon"], Permission.MANAGE_REINTERVENTION)
    assert not has_permission(seed_users["coord"], Permission.VIEW_REFRACTIVE)
    assert not has_permission(seed_users["coord"], Permission.VIEW_ADMIN_ANALYTICS)

    login(client, "admin", "admin123")
    assert client.get("/admin/analytics").status_code == 200
    assert client.get("/refractive").status_code == 200
    assert "Por cirujano" in client.get("/dashboard").text

    login(client, "surgeon", "surgeon123")
    assert client.get("/refractive").status_code == 200
    assert client.get("/surgeries/new").status_code == 200
