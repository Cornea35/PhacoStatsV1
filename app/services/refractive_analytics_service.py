"""Cohort aggregation for refractive star dashboards. Backend is source of truth."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from statistics import median
from typing import Any, Literal

from sqlalchemy.orm import Session, joinedload

from app.clinical.refractive_scoring import (
    OVERALL_BIN_ORDER,
    cohort_mean_stars,
    overall_star_bin,
    round_stars_display,
    verify_cohort_identity,
)
from app.models import FollowUp, Surgery, User
from app.statistics.centroid import compute_centroid
from app.statistics.double_angle import case_vector

VisitWindow = Literal[
    "last_visit",
    "month_1",
    "month_3",
    "month_6",
    "year_1",
    "custom",
    "all",
]

_WINDOW_DAYS: dict[str, tuple[int, int]] = {
    "month_1": (21, 45),
    "month_3": (75, 120),
    "month_6": (150, 210),
    "year_1": (300, 420),
}


@dataclass
class RefractiveResults:
    n_cases: int = 0
    n_complete: int = 0
    n_seq_only: int = 0
    n_astig_only: int = 0
    n_excluded_missing: int = 0
    n_follow_ups: int = 0
    n_seq: int = 0
    n_astig: int = 0
    n_overall: int = 0
    avg_seq_stars: float | None = None
    avg_astig_stars: float | None = None
    avg_overall_stars: float | None = None
    avg_seq_stars_display: float | None = None
    avg_astig_stars_display: float | None = None
    avg_overall_stars_display: float | None = None
    mean_seq: float | None = None
    median_seq: float | None = None
    mean_abs_seq: float | None = None
    pct_seq_within: dict[str, float] = field(default_factory=dict)
    mean_residual_cyl: float | None = None
    mean_cylinder_signed: float | None = None
    pct_cyl_le_050: float | None = None
    pct_cyl_le_100: float | None = None
    seq_star_pct: dict[str, float] = field(default_factory=dict)
    astig_star_pct: dict[str, float] = field(default_factory=dict)
    overall_star_pct: dict[str, float] = field(default_factory=dict)
    overall_bin_pct: dict[str, float] = field(default_factory=dict)
    orientation_pct: dict[str, float] = field(default_factory=dict)
    orientation_counts: dict[str, int] = field(default_factory=dict)
    mean_j0: float | None = None
    mean_j45: float | None = None
    mean_udva_logmar: float | None = None
    mean_cdva_logmar: float | None = None
    followup_completeness_pct: float | None = None
    cohort_identity_ok: bool = True
    cohort_identity_delta: float | None = None
    polar_points: list[dict[str, Any]] = field(default_factory=list)
    mean_vector: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mean(values: list[float]) -> float | None:
    return cohort_mean_stars(values)


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * count / total, 1)


def _star_distribution(stars: list[int | float]) -> dict[str, float]:
    """Integer 1–5 distribution (SEQ / astigmatism)."""
    ints = [int(round(s)) for s in stars]
    total = len(ints)
    return {str(s): _pct(sum(1 for x in ints if x == s), total) for s in range(1, 6)}


def _overall_bin_distribution(overalls: list[float]) -> dict[str, float]:
    total = len(overalls)
    counts = Counter(overall_star_bin(o) for o in overalls)
    return {b: _pct(counts.get(b, 0), total) for b in OVERALL_BIN_ORDER}


def _pick_follow_up(
    follow_ups: list[FollowUp],
    *,
    visit_window: VisitWindow,
    date_from: date | None,
    date_to: date | None,
) -> FollowUp | None:
    active = [f for f in follow_ups if not f.is_voided]
    if not active:
        return None
    active.sort(key=lambda f: (f.visit_date, f.id))

    if visit_window in {"last_visit", "all"}:
        return active[-1]

    if visit_window == "custom":
        filtered = active
        if date_from:
            filtered = [f for f in filtered if f.visit_date >= date_from]
        if date_to:
            filtered = [f for f in filtered if f.visit_date <= date_to]
        return filtered[-1] if filtered else None

    lo, hi = _WINDOW_DAYS.get(visit_window, (0, 10_000))
    in_window = [f for f in active if lo <= f.postoperative_days <= hi]
    if in_window:
        return in_window[-1]
    mid = (lo + hi) / 2
    return min(active, key=lambda f: abs(f.postoperative_days - mid))


def _case_components(fu: FollowUp) -> tuple[int | None, int | None, float | None]:
    seq_s = fu.spherical_equivalent_stars
    ast_s = fu.astigmatism_stars
    # Prefer stored overall if present; else recompute mean
    if seq_s is None or ast_s is None:
        return seq_s, ast_s, None
    overall = fu.overall_refractive_stars
    if overall is None:
        overall = (float(seq_s) + float(ast_s)) / 2.0
    return int(seq_s), int(ast_s), float(overall)


def compute_refractive_results(
    db: Session,
    *,
    surgeon_id: int | None = None,
    institution_id: str | None = None,
    eye: str | None = None,
    iol_type: str | None = None,
    visit_window: VisitWindow = "last_visit",
    date_from: date | None = None,
    date_to: date | None = None,
    surgery_date_from: date | None = None,
    surgery_date_to: date | None = None,
) -> RefractiveResults:
    """All three star KPIs use the same selected follow-up per surgery (same filters)."""
    q = (
        db.query(Surgery)
        .options(joinedload(Surgery.follow_ups), joinedload(Surgery.surgeon))
        .order_by(Surgery.surgery_date.desc())
    )
    if surgeon_id is not None:
        q = q.filter(Surgery.surgeon_id == surgeon_id)
    if institution_id:
        q = q.filter(Surgery.institution_id == institution_id)
    if eye:
        q = q.filter(Surgery.eye == eye)
    if iol_type:
        q = q.filter(Surgery.iol_type == iol_type)
    if surgery_date_from:
        q = q.filter(Surgery.surgery_date >= surgery_date_from)
    if surgery_date_to:
        q = q.filter(Surgery.surgery_date <= surgery_date_to)

    surgeries = q.all()
    selected: list[tuple[Surgery, FollowUp]] = []
    with_any_fu = 0

    for surgery in surgeries:
        fus = list(surgery.follow_ups or [])
        if any(not f.is_voided for f in fus):
            with_any_fu += 1
        picked = _pick_follow_up(
            fus,
            visit_window=visit_window,
            date_from=date_from,
            date_to=date_to,
        )
        if picked is not None:
            selected.append((surgery, picked))

    empty_orient = {"wtr": 0.0, "atr": 0.0, "oblique": 0.0, "none": 0.0}
    result = RefractiveResults(
        n_cases=len(selected),
        n_follow_ups=sum(
            1 for s in surgeries for f in (s.follow_ups or []) if not f.is_voided
        ),
        followup_completeness_pct=_pct(with_any_fu, len(surgeries)) if surgeries else 0.0,
    )

    if not selected:
        result.pct_seq_within = {"0.25": 0.0, "0.50": 0.0, "0.75": 0.0, "1.00": 0.0}
        result.seq_star_pct = {str(s): 0.0 for s in range(1, 6)}
        result.astig_star_pct = {str(s): 0.0 for s in range(1, 6)}
        result.overall_star_pct = {str(s): 0.0 for s in range(1, 6)}
        result.overall_bin_pct = {b: 0.0 for b in OVERALL_BIN_ORDER}
        result.orientation_pct = empty_orient
        result.orientation_counts = {k: 0 for k in empty_orient}
        result.mean_vector = {
            "x": 0.0,
            "y": 0.0,
            "magnitude": 0.0,
            "mean_j0": 0.0,
            "mean_j45": 0.0,
            "mean_axis": None,
        }
        return result

    # Same cohort lists — only complete cases enter all three means
    seq_star_vals: list[float] = []
    astig_star_vals: list[float] = []
    overall_vals: list[float] = []
    complete_pairs: list[tuple[Surgery, FollowUp, int, int, float]] = []

    n_seq_only = n_astig_only = n_excluded = 0
    for surgery, fu in selected:
        seq_s, ast_s, overall = _case_components(fu)
        if seq_s is not None and ast_s is not None and overall is not None:
            seq_star_vals.append(float(seq_s))
            astig_star_vals.append(float(ast_s))
            overall_vals.append(float(overall))
            complete_pairs.append((surgery, fu, seq_s, ast_s, float(overall)))
        elif seq_s is not None and ast_s is None:
            n_seq_only += 1
            n_excluded += 1
        elif ast_s is not None and seq_s is None:
            n_astig_only += 1
            n_excluded += 1
        else:
            n_excluded += 1

    result.n_complete = len(complete_pairs)
    result.n_seq_only = n_seq_only
    result.n_astig_only = n_astig_only
    result.n_excluded_missing = n_excluded
    result.n_seq = len(seq_star_vals)
    result.n_astig = len(astig_star_vals)
    result.n_overall = len(overall_vals)

    result.avg_seq_stars = _mean(seq_star_vals)
    result.avg_astig_stars = _mean(astig_star_vals)
    result.avg_overall_stars = _mean(overall_vals)
    result.avg_seq_stars_display = round_stars_display(result.avg_seq_stars)
    result.avg_astig_stars_display = round_stars_display(result.avg_astig_stars)
    result.avg_overall_stars_display = round_stars_display(result.avg_overall_stars)

    identity = verify_cohort_identity(
        result.avg_seq_stars,
        result.avg_astig_stars,
        result.avg_overall_stars,
    )
    result.cohort_identity_ok = bool(identity.get("ok"))
    result.cohort_identity_delta = identity.get("delta")

    seqs = [fu.spherical_equivalent for _, fu, *_ in complete_pairs]
    abs_seqs = [abs(s) for s in seqs]
    cyl_mags = [fu.residual_astigmatism for _, fu, *_ in complete_pairs]
    cyl_signed = [fu.cylinder for _, fu, *_ in complete_pairs]
    udvas = [fu.udva_logmar for _, fu, *_ in complete_pairs if fu.udva_logmar is not None]
    cdvas = [fu.cdva_logmar for _, fu, *_ in complete_pairs if fu.cdva_logmar is not None]
    orients = [fu.astigmatism_orientation for _, fu, *_ in complete_pairs]
    orient_counts = Counter(orients)

    result.mean_seq = _mean(seqs)
    result.median_seq = round(median(seqs), 3) if seqs else None
    result.mean_abs_seq = _mean(abs_seqs)
    result.pct_seq_within = {
        "0.25": _pct(sum(1 for a in abs_seqs if a <= 0.25), len(abs_seqs)),
        "0.50": _pct(sum(1 for a in abs_seqs if a <= 0.50), len(abs_seqs)),
        "0.75": _pct(sum(1 for a in abs_seqs if a <= 0.75), len(abs_seqs)),
        "1.00": _pct(sum(1 for a in abs_seqs if a <= 1.00), len(abs_seqs)),
    }
    result.mean_residual_cyl = _mean(cyl_mags)
    result.mean_cylinder_signed = _mean(cyl_signed)
    result.pct_cyl_le_050 = _pct(sum(1 for c in cyl_mags if c <= 0.50), len(cyl_mags))
    result.pct_cyl_le_100 = _pct(sum(1 for c in cyl_mags if c <= 1.00), len(cyl_mags))
    result.seq_star_pct = _star_distribution([int(s) for s in seq_star_vals])
    result.astig_star_pct = _star_distribution([int(s) for s in astig_star_vals])
    # Keep integer-ish distribution for legacy chart + documented continuous bins
    result.overall_star_pct = _star_distribution(overall_vals)
    result.overall_bin_pct = _overall_bin_distribution(overall_vals)
    result.orientation_counts = {
        k: orient_counts.get(k, 0) for k in ("wtr", "atr", "oblique", "none")
    }
    result.orientation_pct = {
        k: _pct(result.orientation_counts[k], len(orients)) for k in result.orientation_counts
    }
    result.mean_udva_logmar = _mean(udvas)
    result.mean_cdva_logmar = _mean(cdvas)

    points = []
    j0s: list[float] = []
    j45s: list[float] = []
    rows: list[dict[str, Any]] = []
    for surgery, fu, seq_s, ast_s, overall in complete_pairs:
        vec = case_vector(fu.cylinder, fu.axis)
        j0s.append(float(vec["j0"] or 0.0))
        j45s.append(float(vec["j45"] or 0.0))
        points.append(
            {
                "x": vec["x"],
                "y": vec["y"],
                "j0": vec["j0"],
                "j45": vec["j45"],
                "cylinder": fu.cylinder,
                "cylinder_magnitude": fu.residual_astigmatism,
                "axis": fu.axis,
                "case_code": surgery.case_code,
                "overall_stars": overall,
                "orientation": fu.astigmatism_orientation,
            }
        )
        rows.append(
            {
                "case_code": surgery.case_code,
                "eye": surgery.eye,
                "surgeon": surgery.surgeon.full_name if surgery.surgeon else "",
                "visit_date": fu.visit_date.isoformat(),
                "sphere": fu.sphere,
                "cylinder": fu.cylinder,
                "axis": fu.axis,
                "seq": fu.spherical_equivalent,
                "cylinder_magnitude": fu.residual_astigmatism,
                "orientation": fu.astigmatism_orientation,
                "j0": vec["j0"],
                "j45": vec["j45"],
                "seq_stars": seq_s,
                "astig_stars": ast_s,
                "overall_stars": overall,
            }
        )

    centroid = compute_centroid(j0s, j45s)
    result.polar_points = points
    result.rows = rows
    result.mean_j0 = centroid.mean_j0
    result.mean_j45 = centroid.mean_j45
    result.mean_vector = {
        "x": centroid.centroid_x,
        "y": centroid.centroid_y,
        "magnitude": centroid.magnitude,
        "mean_j0": centroid.mean_j0,
        "mean_j45": centroid.mean_j45,
        "mean_axis": centroid.mean_axis,
    }
    return result


def list_active_surgeons(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.role == "surgeon", User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )
