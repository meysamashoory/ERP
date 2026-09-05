"""Report source catalog aligned with the main-menu pages and their table headers.

Excel uploads and saved reports are never exposed as sources.
"""

from __future__ import annotations

from catalog.models import FlexibleDataset, SystemNamingKey
from catalog.flexible_data import DEFAULT_PRODUCT_TABS, list_tab_levels

SOURCE_WEEKLY = "weekly_planning"
SOURCE_SYSTEMIC_PREFIX = "systemic__"

SYSTEMIC_TABS: list[dict[str, str]] = [
    {"id": "balance", "label": "تراز تقاضا و تأمین"},
    {"id": "materials", "label": "کسری مواد"},
    {"id": "capacity", "label": "بار دستگاه و قالب"},
    {"id": "variance", "label": "انحراف برنامه و واقعی"},
    {"id": "exceptions", "label": "پیام‌های برنامه‌ریزی"},
]


def parenthesized_label(parent: str, tab: str) -> str:
    parent = (parent or "").strip()
    tab = (tab or "").strip()
    if not tab:
        return parent
    return f"{parent} ({tab})"


def is_systemic_source(source: str) -> bool:
    return bool(source) and str(source).startswith(SOURCE_SYSTEMIC_PREFIX)


def parse_systemic_tab(source: str) -> str | None:
    if not is_systemic_source(source):
        return None
    tab = str(source)[len(SOURCE_SYSTEMIC_PREFIX) :].strip()
    return tab or None


def is_dict_row_source(source: str) -> bool:
    """Sources whose report rows are plain dicts (not Django model instances)."""
    src = str(source or "")
    return src in {SOURCE_WEEKLY, "history"} or is_systemic_source(src)


def _dict_get(key: str):
    return lambda r, _k=key: (r.get(_k, "") if isinstance(r, dict) else "")


def _cols(pairs: list[tuple[str, str]]) -> list[tuple[str, str, object]]:
    return [(key, label, _dict_get(key)) for key, label in pairs]


WEEKLY_PLANNING_COLUMNS = _cols([
    # فهرست برنامه‌ریزی هفتگی
    ("row", "ردیف"),
    ("program_number", "شماره برنامه"),
    ("plan_date", "تاریخ برنامه"),
    ("weekday", "روز برنامه"),
    ("mode", "نحوه"),
    ("creator", "ایجاد کننده"),
    ("forms", "تعداد فرم"),
    ("calendar", "تقویم برنامه"),
    ("mold_count", "تعداد قالب برنامه"),
    ("active_mold_count", "تعداد قالب فعال"),
    # جدول اقلام برنامه (شامل ستون‌های مخفی)
    ("change_uid", "شناسه تعویض"),
    ("planning_date", "تاریخ برنامه‌ریزی"),
    ("machine_unit", "واحد دستگاه"),
    ("code", "کد کالا"),
    ("product", "نام جنس"),
    ("mold_number", "شماره قالب"),
    ("unique_code", "کد یکتا"),
    ("start_date", "تاریخ شروع"),
    ("start_weekday", "روز شروع"),
    ("quantity", "مقدار تولید"),
    ("cycle", "سیکل پیش‌فرض"),
    ("production_hours", "ساعت تولید"),
    ("active_cavities", "تعداد حفره فعال"),
    ("production_days", "روزهای تولید"),
    ("plan_status", "وضعیت برنامه"),
])

SYSTEMIC_COLUMNS: dict[str, list[tuple[str, str, object]]] = {
    "balance": _cols([
        ("product_code", "کد"),
        ("product_name", "نام"),
        ("order_qty", "سفارش"),
        ("forecast_qty", "پیش‌بینی"),
        ("stock", "موجودی"),
        ("open_plan_qty", "برنامه باز"),
        ("net_gap", "کسری"),
        ("surplus", "مازاد"),
        ("status", "وضعیت"),
        ("unassembled", "موجودی مونتاژ‌نشده"),
        ("depot_ceiling", "سقف دپو"),
        ("priority", "اولویت"),
        ("backlog", "معوق"),
    ]),
    "materials": _cols([
        ("component_code", "کد جزء / ماده"),
        ("component_name", "نام"),
        ("need", "نیاز"),
        ("have", "موجود"),
        ("gap", "کسری"),
        ("parents", "والدها"),
    ]),
    "capacity": _cols([
        ("machine_label", "دستگاه"),
        ("unit_number", "واحد"),
        ("hours", "ساعت برنامه"),
        ("available", "ظرفیت هفته"),
        ("load_pct", "بار٪"),
        ("item_count", "قالب/ردیف"),
        ("status", "وضعیت"),
    ]),
    "variance": _cols([
        ("uid", "شناسه"),
        ("plan_number", "شماره برنامه"),
        ("product_name", "جنس"),
        ("planned_qty", "مقدار برنامه"),
        ("produced_qty", "مقدار واقعی"),
        ("qty_gap", "اختلاف"),
        ("planned_cycle", "سیکل برنامه"),
        ("last_cycle", "آخرین سیکل"),
        ("scrap_qty", "ضایعات"),
    ]),
    "exceptions": _cols([
        ("code", "کد"),
        ("severity", "شدت"),
        ("title", "عنوان"),
        ("detail", "شرح"),
        ("product_code", "کد کالا"),
    ]),
}

