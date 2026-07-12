"""Clinical refraction: minus-cylinder, orientation, SEQ, J0/J45, centroid."""

import pytest

from app.clinical.astigmatism import (
    classify_orientation,
    plus_to_minus_cylinder,
    require_negative_cylinder,
)
from app.clinical.refractive import (
    astigmatism_stars,
    evaluate_refraction,
    seq_stars,
    spherical_equivalent,
)
from app.clinical.vector_analysis import axis_from_j0_j45, j0_j45
from app.statistics.centroid import compute_centroid
from app.statistics.double_angle import double_angle_xy


def test_seq_formula_uses_signed_cylinder():
    assert spherical_equivalent(-1.0, -1.0) == -1.5
    assert spherical_equivalent(+0.50, -0.75) == 0.125


def test_rejects_positive_cylinder():
    with pytest.raises(Exception):
        require_negative_cylinder(0.75)
    with pytest.raises(Exception):
        evaluate_refraction(0.0, 0.75, 90)


def test_seq_stars_myopia_and_emmetropia():
    assert seq_stars(0) == 5
    assert seq_stars(-0.25) == 5
    assert seq_stars(-0.5) == 4
    assert seq_stars(-0.75) == 3
    assert seq_stars(-1.0) == 2
    assert seq_stars(-2.0) == 1


def test_seq_stars_hyperopia():
    assert seq_stars(0.25) == 5
    assert seq_stars(0.6) == 4
    assert seq_stars(1.0) == 3
    assert seq_stars(1.75) == 2
    assert seq_stars(2.5) == 1


@pytest.mark.parametrize(
    "axis,expected",
    [
        (0, "wtr"),
        (30, "wtr"),
        (31, "oblique"),
        (59, "oblique"),
        (60, "atr"),
        (90, "atr"),
        (120, "atr"),
        (121, "oblique"),
        (149, "oblique"),
        (150, "wtr"),
        (180, "wtr"),
    ],
)
def test_orientation_minus_cylinder_boundaries(axis, expected):
    assert classify_orientation(-0.5, axis) == expected


def test_orientation_none_when_plano_cylinder():
    assert classify_orientation(0, None) == "none"


def test_astig_stars_wtr_vs_atr_tables_unchanged():
    # WTR looser: |C|=0.50 → 5★
    assert astigmatism_stars(-0.5, "wtr") == 5
    assert astigmatism_stars(-0.75, "wtr") == 4
    # ATR/oblique stricter: |C|=0.50 → 4★
    assert astigmatism_stars(-0.5, "atr") == 4
    assert astigmatism_stars(-0.25, "oblique") == 5


def test_overall_is_mean_not_min():
    r = evaluate_refraction(0.25, -0.75, 90)  # 5★ SEQ, 3★ ATR → 4.0
    assert r.overall_refractive_stars == (
        r.spherical_equivalent_stars + r.astigmatism_stars
    ) / 2
    assert r.overall_refractive_stars != min(
        r.spherical_equivalent_stars, r.astigmatism_stars
    )


def test_j0_j45_and_double_angle():
    # C=-1.0 @ 0° → J0 = 0.5, J45 = 0; plot (1, 0)
    j0, j45 = j0_j45(-1.0, 0)
    assert abs(j0 - 0.5) < 1e-6
    assert abs(j45) < 1e-6
    x, y = double_angle_xy(-1.0, 0)
    assert abs(x - 1.0) < 1e-4
    assert abs(y) < 1e-4

    # C=-1.0 @ 90° → J0 = -0.5
    j0, j45 = j0_j45(-1.0, 90)
    assert abs(j0 + 0.5) < 1e-6
    x, y = double_angle_xy(-1.0, 90)
    assert abs(x + 1.0) < 1e-4


def test_centroid_mean_axis_not_arithmetic():
    # Two equal-magnitude orthogonal vectors cancel magnitude; axis from mean J
    j0s = [0.5, -0.5]
    j45s = [0.0, 0.0]
    c = compute_centroid(j0s, j45s)
    assert abs(c.magnitude) < 1e-6
    assert c.mean_axis is None or abs(c.magnitude) < 1e-6

    j0s = [0.5, 0.5]
    j45s = [0.0, 0.0]
    c = compute_centroid(j0s, j45s)
    assert abs(c.magnitude - 1.0) < 1e-3
    assert c.mean_axis is not None
    assert abs(c.mean_axis - 0.0) < 1.0 or abs(c.mean_axis - 180.0) < 1.0


def test_axis_from_j0_j45():
    assert axis_from_j0_j45(0.5, 0.0) in (0.0, 180.0) or abs(axis_from_j0_j45(0.5, 0.0) or 0) < 1e-6
    ax = axis_from_j0_j45(-0.5, 0.0)
    assert ax is not None
    assert abs(ax - 90.0) < 1.0


def test_plus_to_minus_migration():
    sph, cyl, ax = plus_to_minus_cylinder(1.0, +1.0, 20)
    assert sph == 2.0
    assert cyl == -1.0
    assert ax == 110.0
    # axis wrap
    sph, cyl, ax = plus_to_minus_cylinder(0.0, +0.5, 100)
    assert cyl == -0.5
    assert ax == 10.0  # 190 - 180


def test_evaluate_includes_j_components():
    r = evaluate_refraction(+0.50, -0.75, 180)
    assert r.astigmatism_orientation == "wtr"
    assert r.j0 != 0 or r.residual_astigmatism == 0
    assert r.spherical_equivalent == spherical_equivalent(0.50, -0.75)
