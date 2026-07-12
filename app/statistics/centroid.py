"""Centroid / mean astigmatic vector from J0/J45 samples. No PII."""

from __future__ import annotations

from dataclasses import dataclass

from app.clinical.vector_analysis import (
    axis_from_j0_j45,
    vector_magnitude_from_j,
)


@dataclass(frozen=True)
class VectorCentroid:
    mean_j0: float
    mean_j45: float
    centroid_x: float  # 2 * mean_j0
    centroid_y: float  # 2 * mean_j45
    magnitude: float  # |C| of mean vector
    mean_axis: float | None  # from J0/J45, not arithmetic mean of axes
    n: int


def compute_centroid(j0_values: list[float], j45_values: list[float]) -> VectorCentroid:
    if not j0_values or not j45_values or len(j0_values) != len(j45_values):
        return VectorCentroid(
            mean_j0=0.0,
            mean_j45=0.0,
            centroid_x=0.0,
            centroid_y=0.0,
            magnitude=0.0,
            mean_axis=None,
            n=0,
        )
    n = len(j0_values)
    mj0 = sum(j0_values) / n
    mj45 = sum(j45_values) / n
    return VectorCentroid(
        mean_j0=round(mj0, 6),
        mean_j45=round(mj45, 6),
        centroid_x=round(2.0 * mj0, 4),
        centroid_y=round(2.0 * mj45, 4),
        magnitude=vector_magnitude_from_j(mj0, mj45),
        mean_axis=axis_from_j0_j45(mj0, mj45),
        n=n,
    )