_BALANCE_STATUS = {
    "shortage": "کسری",
    "backlog": "معوق",
    "reorder": "سفارش مجدد",
    "surplus": "مازاد",
    "covered": "پوشش",
}
_CAPACITY_STATUS = {
    "overload": "اضافه‌بار",
    "tight": "نزدیک ظرفیت",
    "idle": "آزاد",
    "ok": "متعادل",
}
_SEVERITY = {"serious": "جدی", "watch": "قابل‌پیگیری"}


def columns_for_app_source(source: str) -> list[tuple[str, str, object]]:
    if source == SOURCE_WEEKLY:
        return list(WEEKLY_PLANNING_COLUMNS)
    tab = parse_systemic_tab(source)
    if tab and tab in SYSTEMIC_COLUMNS:
        return list(SYSTEMIC_COLUMNS[tab])
    return []


def weekly_planning_group() -> dict:
    return {
        "id": SOURCE_WEEKLY,
        "label": "برنامه‌ریزی هفتگی",
        "hint": "فهرست برنامه و اقلام آن، شامل ستون‌های مخفی و آشکار.",
        "columns": [(k, label) for k, label, _ in WEEKLY_PLANNING_COLUMNS],
    }


def systemic_groups() -> list[dict]:
    groups = []
    for tab in SYSTEMIC_TABS:
        cols = SYSTEMIC_COLUMNS[tab["id"]]
        groups.append({
            "id": f"{SOURCE_SYSTEMIC_PREFIX}{tab['id']}",
            "label": parenthesized_label("برنامه‌ریزی توسط سیستم", tab["label"]),
            "hint": "همهٔ سرستون‌های این تب، شامل فیلدهای کمکی داده‌ای.",
            "columns": [(k, label) for k, label, _ in cols],
        })
    return groups


def load_all_flex_columns(destination_id: str, level_id: str) -> list[dict]:
    """Schema columns including naming keys that are hidden/inactive."""
    prefix = f"transfer.field.{destination_id}.{level_id}."
    seen: dict[str, dict] = {}
    rows = SystemNamingKey.objects.filter(key__startswith=prefix).order_by("order", "id")
    for r in rows:
        col = (r.column_key or r.key[len(prefix):]).strip()
        if not col:
            continue
        seen[col] = {
            "key": col,
            "label": r.label or col,
            "type": "string",
            "required": False,
            "is_key": bool(r.is_key),
        }
    ds = FlexibleDataset.objects.filter(
        destination_id=destination_id, level_id=level_id
    ).first()
    if ds and isinstance(ds.columns, list):
        for c in ds.columns:
            if not isinstance(c, dict):
                continue
            key = str(c.get("key") or "").strip()
            if not key:
                continue
            if key not in seen:
                seen[key] = {
                    "key": key,
                    "label": str(c.get("label") or key),
                    "type": str(c.get("type") or "string"),
                    "required": False,
                    "is_key": bool(c.get("is_key")),
                }
    return list(seen.values())


def product_data_groups() -> list[dict]:
    groups: list[dict] = []
    for tab in list_tab_levels("product_data", DEFAULT_PRODUCT_TABS):
        level_id = tab["id"]
        cols = load_all_flex_columns("product_data", level_id)
        columns = [(c["key"], c["label"]) for c in cols]
        groups.append({
            "id": f"flex__product_data__{level_id}",
            "label": parenthesized_label("دیتای محصولات", tab["label"]),
            "hint": "ستون‌های منتقل‌شده به این تب (مخفی و آشکار). فایل اکسل خام منبع نیست.",
            "columns": columns,
        })
    return groups


def _jdate(value) -> str:
    from planning.utils import format_jdate
    return format_jdate(value)


