"""Shared date-range resolution for dashboards and analytics."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Literal

Period = Literal["all", "month", "custom"]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def resolve_date_range(
    *,
    period: Period,
    month: str | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date | None, date | None, Period, str, str]:
    """Return (from, to, period, month_value, human label)."""
    today = date.today()

    if period == "all":
        return None, None, "all", "", "Totales (todo el historial)"

    if period == "custom":
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        label_from = date_from.isoformat() if date_from else "…"
        label_to = date_to.isoformat() if date_to else "…"
        return (
            date_from,
            date_to,
            "custom",
            "",
            f"Rango personalizado: {label_from} → {label_to}",
        )

    year, mon = today.year, today.month
    if month:
        try:
            y_str, m_str = month.split("-", 1)
            year, mon = int(y_str), int(m_str)
            if not (1 <= mon <= 12):
                raise ValueError
        except ValueError:
            year, mon = today.year, today.month
            month = f"{year:04d}-{mon:02d}"
    else:
        month = f"{year:04d}-{mon:02d}"

    start, end = month_bounds(year, mon)
    month_names = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    return start, end, "month", month, f"{month_names[mon - 1]} {year}"


def current_and_previous_month(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    current = f"{today.year:04d}-{today.month:02d}"
    if today.month == 1:
        previous = f"{today.year - 1:04d}-12"
    else:
        previous = f"{today.year:04d}-{today.month - 1:02d}"
    return current, previous
