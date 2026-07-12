"""Migration plus-cylinder → minus-cylinder."""

from app.clinical.astigmatism import plus_to_minus_cylinder
from app.clinical.refractive import evaluate_refraction
from app.models import ComplicationEvent, FollowUp, Surgery
from datetime import date, timedelta

from sqlalchemy.orm import Session

from tests.conftest import seed_users  # noqa: F401 — fixture via pytest


def test_migrate_positive_rows(db_session: Session, seed_users):
    from migrate_positive_cylinder import migrate

    surgery = Surgery(
        case_code="CASE-PLUS",
        surgery_date=date.today() - timedelta(days=40),
        eye="OD",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(surgery)
    db_session.flush()

    # Store a plus-cylinder row as if legacy data bypassed validation
    fu = FollowUp(
        surgery_id=surgery.id,
        institution_id="CODET",
        visit_date=surgery.surgery_date + timedelta(days=30),
        visit_type="month_1",
        postoperative_days=30,
        sphere=1.0,
        cylinder=1.0,
        axis=20.0,
        spherical_equivalent=1.5,
        residual_astigmatism=1.0,
        astigmatism_orientation="atr",  # stale
        spherical_equivalent_stars=3,
        astigmatism_stars=3,
        overall_refractive_stars=3,
        created_by_id=seed_users["admin"].id,
        is_voided=False,
    )
    db_session.add(fu)
    db_session.commit()

    stats = migrate(db_session)
    assert stats["converted_plus"] >= 1
    db_session.refresh(fu)
    assert fu.cylinder == -1.0
    assert fu.sphere == 2.0
    assert fu.axis == 110.0
    expected = evaluate_refraction(fu.sphere, fu.cylinder, fu.axis)
    assert fu.astigmatism_orientation == expected.astigmatism_orientation
    assert fu.spherical_equivalent == expected.spherical_equivalent


def test_plus_to_minus_helper():
    sph, cyl, ax = plus_to_minus_cylinder(-0.5, 1.0, 170)
    assert sph == 0.5
    assert cyl == -1.0
    assert ax == 80.0  # 260 → 80
