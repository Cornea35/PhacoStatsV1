"""Fisher's exact test for 2x2 contingency tables (pure Python)."""

from __future__ import annotations

from math import comb


def _hypergeometric_pmf(a: int, row1: int, col1: int, n: int) -> float:
    """P(A=a) under hypergeometric model for a fixed-margin 2x2 table."""
    # Guard impossible tables.
    lo = max(0, row1 + col1 - n)
    hi = min(row1, col1)
    if a < lo or a > hi:
        return 0.0
    return comb(col1, a) * comb(n - col1, row1 - a) / comb(n, row1)


def fisher_exact_pvalue(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact p-value for a 2x2 table.

    Uses the sum of probabilities of all tables with probability less than or
    equal to the observed table (standard two-sided Fisher definition).
    """
    if min(a, b, c, d) < 0:
        raise ValueError("table counts must be non-negative")

    row1 = a + b
    col1 = a + c
    n = a + b + c + d
    if n == 0 or row1 == 0 or (b + d) == 0 or col1 == 0 or (a + c == n):
        return 1.0

    observed = _hypergeometric_pmf(a, row1, col1, n)
    lo = max(0, row1 + col1 - n)
    hi = min(row1, col1)

    total = 0.0
    # Numerical tolerance for floating comparisons of pmf values.
    eps = 1e-12
    for x in range(lo, hi + 1):
        p = _hypergeometric_pmf(x, row1, col1, n)
        if p <= observed + eps:
            total += p
    # Clamp floating error.
    return min(1.0, max(0.0, total))


def fisher_exact_one_sided(a: int, b: int, c: int, d: int, *, alternative: str = "greater") -> float:
    """One-sided Fisher p-value (greater or less)."""
    if alternative not in {"greater", "less"}:
        raise ValueError("alternative must be 'greater' or 'less'")
    row1 = a + b
    col1 = a + c
    n = a + b + c + d
    if n == 0:
        return 1.0
    lo = max(0, row1 + col1 - n)
    hi = min(row1, col1)
    if alternative == "greater":
        return min(1.0, sum(_hypergeometric_pmf(x, row1, col1, n) for x in range(a, hi + 1)))
    return min(1.0, sum(_hypergeometric_pmf(x, row1, col1, n) for x in range(lo, a + 1)))
