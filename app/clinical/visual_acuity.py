"""Visual acuity helpers (Snellen <-> logMAR). No PII."""

from __future__ import annotations

import re
from math import log10

# Common Snellen denominators (feet) and non-numeric codes.
_SNELLEN_RE = re.compile(r"^\s*(?:20/)?(\d+)\s*$", re.IGNORECASE)

NON_NUMERIC_LOGMAR: dict[str, float] = {
    "CF": 1.6,  # count fingers approximate
    "HM": 2.0,  # hand motion
    "LP": 2.3,  # light perception
    "NLP": 3.0,
}


def snellen_to_logmar(snellen: str | None) -> float | None:
    """Convert Snellen (e.g. '20/40' or '40') to logMAR."""
    if snellen is None:
        return None
    raw = snellen.strip().upper()
    if not raw:
        return None
    if raw in NON_NUMERIC_LOGMAR:
        return NON_NUMERIC_LOGMAR[raw]
    match = _SNELLEN_RE.match(raw.replace("20/", ""))
    if not match:
        # Try full 20/xx
        full = re.match(r"^\s*20/(\d+)\s*$", raw, re.IGNORECASE)
        if not full:
            return None
        denom = int(full.group(1))
    else:
        denom = int(match.group(1))
    if denom <= 0:
        return None
    decimal = 20 / denom
    return round(-log10(decimal), 3)


def logmar_to_snellen_approx(logmar: float | None) -> str | None:
    """Approximate Snellen string from logMAR for display."""
    if logmar is None:
        return None
    for code, value in NON_NUMERIC_LOGMAR.items():
        if abs(logmar - value) < 1e-6:
            return code
    decimal = 10 ** (-logmar)
    denom = max(1, int(round(20 / decimal)))
    return f"20/{denom}"


def normalize_snellen(snellen: str | None) -> str | None:
    if snellen is None:
        return None
    raw = snellen.strip().upper()
    if not raw:
        return None
    if raw in NON_NUMERIC_LOGMAR:
        return raw
    if re.match(r"^\d+$", raw):
        return f"20/{raw}"
    if re.match(r"^20/\d+$", raw, re.IGNORECASE):
        return raw.upper()
    return raw
