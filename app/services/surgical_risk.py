"""Surgical Risk Profile — interpretable regularized logistic MVP.

Educational quality-improvement analytics. Not clinical decision support.
Associations are not causal. Preliminary when sample size is insufficient.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.constants import (
    RISK_CATEGORY_THRESHOLDS,
    RISK_FACTOR_CATALOG,
    RISK_INTERACTION_PAIRS,
    RISK_MIN_CASES,
    RISK_MIN_COMBO_CASES,
    RISK_MIN_EVENTS,
)
from app.models import ComplicationEvent, RiskFactor, Surgery


@dataclass
class ComboStats:
    code: str
    label: str
    n_cases: int
    n_events: int
    observed_rate: float | None
    adjusted_risk: float | None
    ci_low: float | None
    ci_high: float | None
    delta_vs_center: float | None
    sufficient: bool
    status: str


@dataclass
class SurgeonRiskProfile:
    surgeon_id: int | None
    surgeon_name: str
    period_label: str
    model_version: str
    is_preliminary: bool
    n_cases: int
    n_events: int
    observed_rate: float | None
    expected_rate: float | None
    oe_ratio: float | None
    oe_ci: tuple[float, float] | None
    center_avg_rate: float | None
    top_factors: list[ComboStats] = field(default_factory=list)
    combinations: list[ComboStats] = field(default_factory=list)
    better_than_expected: list[str] = field(default_factory=list)
    most_frequent_complication: str | None = None
    most_vulnerable_stage: str | None = None
    recommendations: list[str] = field(default_factory=list)
    trend: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)


def _category(risk: float) -> str:
    low, mid = RISK_CATEGORY_THRESHOLDS
    if risk < low:
        return "bajo"
    if risk < mid:
        return "intermedio"
    return "elevado"


def _cases_query(
    db: Session,
    *,
    center_id: int | None,
    institution_code: str | None,
    surgeon_id: int | None,
    date_from: date | None,
    date_to: date | None,
):
    q = (
        db.query(Surgery)
        .options(joinedload(Surgery.risk_factors), joinedload(Surgery.complication))
        .order_by(Surgery.surgery_date.desc())
    )
    if center_id is not None:
        q = q.filter(Surgery.center_id == center_id)
    elif institution_code:
        q = q.filter(Surgery.institution_id == institution_code)
    if surgeon_id is not None:
        q = q.filter(Surgery.surgeon_id == surgeon_id)
    if date_from:
        q = q.filter(Surgery.surgery_date >= date_from)
    if date_to:
        q = q.filter(Surgery.surgery_date <= date_to)
    return q.all()


def _has_event(s: Surgery) -> bool:
    return bool(s.complication and s.complication.occurred)


def _factor_set(s: Surgery) -> set[str]:
    return {rf.code for rf in (s.risk_factors or [])}


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)


def _fit_ridge_logit(
    rows: list[tuple[list[float], int]],
    l2: float = 1.0,
    iters: int = 80,
) -> tuple[list[float], float]:
    """Simple L2-regularized logistic regression (no sklearn dependency)."""
    if not rows:
        return [], 0.0
    n_feat = len(rows[0][0])
    w = [0.0] * n_feat
    b = 0.0
    n = len(rows)
    lr = 0.2
    for _ in range(iters):
        grad_w = [l2 * wi for wi in w]
        grad_b = 0.0
        for x, y in rows:
            z = b + sum(wi * xi for wi, xi in zip(w, x))
            p = _sigmoid(z)
            err = p - y
            for j in range(n_feat):
                grad_w[j] += err * x[j]
            grad_b += err
        for j in range(n_feat):
            w[j] -= lr * grad_w[j] / max(n, 1)
        b -= lr * grad_b / max(n, 1)
    return w, b


def _interaction_code(a: str, b: str) -> str:
    return f"{a}*{b}"


def build_surgical_risk_profile(
    db: Session,
    *,
    center_id: int | None = None,
    institution_code: str | None = None,
    surgeon_id: int | None = None,
    surgeon_name: str = "Cirujano",
    date_from: date | None = None,
    date_to: date | None = None,
    period_label: str = "Totales",
) -> SurgeonRiskProfile:
    model_version = "srp-logit-l2-v1"
    cases = _cases_query(
        db,
        center_id=center_id,
        institution_code=institution_code,
        surgeon_id=surgeon_id,
        date_from=date_from,
        date_to=date_to,
    )
    n = len(cases)
    events = sum(1 for s in cases if _has_event(s))
    observed = (events / n) if n else None

    # Center baseline (same center, all surgeons)
    center_cases = _cases_query(
        db,
        center_id=center_id,
        institution_code=institution_code,
        surgeon_id=None,
        date_from=date_from,
        date_to=date_to,
    )
    cn, ce = len(center_cases), sum(1 for s in center_cases if _has_event(s))
    center_avg = (ce / cn) if cn else None

    preliminary = n < RISK_MIN_CASES or events < RISK_MIN_EVENTS
    notes = [
        "Herramienta educativa de mejora de calidad. No sustituye el criterio clínico.",
        "Las asociaciones no implican causalidad.",
    ]
    if preliminary:
        notes.append(
            "Análisis preliminar: volumen insuficiente para un modelo predictivo estable. "
            "Se muestran estadísticas descriptivas."
        )

    # Feature matrix: main effects + selected interactions
    feature_codes = [c for c in RISK_FACTOR_CATALOG if c != "other"]
    inter_codes = [_interaction_code(a, b) for a, b in RISK_INTERACTION_PAIRS]
    all_codes = feature_codes + inter_codes

    rows: list[tuple[list[float], int]] = []
    for s in cases:
        fs = _factor_set(s)
        x = [1.0 if code in fs else 0.0 for code in feature_codes]
        for a, b in RISK_INTERACTION_PAIRS:
            x.append(1.0 if (a in fs and b in fs) else 0.0)
        rows.append((x, 1 if _has_event(s) else 0))

    weights, bias = _fit_ridge_logit(rows) if not preliminary and rows else ([], 0.0)

    def predict(fs: set[str]) -> float:
        if preliminary or not weights:
            # Fallback: center average shrunk toward global observed
            base = center_avg if center_avg is not None else (observed or 0.03)
            return base
        x = [1.0 if code in fs else 0.0 for code in feature_codes]
        for a, b in RISK_INTERACTION_PAIRS:
            x.append(1.0 if (a in fs and b in fs) else 0.0)
        z = bias + sum(w * xi for w, xi in zip(weights, x))
        return _sigmoid(z)

    expected_rates = [predict(_factor_set(s)) for s in cases]
    expected = sum(expected_rates) / n if n else None
    oe = (observed / expected) if (observed is not None and expected and expected > 0) else None
    oe_ci = None
    if oe is not None and n and expected:
        # Approximate CI via Wilson on observed, divided by expected
        ci = _wilson_ci(events, n)
        if ci:
            oe_ci = (ci[0] / expected, ci[1] / expected)

    def combo_stats(code: str, label: str, predicate) -> ComboStats:
        subset = [s for s in cases if predicate(s)]
        sn, se = len(subset), sum(1 for s in subset if _has_event(s))
        sufficient = sn >= RISK_MIN_COMBO_CASES and se >= 1
        obs = (se / sn) if sn else None
        adj = None
        if subset and not preliminary:
            adj = sum(predict(_factor_set(s)) for s in subset) / sn
        elif subset:
            adj = obs
        ci = _wilson_ci(se, sn) if sn else None
        delta = None
        if obs is not None and center_avg is not None:
            delta = obs - center_avg
        return ComboStats(
            code=code,
            label=label,
            n_cases=sn,
            n_events=se,
            observed_rate=obs,
            adjusted_risk=adj,
            ci_low=ci[0] if ci else None,
            ci_high=ci[1] if ci else None,
            delta_vs_center=delta,
            sufficient=sufficient,
            status="ok" if sufficient else "insufficient",
        )

    top_factors = []
    for code in feature_codes:
        st = combo_stats(code, RISK_FACTOR_CATALOG[code], lambda s, c=code: c in _factor_set(s))
        top_factors.append(st)
    top_factors.sort(key=lambda x: (-(x.observed_rate or 0), -x.n_cases))

    combinations = []
    for a, b in RISK_INTERACTION_PAIRS:
        label = f"{RISK_FACTOR_CATALOG.get(a, a)} × {RISK_FACTOR_CATALOG.get(b, b)}"
        combinations.append(
            combo_stats(
                _interaction_code(a, b),
                label,
                lambda s, a=a, b=b: a in _factor_set(s) and b in _factor_set(s),
            )
        )

    better = [
        f.label
        for f in top_factors
        if f.sufficient
        and f.observed_rate is not None
        and f.adjusted_risk is not None
        and f.observed_rate < f.adjusted_risk
    ][:5]

    # Complication type / stage among events
    type_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    for s in cases:
        if not _has_event(s) or not s.complication:
            continue
        ct = s.complication.complication_type or "other"
        type_counts[ct] = type_counts.get(ct, 0) + 1
        st = s.complication.surgical_stage or "other"
        stage_counts[st] = stage_counts.get(st, 0) + 1
    most_type = max(type_counts, key=type_counts.get) if type_counts else None
    most_stage = max(stage_counts, key=stage_counts.get) if stage_counts else None

    recommendations: list[str] = []
    for c in combinations:
        if not c.sufficient or c.observed_rate is None or center_avg is None:
            continue
        if c.observed_rate > (center_avg + 0.02) and c.n_cases >= RISK_MIN_COMBO_CASES:
            recommendations.append(
                f"En los casos con {c.label} se ha observado una frecuencia de complicaciones "
                f"superior a tu promedio (n={c.n_cases}, eventos={c.n_events}). "
                "Considera revisar la planeación del caso y solicitar supervisión según el "
                "protocolo del centro. Esto no constituye una indicación médica."
            )

    # Simple temporal trend by month
    by_month: dict[str, list[int]] = {}
    for s in cases:
        key = s.surgery_date.strftime("%Y-%m")
        bucket = by_month.setdefault(key, [0, 0])
        bucket[0] += 1
        bucket[1] += 1 if _has_event(s) else 0
    labels = sorted(by_month.keys())
    trend = {
        "labels": labels,
        "cases": [by_month[k][0] for k in labels],
        "events": [by_month[k][1] for k in labels],
        "rates": [
            (by_month[k][1] / by_month[k][0]) if by_month[k][0] else None for k in labels
        ],
    }

    return SurgeonRiskProfile(
        surgeon_id=surgeon_id,
        surgeon_name=surgeon_name,
        period_label=period_label,
        model_version=model_version,
        is_preliminary=preliminary,
        n_cases=n,
        n_events=events,
        observed_rate=observed,
        expected_rate=expected,
        oe_ratio=oe,
        oe_ci=oe_ci,
        center_avg_rate=center_avg,
        top_factors=top_factors[:12],
        combinations=combinations,
        better_than_expected=better,
        most_frequent_complication=most_type,
        most_vulnerable_stage=most_stage,
        recommendations=recommendations[:5],
        trend=trend,
        notes=notes,
    )


def case_baseline_risk(
    db: Session,
    surgery: Surgery,
    *,
    center_id: int | None = None,
    institution_code: str | None = None,
) -> dict[str, Any]:
    """Per-case estimated risk vs center average (descriptive / model-based)."""
    profile = build_surgical_risk_profile(
        db,
        center_id=center_id or surgery.center_id,
        institution_code=institution_code or surgery.institution_id,
        surgeon_id=None,
        period_label="Centro",
    )
    fs = _factor_set(surgery)
    # Reuse center model expected for this factor set via a one-row predict
    # Approximate with mean of similar cases if preliminary
    similar = [
        s
        for s in _cases_query(
            db,
            center_id=center_id or surgery.center_id,
            institution_code=institution_code or surgery.institution_id,
            surgeon_id=None,
            date_from=None,
            date_to=None,
        )
        if _factor_set(s) == fs
    ]
    if similar:
        est = sum(1 for s in similar if _has_event(s)) / len(similar)
    else:
        est = profile.center_avg_rate or 0.03
    return {
        "estimated_risk": est,
        "center_avg": profile.center_avg_rate,
        "category": _category(est),
        "factors": [RISK_FACTOR_CATALOG.get(c, c) for c in sorted(fs)],
        "preliminary": profile.is_preliminary,
        "model_version": profile.model_version,
    }
