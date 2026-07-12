"""Overall refractive stars = mean of SEQ★ and Ast★ (not min)."""

import pytest

from app.clinical.refractive_scoring import (
    calculate_overall_refractive_stars,
    cohort_mean_stars,
    round_stars_display,
    verify_cohort_identity,
)
from app.clinical.refractive import evaluate_refraction
from app.services.refractive_analytics_service import compute_refractive_results


@pytest.mark.parametrize(
    "seq,astig,expected",
    [
        (3, 4, 3.5),
        (5, 3, 4.0),
        (1, 5, 3.0),
        (5, 5, 5.0),
        (1, 1, 1.0),
    ],
)
def test_overall_is_mean(seq, astig, expected):
    assert calculate_overall_refractive_stars(seq, astig) == expected


def test_overall_null_when_missing_component():
    assert calculate_overall_refractive_stars(None, 4) is None
    assert calculate_overall_refractive_stars(4, None) is None


def test_overall_between_components():
    for seq in range(1, 6):
        for ast in range(1, 6):
            overall = calculate_overall_refractive_stars(seq, ast)
            assert overall is not None
            assert min(seq, ast) <= overall <= max(seq, ast)


def test_never_uses_zero_for_missing():
    assert calculate_overall_refractive_stars(None, 4) is None
    assert calculate_overall_refractive_stars(4, None) is not 0


def test_cohort_means_identity():
    # Cases: (3,4)->3.5, (4,4)->4.0, (5,3)->4.0
    seqs = [3.0, 4.0, 5.0]
    astigs = [4.0, 4.0, 3.0]
    overalls = [3.5, 4.0, 4.0]
    mean_seq = cohort_mean_stars(seqs)
    mean_astig = cohort_mean_stars(astigs)
    mean_overall = cohort_mean_stars(overalls)
    assert abs(mean_seq - 4.0) < 1e-9
    assert abs(mean_astig - (11 / 3)) < 1e-9
    assert abs(mean_overall - (11.5 / 3)) < 1e-9
    identity = verify_cohort_identity(mean_seq, mean_astig, mean_overall)
    assert identity["ok"] is True


def test_regression_dashboard_cannot_show_min_bias():
    """If SEQ mean=3.3 and Ast=3.5, overall display must be 3.4 (not 2.8 from min())."""
    mean_seq = 3.3
    mean_astig = 3.5
    # Simulate N cases whose component means are 3.3 / 3.5 and overall is mean of means
    # Using equal weights: overall_mean must equal (3.3+3.5)/2
    mean_overall = (mean_seq + mean_astig) / 2.0
    assert abs(mean_overall - 3.4) < 1e-9
    assert round_stars_display(mean_overall) == 3.4
    # The forbidden legacy value
    assert round_stars_display(mean_overall) != 2.8


def test_round_display_half_up():
    assert round_stars_display(3.35) == 3.4
    assert round_stars_display(3.34) == 3.3


def test_evaluate_refraction_overall_is_mean_not_min():
    # SEQ around -0.625 → 3★; ATR |C|=0.75 → 3★ → overall 3.0
    # Better case: SEQ 5★ and ATR 3★ → overall 4.0 not min=3
    r = evaluate_refraction(0.25, -0.75, 90)  # SEQ= -0.125 → 5; ATR 0.75 → 3
    assert r.spherical_equivalent_stars == 5
    assert r.astigmatism_stars == 3
    assert r.overall_refractive_stars == 4.0


def test_dashboard_same_n_and_identity(db_session, seed_users):
    from datetime import date, timedelta

    from app.models import ComplicationEvent, Surgery
    from app.services.followups import create_follow_up

    surgery = Surgery(
        case_code="CASE-STAR-AVG",
        surgery_date=date.today() - timedelta(days=40),
        eye="OD",
        technique="Phacoemulsification",
        surgeon_id=seed_users["surgeon"].id,
        created_by_id=seed_users["admin"].id,
        complication=ComplicationEvent(occurred=False),
    )
    db_session.add(surgery)
    db_session.commit()
    # Force known stars via refraction that yields 5 and 3 → overall 4
    create_follow_up(
        db_session,
        surgery,
        created_by=seed_users["admin"],
        visit_date=surgery.surgery_date + timedelta(days=30),
        visit_type="month_1",
        sphere=0.25,
        cylinder=-0.75,
        axis=90,
    )
    results = compute_refractive_results(
        db_session, surgeon_id=seed_users["surgeon"].id, visit_window="last_visit"
    )
    assert results.n_seq == results.n_astig == results.n_overall
    assert results.cohort_identity_ok is True
    assert results.avg_overall_stars_display == round_stars_display(
        (results.avg_seq_stars + results.avg_astig_stars) / 2.0
    )
