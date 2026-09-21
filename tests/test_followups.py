"""Follow-up CRUD and refractive dashboard tests."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ComplicationEvent, Surgery, User
from app.services.followups import create_follow_up
from app.services.refractive import compute_refractive_results
from tests.conftest import login


def _surgery(db_session: Session, seed_users: dict[str, User], *, days_ago: int = 40) -> Surgery:
    surgery = Surgery(
        case_code="CASE-RX-01",
        surgery_date=date.today() - timedelta(days=days_ago),
        eye="OD",
        technique="Phacoemulsification",
        iol_type="panoptix",
        institution_id="CODET",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(surgery)
    db_session.commit()
    db_session.refresh(surgery)
    return surgery


def test_create_follow_up_computes_stars(db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    fu = create_follow_up(
        db_session,
        surgery,
        created_by=seed_users["admin"],
        visit_date=surgery.surgery_date + timedelta(days=30),
        visit_type="month_1",
        sphere=0.0,
        cylinder=-0.25,
        axis=90,
        udva_snellen="20/25",
        cdva_snellen="20/20",
    )
    assert fu.postoperative_days == 30
    assert fu.spherical_equivalent == -0.125
    assert fu.astigmatism_orientation == "atr"  # axis 90° = ATR (minus cyl)
    assert fu.spherical_equivalent_stars == 5
    assert fu.astigmatism_stars == 5
    assert fu.overall_refractive_stars == 5.0
    assert fu.udva_logmar is not None


def test_follow_up_http_create(client: TestClient, db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    login(client, "surgeon", "surgeon123")
    visit = (surgery.surgery_date + timedelta(days=28)).isoformat()
    response = client.post(
        f"/surgeries/{surgery.id}/follow-ups/new",
        data={
            "visit_date": visit,
            "visit_type": "month_1",
            "sphere": "-0.25",
            "cylinder": "-0.50",
            "axis": "15",
            "udva_snellen": "20/30",
            "cdva_snellen": "20/20",
            "notes": "Demo sin PII",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(surgery)
    assert len(surgery.follow_ups) == 1
    fu = surgery.follow_ups[0]
    assert fu.astigmatism_orientation == "wtr"  # axis 15° = WTR (minus cyl)
    assert fu.is_voided is False


def test_rejects_positive_cylinder_http(client: TestClient, db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    login(client, "surgeon", "surgeon123")
    visit = (surgery.surgery_date + timedelta(days=28)).isoformat()
    response = client.post(
        f"/surgeries/{surgery.id}/follow-ups/new",
        data={
            "visit_date": visit,
            "visit_type": "month_1",
            "sphere": "0.50",
            "cylinder": "0.75",
            "axis": "90",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(surgery)
    assert len(surgery.follow_ups) == 0


def test_refractive_export_endpoints(client: TestClient, db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    create_follow_up(
        db_session,
        surgery,
        created_by=seed_users["admin"],
        visit_date=surgery.surgery_date + timedelta(days=30),
        visit_type="month_1",
        sphere=0.0,
        cylinder=-0.50,
        axis=10,
    )
    login(client, "admin", "admin123")
    xlsx = client.get("/refractive/export.xlsx")
    assert xlsx.status_code == 200
    assert "spreadsheet" in xlsx.headers.get("content-type", "")
    csv_r = client.get("/refractive/export.csv")
    assert csv_r.status_code == 200
    assert b"sphere" in csv_r.content
    assert b"j0" in csv_r.content
    pdf = client.get("/refractive/export.pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_refractive_dashboard_metrics(db_session: Session, seed_users):
    surgery = _surgery(db_session, seed_users)
    create_follow_up(
        db_session,
        surgery,
        created_by=seed_users["admin"],
        visit_date=surgery.surgery_date + timedelta(days=30),
        visit_type="month_1",
        sphere=0.25,
        cylinder=-0.50,
        axis=100,
        udva_snellen="20/25",
    )
    results = compute_refractive_results(
        db_session,
        surgeon_id=seed_users["surgeon"].id,
        visit_window="last_visit",
    )
    assert results.n_cases >= 1
    assert results.avg_overall_stars is not None
    assert "5" in results.seq_star_pct
    assert results.polar_points
    assert sum(results.seq_star_pct.values()) == 100.0 or results.n_cases == 0


def test_refractive_page_not_on_dashboard(client: TestClient, seed_users):
    login(client, "admin", "admin123")
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "EQ. ESFÉRICO" not in dash.text
    assert 'href="/refractive"' in dash.text
    response = client.get("/refractive")
    assert response.status_code == 200
    assert "Resultados refractivos" in response.text
    assert "EQ. ESFÉRICO" in response.text


def test_refractive_surgeon_filter_accepts_empty_and_id(
    client: TestClient,
    db_session: Session,
    seed_users,
):
    """Empty rx_surgeon (Todos) must not 422; selecting a surgeon must 200."""
    login(client, "admin", "admin123")
    empty = client.get("/refractive?rx_surgeon=")
    assert empty.status_code == 200
    assert 'name="rx_surgeon"' in empty.text

    sid = seed_users["surgeon"].id
    filtered = client.get(f"/refractive?rx_surgeon={sid}")
    assert filtered.status_code == 200
    assert f'value="{sid}"' in filtered.text
    assert "selected" in filtered.text

    export = client.get(f"/refractive/export.csv?rx_surgeon=")
    assert export.status_code == 200
