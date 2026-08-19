"""Structured 14-digit program UID (شناسه برنامه).

Default law (قابل بازتعریف از «مدیریت داده‌ها» → قانون شناسه برنامه):

  YY PPP U MM DDD T RR   (۱۴ رقم)

  YY  = سال برنامه‌ریزی − سال مبدأ (۱۳۷۰) + ۱   → ۱۴۰۵→۳۶ ، ۱۴۰۹→۴۰
  PPP = شماره برنامه (۳ رقم)
  U   = شماره واحد تولیدی
  MM  = شماره دستگاه تزریق (۲ رقم، با صفر پیشوند)
  DDD = (روز اکسل تاریخ برنامه − اول سال) + (روز اکسل تعویض قالب − اول سال)
  T   = ترتیب نوع تولید روی همان ردیف (۱، ۲، …)
  RR  = شماره ردیف/قالب در برنامه (۱…N)
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import jdatetime

# Excel serial for civil dates after 1900-02-28 matches (d - 1899-12-30).days
_EXCEL_EPOCH = date(1899, 12, 30)

DEFAULT_SEGMENTS = [
    {
        "key": "year",
        "digits": 2,
        "rule": "plan_year - base_year + 1",
        "label": "کد سال",
    },
    {
        "key": "program",
        "digits": 3,
        "rule": "program_number",
        "label": "شماره برنامه",
    },
    {
        "key": "unit",
        "digits": 1,
        "rule": "unit_number",
        "label": "واحد",
    },
    {
        "key": "machine",
        "digits": 2,
        "rule": "machine_number",
        "label": "دستگاه",
    },
    {
        "key": "date_sum",
        "digits": 3,
        "rule": "excel_offset(plan_date) + excel_offset(mold_change_date)",
        "label": "جمع روز برنامه و تعویض",
    },
    {
        "key": "production_type",
        "digits": 1,
        "rule": "1-based production type index on the item",
        "label": "نوع تولید",
    },
    {
        "key": "mold_row",
        "digits": 2,
        "rule": "1-based mold/row ordinal in the plan",
        "label": "ردیف قالب",
    },
]


def excel_serial(value) -> int:
    """Return Excel day serial for a jalali or Gregorian date."""
    if value is None:
        raise ValueError("date is required")
    if hasattr(value, "togregorian"):
        g = value.togregorian()
        d = date(g.year, g.month, g.day)
    elif isinstance(value, date):
        d = value
    else:
        d = date(value.year, value.month, value.day)
    return (d - _EXCEL_EPOCH).days


def jalali_year_start(year: int) -> jdatetime.date:
    return jdatetime.date(int(year), 1, 1)


def year_code(plan_year: int, base_year: int = 1370) -> int:
    """۱۴۰۵→۳۶ with base_year=۱۳۷۰ (year - base + 1)."""
    return int(plan_year) - int(base_year) + 1


def excel_year_day_offset(jdate, year: int | None = None) -> int:
    """Days from Nowruz of that Jalali year (Excel serial difference)."""
    y = int(year if year is not None else jdate.year)
    return excel_serial(jdate) - excel_serial(jalali_year_start(y))


def parse_program_number(program_number: str | int) -> int:
    """Extract integer program number from values like '159' or 'BP-159'."""
    if isinstance(program_number, int):
        return program_number
    digits = re.sub(r"\D", "", str(program_number or ""))
    return int(digits) if digits else 0


def parse_machine_number(machine_number: str | int) -> int:
    digits = re.sub(r"\D", "", str(machine_number or ""))
    return int(digits) if digits else 0


def _pad(value: int, digits: int) -> str:
    mod = 10 ** digits
    return f"{int(value) % mod:0{digits}d}"


def load_scheme() -> Any:
    """Active UID scheme from مدیریت داده‌ها (or in-memory defaults)."""
    try:
        from catalog.models import ProgramUidScheme
        return ProgramUidScheme.load()
    except Exception:
        return None


def scheme_params(scheme=None) -> dict:
    scheme = scheme if scheme is not None else load_scheme()
    if scheme is None:
        return {
            "base_year": 1370,
            "year_digits": 2,
            "program_digits": 3,
            "unit_digits": 1,
            "machine_digits": 2,
            "date_sum_digits": 3,
            "production_type_digits": 1,
            "mold_row_digits": 2,
            "segments": list(DEFAULT_SEGMENTS),
        }
    return {
        "base_year": int(getattr(scheme, "base_year", 1370) or 1370),
        "year_digits": int(getattr(scheme, "year_digits", 2) or 2),
        "program_digits": int(getattr(scheme, "program_digits", 3) or 3),
        "unit_digits": int(getattr(scheme, "unit_digits", 1) or 1),
        "machine_digits": int(getattr(scheme, "machine_digits", 2) or 2),
        "date_sum_digits": int(getattr(scheme, "date_sum_digits", 3) or 3),
        "production_type_digits": int(getattr(scheme, "production_type_digits", 1) or 1),
        "mold_row_digits": int(getattr(scheme, "mold_row_digits", 2) or 2),
        "segments": getattr(scheme, "segments_json", None) or list(DEFAULT_SEGMENTS),
    }


def build_program_uid(
    *,
    plan_date,
    program_number: str | int,
    unit_number: int,
    machine_number: str | int,
    mold_change_date,
    production_type_index: int = 1,
    mold_row: int = 1,
    scheme=None,
) -> str:
    """Build the structured UID string according to the active scheme."""
    p = scheme_params(scheme)
    plan_year = int(plan_date.year)
    yy = year_code(plan_year, p["base_year"])
    date_sum = excel_year_day_offset(plan_date, plan_year) + excel_year_day_offset(
        mold_change_date, plan_year
    )
    parts = [
        _pad(yy, p["year_digits"]),
        _pad(parse_program_number(program_number), p["program_digits"]),
        _pad(unit_number, p["unit_digits"]),
        _pad(parse_machine_number(machine_number), p["machine_digits"]),
        _pad(date_sum, p["date_sum_digits"]),
        _pad(production_type_index, p["production_type_digits"]),
        _pad(mold_row, p["mold_row_digits"]),
    ]
    return "".join(parts)


def mold_row_for_item(item) -> int:
    """1-based ordinal of this item among molds in its plan."""
    plan = item.plan
    ordered = list(
        plan.items.order_by("mold_change_date", "id").values_list("id", flat=True)
    )
    try:
        return ordered.index(item.id) + 1
    except ValueError:
        return len(ordered) + 1


def production_type_index_for_line(line) -> int:
    """1-based index of this production line on its item."""
    ids = list(line.item.lines.order_by("id").values_list("id", flat=True))
    try:
        return ids.index(line.id) + 1
    except ValueError:
        return line.item.lines.count() + 1


def uid_for_item(item, production_type_index: int = 1, scheme=None) -> str:
    """Compute UID for a plan item at a given production-type index."""
    unit_number = item.unit.number if item.unit_id else (
        item.machine.unit.number if item.machine_id and item.machine.unit_id else 0
    )
    machine_number = item.machine.number if item.machine_id else 0
    return build_program_uid(
        plan_date=item.plan.date,
        program_number=item.plan.program_number,
        unit_number=unit_number,
        machine_number=machine_number,
        mold_change_date=item.mold_change_date,
        production_type_index=production_type_index,
        mold_row=mold_row_for_item(item),
        scheme=scheme,
    )


def find_uid_owner(uid: str, *, exclude_item_id=None, exclude_line_id=None):
    """Return (kind, obj) owning this uid, or None."""
    from planning.models import WeeklyPlanItem, WeeklyPlanLine

    qs = WeeklyPlanItem.objects.filter(uid=uid)
    if exclude_item_id:
        qs = qs.exclude(pk=exclude_item_id)
    item = qs.select_related("plan", "product", "machine").first()
    if item:
        return ("item", item)
    lqs = WeeklyPlanLine.objects.filter(uid=uid)
    if exclude_line_id:
        lqs = lqs.exclude(pk=exclude_line_id)
    line = lqs.select_related("item__plan", "item__product", "item__machine").first()
    if line:
        return ("line", line)
    return None


def describe_uid_owner(owner) -> str:
    kind, obj = owner
    if kind == "item":
        return (
            f"کالای «{obj.product.name}» در برنامه {obj.plan.program_number} "
            f"(دستگاه {obj.machine.number})"
        )
    item = obj.item
    return (
        f"ردیف تولید «{obj.production_type}» از کالای «{item.product.name}» "
        f"در برنامه {item.plan.program_number}"
    )


def assign_uids_for_item(item, scheme=None) -> tuple[str, list[dict]]:
    """Assign UIDs on lines and item. Returns (primary_uid, collisions).

    On duplicate full UID: does not overwrite with the colliding value, registers a
    serious SystemAlarm with a suggested fix, and records the collision.
    """
    from catalog.alarms import register_alarm, uid_collision_suggestion
    from catalog.models import SystemAlarm

    scheme = scheme if scheme is not None else load_scheme()
    lines = list(item.lines.order_by("id"))
    collisions: list[dict] = []
    primary = ""

    def _handle_collision(uid: str, *, line=None, type_index: int) -> None:
        owner = find_uid_owner(
            uid,
            exclude_item_id=item.pk,
            exclude_line_id=getattr(line, "pk", None),
        )
        owner_label = describe_uid_owner(owner) if owner else "رکورد دیگر"
        suggestion = uid_collision_suggestion(
            uid=uid,
            owner_label=owner_label,
            program_number=str(item.plan.program_number),
        )
        register_alarm(
            title="تکرار شناسه برنامه",
            message=(
                f"شناسه {uid} برای کالای «{item.product.name}» "
                f"(برنامه {item.plan.program_number}، نوع تولید {type_index}) "
                f"تکراری است و با {owner_label} تداخل دارد."
            ),
            suggestion=suggestion,
            severity=SystemAlarm.Severity.SERIOUS,
            kind=SystemAlarm.Kind.UID_DUPLICATE,
            details={
                "uid": uid,
                "plan_id": item.plan_id,
                "plan_number": str(item.plan.program_number),
                "item_id": item.pk,
                "product": item.product.name if item.product_id else "",
                "production_type_index": type_index,
                "owner": owner_label,
            },
        )
        collisions.append({
            "uid": uid,
            "item_id": item.pk,
            "type_index": type_index,
            "owner": owner_label,
            "suggestion": suggestion,
        })

    if lines:
        for idx, line in enumerate(lines, start=1):
            uid = uid_for_item(item, production_type_index=idx, scheme=scheme)
            owner = find_uid_owner(uid, exclude_item_id=item.pk, exclude_line_id=line.pk)
            # Also collide if another line of a different item has it, or item.uid of other
            if owner:
                _handle_collision(uid, line=line, type_index=idx)
            else:
                if line.uid != uid:
                    line.uid = uid
                    line.save(update_fields=["uid"])
            if idx == 1:
                primary = uid if not owner else (line.uid or item.uid or uid)
    else:
        uid = uid_for_item(item, production_type_index=1, scheme=scheme)
        owner = find_uid_owner(uid, exclude_item_id=item.pk)
        if owner:
            _handle_collision(uid, type_index=1)
            primary = item.uid or uid
        else:
            primary = uid

    if primary and not any(c.get("type_index") == 1 for c in collisions):
        if item.uid != primary:
            clash = type(item).objects.filter(uid=primary).exclude(pk=item.pk).exists()
            if clash:
                temp = f"T{item.pk:013d}"[:16]
                type(item).objects.filter(pk=item.pk).update(uid=temp)
                item.uid = temp
            type(item).objects.filter(pk=item.pk).update(uid=primary)
            item.uid = primary
    return primary, collisions


def refresh_plan_uids(plan, scheme=None) -> list[dict]:
    """Recompute UIDs for every item in a plan. Returns list of collision dicts."""
    scheme = scheme if scheme is not None else load_scheme()
    all_collisions: list[dict] = []
    for item in plan.items.select_related(
        "unit", "machine__unit", "plan", "product"
    ).order_by("mold_change_date", "id"):
        _primary, collisions = assign_uids_for_item(item, scheme=scheme)
        all_collisions.extend(collisions)
    return all_collisions
