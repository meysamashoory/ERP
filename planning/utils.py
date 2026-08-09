"""Helpers for weekly-planning date logic."""

import jdatetime


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
