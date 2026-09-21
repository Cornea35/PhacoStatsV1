"""Surgery, permissions, and dashboard metric tests."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ComplicationEvent, RiskFactor, Surgery, User
from app.services.dashboard import compute_dashboard
from tests.conftest import login


def test_create_surgery_with_complication(client: TestClient, seed_users: dict[str, User]):
    login(client, "admin", "admin123")
    response = client.post(
        "/surgeries/new",
        data={
            "case_code": "CASE-T001",
            "surgery_date": "2026-01-15",
            "eye": "OD",
            "technique": "Phacoemulsification",
            "notes": "Synthetic only",
            "surgeon_id": str(seed_users["surgeon"].id),
            "risk_codes": ["dense_cataract", "small_pupil"],
            "complication_occurred": "on",
            "complication_type": "pcr",
            "surgical_stage": "nucleus_emulsification",
            "vitreous_loss": "true",
            "anterior_vitrectomy": "true",
            "fragments_to_posterior": "false",
            "retina_intervention": "false",
            "iol_position": "sulcus",
            "capsular_tension_ring": "false",
            "segment_ring_suture": "false",
            "f2_assistant_help": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/surgeries"

    list_page = client.get("/surgeries")
    assert "CASE-T001" in list_page.text
    assert "RCP" in list_page.text


def test_create_surgery_without_complication(client: TestClient, seed_users: dict[str, User]):
    login(client, "surgeon", "surgeon123")
    response = client.post(
        "/surgeries/new",
        data={
            "case_code": "CASE-T002",
            "surgery_date": "2026-01-20",
            "eye": "OS",
            "technique": "Phacoemulsification",
            "notes": "",
            "surgeon_id": str(seed_users["surgeon"].id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_surgeon_cannot_see_others_cases(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    other = Surgery(
        case_code="CASE-OTHER",
        surgery_date=date(2026, 2, 1),
        eye="OS",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon2"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(other)
    db_session.commit()

    login(client, "surgeon", "surgeon123")
    response = client.get(f"/surgeries/{other.id}", follow_redirects=False)
    assert response.status_code == 303


def test_dashboard_metrics(db_session: Session, seed_users: dict[str, User]):
    s1 = Surgery(
        case_code="CASE-D1",
        surgery_date=date(2026, 3, 1),
        eye="OD",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        risk_factors=[RiskFactor(code="dense_cataract")],
        complication=ComplicationEvent(occurred=False),
    )
    s2 = Surgery(
        case_code="CASE-D2",
        surgery_date=date(2026, 3, 10),
        eye="OS",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(
            occurred=True,
            complication_type="pcr",
            surgical_stage="cortex_removal",
            vitreous_loss=True,
            anterior_vitrectomy=True,
            fragments_to_posterior=False,
            retina_intervention=False,
            iol_position="bag",
            capsular_tension_ring=False,
            segment_ring_suture=False,
            f2_assistant_help=True,
        ),
    )
    s3 = Surgery(
        case_code="CASE-D3",
        surgery_date=date(2026, 4, 5),
        eye="OD",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add_all([s1, s2, s3])
    db_session.commit()

    stats = compute_dashboard(db_session)
    assert stats.total_surgeries == 3
    assert stats.total_complications == 1
    assert stats.complication_rate_pct == round(100 / 3, 2)
    assert stats.total_pcr == 1
    assert any("Aspiración" in label for label in stats.stage_labels)

    march = compute_dashboard(
        db_session,
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
    )
    assert march.total_surgeries == 2
    assert march.total_complications == 1


def test_dashboard_page(client: TestClient):
    login(client, "admin", "admin123")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "complicaciones" in response.text.lower()
    assert "Factores de riesgo más frecuentes" in response.text
    assert "chartRisks" in response.text
    assert "dashboard.js?v=" in response.text
    assert '"risks"' in response.text
    assert "Totales" in response.text
    assert "Este mes" in response.text
    assert 'id="surgeon_id"' in response.text
    assert "Vista institucional (todos los cirujanos)" in response.text

    month_page = client.get("/dashboard?period=month&month=2026-03")
    assert month_page.status_code == 200
    assert "Marzo 2026" in month_page.text


def test_admin_dashboard_surgeon_filter(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    db_session.add_all(
        [
            Surgery(
                case_code="CASE-F1",
                surgery_date=date(2026, 5, 1),
                eye="OD",
                technique="Phacoemulsification",
                surgeon_id=seed_users["surgeon"].id,
                created_by_id=seed_users["admin"].id,
                complication=ComplicationEvent(occurred=False),
            ),
            Surgery(
                case_code="CASE-F2",
                surgery_date=date(2026, 5, 2),
                eye="OS",
                technique="Phacoemulsification",
                surgeon_id=seed_users["surgeon2"].id,
                created_by_id=seed_users["admin"].id,
                complication=ComplicationEvent(occurred=False),
            ),
        ]
    )
    db_session.commit()

    login(client, "admin", "admin123")
    filtered = client.get(f"/dashboard?surgeon_id={seed_users['surgeon'].id}")
    assert filtered.status_code == 200
    assert "Vista filtrada: Surgeon Test" in filtered.text
    assert 'selected">Surgeon Test</option>' in filtered.text or (
        f'value="{seed_users["surgeon"].id}"' in filtered.text
        and "selected" in filtered.text
    )
    assert '<div class="kpi-value">1</div>' in filtered.text

    all_again = client.get("/dashboard?surgeon_id=")
    assert all_again.status_code == 200
    assert "Vista institucional (todos los cirujanos)" in all_again.text
    assert '<div class="kpi-value">2</div>' in all_again.text

    login(client, "surgeon", "surgeon123")
    surgeon_dash = client.get("/dashboard")
    assert surgeon_dash.status_code == 200
    assert 'id="surgeon_id"' not in surgeon_dash.text
    assert "Vista filtrada a sus cirugías" in surgeon_dash.text


def _seed_search_cases(db_session: Session, seed_users: dict[str, User]) -> None:
    db_session.add_all(
        [
            Surgery(
                case_code="SEARCH-A1",
                surgery_date=date(2026, 5, 1),
                eye="OD",
                technique="Phacoemulsification",
                surgeon_id=seed_users["surgeon"].id,
                created_by_id=seed_users["admin"].id,
                reintervention_needed=False,
                complication=ComplicationEvent(occurred=False),
            ),
            Surgery(
                case_code="SEARCH-B2",
                surgery_date=date(2026, 5, 2),
                eye="OS",
                technique="Phacoemulsification",
                surgeon_id=seed_users["surgeon"].id,
                created_by_id=seed_users["admin"].id,
                reintervention_needed=True,
                complication=ComplicationEvent(
                    occurred=True,
                    complication_type="pcr",
                    surgical_stage="cortex_removal",
                    vitreous_loss=True,
                    anterior_vitrectomy=True,
                    fragments_to_posterior=False,
                    retina_intervention=False,
                    iol_position="bag",
                    capsular_tension_ring=False,
                    segment_ring_suture=False,
                    f2_assistant_help=False,
                ),
            ),
            Surgery(
                case_code="OTHER-X9",
                surgery_date=date(2026, 5, 3),
                eye="OD",
                technique="Phacoemulsification",
                surgeon_id=seed_users["surgeon2"].id,
                created_by_id=seed_users["admin"].id,
                reintervention_needed=True,
                complication=ComplicationEvent(occurred=False),
            ),
        ]
    )
    db_session.commit()


def test_surgeries_list_search_filters_for_all_roles(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    _seed_search_cases(db_session, seed_users)

    # Admin: clinical list + code search
    login(client, "admin", "admin123")
    page = client.get("/surgeries")
    assert page.status_code == 200
    assert "Código de cirugía" in page.text
    assert "SEARCH-A1" in page.text
    assert "OTHER-X9" in page.text

    by_code = client.get("/surgeries?q=search-b")
    assert by_code.status_code == 200
    assert "SEARCH-B2" in by_code.text
    assert "SEARCH-A1" not in by_code.text

    with_comp = client.get("/surgeries?complication=yes")
    assert "SEARCH-B2" in with_comp.text
    assert "SEARCH-A1" not in with_comp.text

    # Coordinator: ops list (Sí/No only) + same filters within institution
    login(client, "coord", "coord123")
    coord_page = client.get("/surgeries")
    assert coord_page.status_code == 200
    assert "Vista operativa" in coord_page.text
    assert "SEARCH-A1" in coord_page.text
    assert "RCP (ruptura" not in coord_page.text
    assert client.get("/surgeries/new").status_code == 403

    # Surgeon: only own cases
    login(client, "surgeon", "surgeon123")
    own = client.get("/surgeries")
    assert "SEARCH-A1" in own.text
    assert "SEARCH-B2" in own.text
    assert "OTHER-X9" not in own.text
    assert "Vista filtrada a sus cirugías" in own.text


def test_edit_surgery_by_account_type(
    client: TestClient,
    db_session: Session,
    seed_users: dict[str, User],
):
    surgery = Surgery(
        case_code="EDIT-ROLE-1",
        surgery_date=date(2026, 6, 1),
        eye="OD",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    other = Surgery(
        case_code="EDIT-ROLE-2",
        surgery_date=date(2026, 6, 2),
        eye="OS",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon2"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add_all([surgery, other])
    db_session.commit()
    db_session.refresh(surgery)
    db_session.refresh(other)

    # Admin can edit any case; empty surgeon_id must not 422
    login(client, "admin", "admin123")
    assert client.get(f"/surgeries/{surgery.id}/edit").status_code == 200
    assert 'action="/surgeries/%s/edit"' % surgery.id in client.get(
        f"/surgeries/{surgery.id}/edit"
    ).text
    empty = client.post(
        f"/surgeries/{surgery.id}/edit",
        data={
            "case_code": "EDIT-ROLE-1",
            "surgery_date": "2026-06-01",
            "eye": "OD",
            "technique": "Phacoemulsification",
            "notes": "",
            "surgeon_id": "",
            "iol_type": "",
        },
        follow_redirects=False,
    )
    assert empty.status_code == 303
    assert empty.headers["location"] == f"/surgeries/{surgery.id}/edit"

    ok = client.post(
        f"/surgeries/{surgery.id}/edit",
        data={
            "case_code": "EDIT-ROLE-1A",
            "surgery_date": "2026-06-03",
            "eye": "OS",
            "technique": "Phacoemulsification",
            "notes": "admin edit",
            "surgeon_id": str(seed_users["surgeon"].id),
            "iol_type": "",
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == f"/surgeries/{surgery.id}"
    db_session.refresh(surgery)
    assert surgery.case_code == "EDIT-ROLE-1A"
    assert surgery.eye == "OS"

    # Surgeon can edit own case
    login(client, "surgeon", "surgeon123")
    own_edit = client.post(
        f"/surgeries/{surgery.id}/edit",
        data={
            "case_code": "EDIT-ROLE-1B",
            "surgery_date": "2026-06-04",
            "eye": "OD",
            "technique": "Phacoemulsification",
            "notes": "surgeon edit",
            "surgeon_id": str(seed_users["surgeon"].id),
            "iol_type": "",
        },
        follow_redirects=False,
    )
    assert own_edit.status_code == 303
    assert own_edit.headers["location"] == f"/surgeries/{surgery.id}"

    # Surgeon cannot edit another surgeon's case
    denied = client.get(f"/surgeries/{other.id}/edit", follow_redirects=False)
    assert denied.status_code == 303
    assert denied.headers["location"] == "/surgeries"

    # Coordinator cannot edit clinical cases
    login(client, "coord", "coord123")
    assert client.get(f"/surgeries/{surgery.id}/edit").status_code == 403
    assert f'/surgeries/{surgery.id}/edit' not in client.get("/surgeries").text
