"""Jalali calendar helpers for Excel transfer and history ``DateField``s.

Convention for plain ``models.DateField`` (e.g. ``ProductionHistoryRecord``):
store Jalali year/month/day as ``datetime.date(jy, jm, jd)`` so display helpers
like ``format_jdate`` / ``strftime`` show شمسی (e.g. ``1405/06/01``).

True Gregorian values (year ≥ 1600) and Excel serials are converted to this
Jalali-encoded form on import. ``jDateField`` values (planning/production)
remain real ``jdatetime.date`` objects.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import jdatetime

_EXCEL_EPOCH = date(1899, 12, 30)
_JALALI_YEAR_MIN = 1200
_JALALI_YEAR_MAX = 1500
_GREGORIAN_YEAR_MIN = 1600
_GREGORIAN_YEAR_MAX = 2100


def is_jalali_year(year: int) -> bool:
    return _JALALI_YEAR_MIN <= int(year) <= _JALALI_YEAR_MAX


def is_gregorian_year(year: int) -> bool:
    return _GREGORIAN_YEAR_MIN <= int(year) <= _GREGORIAN_YEAR_MAX


def jalali_to_storage(j: jdatetime.date) -> date:
    """Encode a Jalali date into a plain ``date`` for history ``DateField``s."""
    return date(int(j.year), int(j.month), int(j.day))


def storage_to_jalali(value: Any) -> jdatetime.date | None:
    """Convert stored history/planning date values to ``jdatetime.date``.

    - Already ``jdatetime.date`` → as-is
    - ``date`` with Jalali year (1200–1500) → ``jdatetime.date(y, m, d)``
    - ``date`` with Gregorian year (≥1600) → ``fromgregorian``
    """
    if value is None or value == "":
        return None
    if hasattr(value, "togregorian") and hasattr(value, "year"):
        # jdatetime.date (and compatible)
        if type(value).__module__.startswith("jdatetime"):
            return value
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        y, m, d = value.year, value.month, value.day
        if is_jalali_year(y):
            try:
                return jdatetime.date(y, m, d)
            except ValueError:
                return None
        if is_gregorian_year(y):
            try:
                return jdatetime.date.fromgregorian(date=value)
            except (ValueError, OverflowError):
                return None
    return None


def coerce_to_jalali_storage(value: Any) -> date | None:
    """Normalize any date-like value to Jalali-encoded ``date`` for history fields."""
    j = storage_to_jalali(value)
    if j is None:
        return None
    return jalali_to_storage(j)


def gregorian_to_jalali_storage(g: date) -> date:
    return jalali_to_storage(jdatetime.date.fromgregorian(date=g))


def excel_serial_to_gregorian(serial: float | int) -> date | None:
    try:
        n = int(float(serial))
    except (TypeError, ValueError):
        return None
    if not (1 <= n <= 100000):
        return None
    try:
        return _EXCEL_EPOCH + timedelta(days=n)
    except OverflowError:
        return None


def format_jalali_slash(value: Any) -> str:
    """``1405/06/01`` display form."""
    j = storage_to_jalali(value)
    if j is None:
        return ""
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
