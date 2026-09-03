"""Mold-change aggregates for the planning glass strip and day×unit matrix."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from catalog.models import PlanningDisplaySettings
from planning.models import PERSIAN_WEEKDAYS, WeeklyPlan
from planning.utils import format_jdate


def _settings() -> PlanningDisplaySettings:
    return PlanningDisplaySettings.load()


def mold_change_stats(plan: WeeklyPlan) -> dict[str, Any]:
    """Build glass rows and matrix data from plan items (each item = one mold change)."""
    settings = _settings()
    unit_numbers = settings.unit_numbers()
    items = list(
        plan.items.select_related("unit", "subgroup__group").all()
    )

    # unit_number -> {total, groups: {group_name: count}}
    by_unit: dict[int, dict[str, Any]] = {
        n: {"unit": n, "total": 0, "groups": defaultdict(int)} for n in unit_numbers
    }
    # (weekday_int, date_str) -> unit_number -> count
    matrix_counts: dict[tuple[int, str], dict[int, int]] = defaultdict(
        lambda: {n: 0 for n in unit_numbers}
    )

    for item in items:
        unit_no = item.unit.number
        if unit_no not in by_unit:
            by_unit[unit_no] = {"unit": unit_no, "total": 0, "groups": defaultdict(int)}
        by_unit[unit_no]["total"] += 1
        group_name = item.subgroup.group.name if item.subgroup_id else "—"
        by_unit[unit_no]["groups"][group_name] += 1

        date_str = format_jdate(item.mold_change_date)
        key = (int(item.mold_change_weekday), date_str)
        if unit_no not in matrix_counts[key]:
            matrix_counts[key][unit_no] = 0
        if unit_no in unit_numbers or unit_no in matrix_counts[key]:
            matrix_counts[key][unit_no] = matrix_counts[key].get(unit_no, 0) + 1

    # Ordered glass cards: only configured units, then any extras that appear
    ordered_units = list(unit_numbers)
    for n in sorted(by_unit.keys()):
        if n not in ordered_units and by_unit[n]["total"]:
            ordered_units.append(n)

    glass_rows = []
    for n in ordered_units:
        row = by_unit.get(n)
        if not row:
            continue
        groups = [
            {"name": name, "count": count}
            for name, count in sorted(row["groups"].items(), key=lambda x: (-x[1], x[0]))
        ]
        glass_rows.append(
            {
                "unit": n,
                "total": row["total"],
                "groups": groups if settings.show_group_breakdown else [],
                "label": f"واحد {n}",
                "value": f"{row['total']} قالب",
            }
        )

    matrix_rows = []
    for (weekday, date_str), counts in sorted(
        matrix_counts.items(), key=lambda x: (x[0][1], x[0][0])
    ):
        try:
            day_name = PERSIAN_WEEKDAYS[weekday]
        except IndexError:
            day_name = str(weekday)
        matrix_rows.append(
            {
                "weekday": day_name,
                "date": date_str,
                "counts": {n: counts.get(n, 0) for n in unit_numbers},
                "counts_list": [counts.get(n, 0) for n in unit_numbers],
            }
        )

    coef = float(settings.height_coefficient or 1)
    if coef <= 0:
        coef = 1.0

    return {
        "glass_rows": glass_rows,
        "matrix_rows": matrix_rows,
        "matrix_units": unit_numbers,
        "height_coefficient": coef,
        "width_coefficient": coef,
        "show_group_breakdown": settings.show_group_breakdown,
    }