def _production_days_text(raw) -> str:
    if not isinstance(raw, list):
        return ""
    bits = []
    for item in raw:
        if isinstance(item, dict):
            date = str(item.get("date") or "").strip()
            if date:
                bits.append(date)
    return "، ".join(bits)


def weekly_planning_rows() -> list[dict]:
    from django.db.models import Count, Q
    from production.models import ProductionProgram
    from planning.models import WeeklyPlan, WeeklyPlanItem

    active_statuses = [
        ProductionProgram.Status.RUNNING,
        ProductionProgram.Status.TEMP_STOP,
    ]
    counts = {
        p.pk: p
        for p in WeeklyPlan.objects.annotate(
            mold_count=Count("items", distinct=True),
            active_mold_count=Count(
                "items__program",
                filter=Q(items__program__status__in=active_statuses),
                distinct=True,
            ),
        )
    }
    items = (
        WeeklyPlanItem.objects.select_related(
            "plan", "plan__created_by", "product", "machine", "unit", "mold"
        )
        .prefetch_related("lines", "lines__mold")
        .order_by("plan_id", "sequence", "pk")
    )
    rows: list[dict] = []
    index = 0
    for item in items:
        plan = item.plan
        stats = counts.get(plan.pk)
        lines = list(item.lines.all()) or [None]
        for line in lines:
            index += 1
            mold = None
            if line is not None:
                mold = getattr(line, "mold", None) or item.mold
            else:
                mold = item.mold
            rows.append({
                "row": index,
                "program_number": plan.program_number,
                "plan_date": _jdate(plan.date),
                "weekday": plan.weekday_name,
                "mode": plan.get_planning_mode_display(),
                "creator": getattr(plan.created_by, "username", "") or "",
                "forms": "",
                "calendar": "",
                "mold_count": getattr(stats, "mold_count", 0) if stats else 0,
                "active_mold_count": getattr(stats, "active_mold_count", 0) if stats else 0,
                "change_uid": item.uid,
                "planning_date": _jdate(plan.date),
                "machine_unit": f"{item.machine.number}/{item.unit.number}",
                "code": item.product.code,
                "product": item.product.name,
                "mold_number": str(mold) if mold else "",
                "unique_code": (getattr(line, "uid", None) or "") if line is not None else "",
                "start_date": _jdate(item.mold_change_date),
                "start_weekday": item.get_mold_change_weekday_display(),
                "quantity": getattr(line, "quantity", "") if line is not None else "",
                "cycle": getattr(line, "cycle", "") if line is not None else "",
                "production_hours": getattr(line, "production_hours", "") if line is not None else "",
                "active_cavities": (
                    getattr(line, "active_cavities", None)
                    if line is not None
                    else item.active_cavities
                ) or item.active_cavities,
                "production_days": _production_days_text(item.production_days),
                "plan_status": plan.get_status_display(),
            })
    return rows


def _display_balance(row: dict) -> dict:
    out = dict(row)
    out["status"] = _BALANCE_STATUS.get(str(row.get("status") or ""), row.get("status") or "")
    out["backlog"] = "بله" if row.get("backlog") else ""
    return out


def _display_capacity(row: dict) -> dict:
    out = dict(row)
    out["status"] = _CAPACITY_STATUS.get(str(row.get("status") or ""), row.get("status") or "")
    return out


def _display_exceptions(row: dict) -> dict:
    out = dict(row)
    out["severity"] = _SEVERITY.get(str(row.get("severity") or ""), row.get("severity") or "")
    return out


def _display_materials(row: dict) -> dict:
    out = dict(row)
    parents = row.get("parents") or []
    if isinstance(parents, list):
        out["parents"] = "، ".join(str(p) for p in parents if p)
    return out


def systemic_rows(tab: str) -> list[dict]:
    from planning.intelligence import cockpit_payload

    payload = cockpit_payload()
    raw = list(payload.get(tab) or [])
    if tab == "balance":
        return [_display_balance(r) for r in raw]
    if tab == "capacity":
        return [_display_capacity(r) for r in raw]
    if tab == "exceptions":
        return [_display_exceptions(r) for r in raw]
    if tab == "materials":
        return [_display_materials(r) for r in raw]
    return [dict(r) for r in raw]


def rows_for_app_source(source: str) -> list[dict] | None:
    """Return dict rows for app sources, or None if this is not an app dict-source."""
    if source == SOURCE_WEEKLY:
        return weekly_planning_rows()
    tab = parse_systemic_tab(source)
    if tab:
        return systemic_rows(tab)
    return None
