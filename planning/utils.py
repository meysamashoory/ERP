"""Helpers for weekly-planning date logic."""

from __future__ import annotations

import jdatetime


def format_jdate(value) -> str:
    """Display Jalali dates as ``1405/02/25`` (never day-first or dash-separated)."""
    if value in (None, ""):
        return ""
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y/%m/%d")
        except (ValueError, TypeError, OverflowError):
            pass
    text = str(value).strip()
    if not text:
        return ""
    # Normalize common stored/display variants: 1405-02-25, 25-02-1405, 1405/02/25
    for sep in ("/", "-", "."):
        if sep in text:
            parts = text.split(sep)
            if len(parts) == 3:
                a, b, c = parts
                if len(a) == 4:
                    return f"{a}/{b.zfill(2)}/{c.zfill(2)}"
                if len(c) == 4:
                    return f"{c}/{b.zfill(2)}/{a.zfill(2)}"
            break
    return text


def parse_jdate_string(raw: str) -> jdatetime.date:
    """Parse ``YYYY/MM/DD`` or ``YYYY-MM-DD`` into a Jalali date."""
    normalized = str(raw or "").strip().replace("-", "/")
    y, m, d = (int(p) for p in normalized.split("/"))
    return jdatetime.date(y, m, d)


def start_of_week(jdate: jdatetime.date) -> jdatetime.date:
    """Return the Saturday that starts the Jalali week containing ``jdate``.

    jdatetime uses Saturday == 0 for :meth:`weekday`.
    """
    return jdate - jdatetime.timedelta(days=jdate.weekday())


def mold_change_date_candidates(plan_date: jdatetime.date, target_weekday: int) -> list[jdatetime.date]:
    """Candidate mold-change dates for a target weekday.

    Per the specification, the horizon runs from the planning date through the
    end of the *following* week (that week's Friday). Only dates on/after the
    planning date are returned, so a weekday whose only occurrence already
    passed yields fewer (or zero) options.
    """
    if plan_date is None:
        return []
    horizon = start_of_week(plan_date) + jdatetime.timedelta(days=13)  # next week's Friday
    candidates = []
    current = plan_date
    while current <= horizon:
        if current.weekday() == target_weekday:
            candidates.append(current)
        current += jdatetime.timedelta(days=1)
    return candidates
