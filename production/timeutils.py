"""Shift-based time accounting for production programs.

Work-day model: a work-day starts at 07:00 and ends at 07:00 the next day.
Two 12h shifts: day 07:00–19:00, night 19:00–07:00. Expected production is the
elapsed time (seconds) divided by the one-shot cycle (seconds), rounded.
"""

import datetime

import jdatetime

WORKDAY_START_HOUR = 7


def to_gregorian(jdate, t: datetime.time) -> datetime.datetime:
    """Combine a jdatetime.date and a time into a Gregorian datetime."""
    return jdatetime.datetime(
        jdate.year, jdate.month, jdate.day, t.hour, t.minute, getattr(t, "second", 0)
    ).togregorian()


def workday_bounds(jdate):
    """Gregorian [start, end) for the work-day that begins at 07:00 on jdate."""
    start = jdatetime.datetime(jdate.year, jdate.month, jdate.day, WORKDAY_START_HOUR, 0).togregorian()
    return start, start + datetime.timedelta(hours=24)


def expected_shots(seconds: float, cycle: int) -> int:
    if not cycle or cycle <= 0 or seconds <= 0:
        return 0
    return round(seconds / cycle)


def day_active_seconds(start_dt, stop_dt, jdate) -> int:
    """Seconds the program is active during the work-day of ``jdate``.

    ``start_dt`` is when the program started (راه‌اندازی). ``stop_dt`` is when it
    stopped (اتمام/توقف), or ``None`` if still running (then the full day counts).
    """
    day_start, day_end = workday_bounds(jdate)
    win_start = max(start_dt, day_start) if start_dt else day_start
    win_end = min(stop_dt, day_end) if stop_dt else day_end
    secs = (win_end - win_start).total_seconds()
    return int(secs) if secs > 0 else 0
