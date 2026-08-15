"""Column catalogs and leveled report data resolution."""

from __future__ import annotations

from catalog.models import Product
from production.models import PipeProduction, ProductionDayEntry


def _fit_material_used(r):
    w = r.program.item.product.unit_weight_grams or 0
    return round(float(w) * r.produced_quantity * r.active_cavities / 1000, 2)


def _fit_material_scrap(r):
    w = r.program.item.product.unit_weight_grams or 0
    return round(float(w) * r.scrap_quantity * r.active_cavities / 1000, 2)


def _dev_reason(r):
    return r.deviation_reason.label if r.deviation_reason_id else ""


FITTING_COLUMNS = [
    ("uid", "شناسه برنامه", lambda r: r.program.item.uid),
    ("document_date", "تاریخ سند", lambda r: str(r.date)),
    ("date", "تاریخ", lambda r: str(r.date)),
    ("machine", "دستگاه/واحد", lambda r: r.program.machine_label),
    ("code", "کد کالا", lambda r: r.program.item.product.code),
    ("product", "نام محصول", lambda r: r.program.item.product.name),
    ("cycle", "سیکل یک‌ضرب", lambda r: r.cycle),
    ("cavities", "حفره فعال", lambda r: r.active_cavities),
    ("produced", "تولیدشده (ضرب)", lambda r: r.produced_quantity),
    ("planned", "برنامه‌ریزی‌شده (ضرب)", lambda r: r.planned_quantity),
    ("scrap", "ضایعات", lambda r: r.scrap_quantity),
    ("material_used", "مواد مصرفی (kg)", _fit_material_used),
    ("material_scrap", "مواد ضایعاتی (kg)", _fit_material_scrap),
    ("deviation", "انحراف", lambda r: r.deviation),
    ("deviation_reason", "دلیل انحراف", _dev_reason),
    ("stock_finished", "موجودی محصول", lambda r: r.program.item.product.stock_finished),
    ("stock_unassembled", "موجودی مونتاژ‌نشده", lambda r: r.program.item.product.stock_unassembled),
]

PIPE_COLUMNS = [
    ("document_date", "تاریخ سند", lambda r: str(r.date)),
    ("date", "تاریخ", lambda r: str(r.date)),
    ("unit", "واحد", lambda r: f"واحد {r.unit.number}"),
    ("line", "خط", lambda r: str(r.line.number)),
    ("type", "نوع", lambda r: r.pipe_type),
    ("code", "کد کالا", lambda r: r.product.code if r.product_id else ""),
    ("product", "نام محصول", lambda r: r.product.name if r.product_id else ""),
    ("produced", "تولیدشده", lambda r: r.produced_quantity),
    ("planned", "برنامه‌ریزی‌شده", lambda r: r.planned_quantity),
    ("scrap", "ضایعات", lambda r: r.scrap_quantity),
    ("material_used", "مواد مصرفی (kg)", lambda r: r.material_used),
    ("material_scrap", "مواد ضایعاتی (kg)", lambda r: r.material_scrap),
    ("deviation", "انحراف", lambda r: r.deviation),
    ("deviation_reason", "دلیل انحراف", _dev_reason),
    ("stock_finished", "موجودی محصول", lambda r: r.product.stock_finished if r.product_id else ""),
    ("stock_unassembled", "موجودی مونتاژ‌نشده", lambda r: r.product.stock_unassembled if r.product_id else ""),
]

PRODUCT_COLUMNS = [
    ("code", "کد کالا", lambda r: r.code),
    ("product", "نام محصول", lambda r: r.name),
    ("subgroup", "زیرگروه", lambda r: str(r.subgroup)),
    ("stock_finished", "موجودی محصول", lambda r: r.stock_finished),
    ("stock_unassembled", "موجودی مونتاژ‌نشده", lambda r: r.stock_unassembled),
    ("reorder_level", "سطح سفارش مجدد", lambda r: r.reorder_level),
    ("depot_ceiling", "سقف دپو", lambda r: r.depot_ceiling or ""),
    ("per_carton", "تعداد در کارتن", lambda r: r.per_carton or ""),
    ("per_bag", "تعداد در کیسه", lambda r: r.per_bag or ""),
    ("main_cavities", "حفره اصلی", lambda r: r.main_cavities or ""),
    ("last_cycle", "آخرین سیکل", lambda r: r.last_cycle or ""),
    ("unit_weight_grams", "وزن واحد (گرم)", lambda r: r.unit_weight_grams),
]

FILE_COLUMNS = [
    ("file_document_date", "تاریخ سند (فایل)", None),
    ("file_stock", "موجودی (فایل)", None),
    ("file_col_1", "ستون فایل ۱", None),
    ("file_col_2", "ستون فایل ۲", None),
]

COLUMNS_BY_SOURCE = {
    "fitting": FITTING_COLUMNS,
    "pipe": PIPE_COLUMNS,
    "product": PRODUCT_COLUMNS,
    "file": [(k, label, getter) for k, label, getter in FILE_COLUMNS],
}

COLUMN_GROUPS = [
    {
        "id": "fitting",
        "label": "تولید اتصالات (داده ذخیره‌شده)",
        "columns": [(k, label) for k, label, _ in FITTING_COLUMNS],
    },
    {
        "id": "pipe",
        "label": "تولید لوله (داده ذخیره‌شده)",
        "columns": [(k, label) for k, label, _ in PIPE_COLUMNS],
    },
    {
        "id": "product",
        "label": "کالا و موجودی",
        "columns": [(k, label) for k, label, _ in PRODUCT_COLUMNS],
    },
    {
        "id": "file",
        "label": "ستون‌های فایل / داده خارجی",
        "columns": [(k, label) for k, label, _ in FILE_COLUMNS],
        "hint": "پس از اتصال فایل، این ستون‌ها از اکسل خوانده می‌شوند.",
    },
]


def column_label_map(source: str) -> dict[str, str]:
    mapping = {k: label for k, label, _ in COLUMNS_BY_SOURCE.get(source, [])}
    for k, label, _ in FILE_COLUMNS:
        mapping[k] = label
    return mapping


def available_keys(source: str) -> set[str]:
    keys = {k for k, _, _ in COLUMNS_BY_SOURCE.get(source, [])}
    keys.update(k for k, _, _ in FILE_COLUMNS)
    return keys


def normalize_columns(raw) -> list[dict]:
    """Accept legacy string keys or structured dicts → list of dicts."""
    out = []
    if not raw:
        return out
    for item in raw:
        if isinstance(item, str):
            out.append({"key": item, "source": "", "level": 1, "label": item})
            continue
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        try:
            level = int(item.get("level") or 1)
        except (TypeError, ValueError):
            level = 1
        level = max(1, min(10, level))
        source = str(item.get("source") or "").strip()
        label = str(item.get("label") or key)[:120]
        if not label:
            label = column_label_map(source).get(key, key) if source else key
        out.append({"key": key, "source": source, "level": level, "label": label})
    return out


def _getter_map(source: str) -> dict:
    by_key = {}
    for k, label, getter in COLUMNS_BY_SOURCE.get(source, []):
        by_key[k] = (label, getter)
    for k, label, getter in FILE_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    return by_key


def _queryset(data_source: str):
    if data_source == "pipe":
        return PipeProduction.objects.select_related(
            "unit", "line", "product", "deviation_reason"
        ).all()
    if data_source == "product":
        return Product.objects.select_related("subgroup").filter(is_active=True)
    return ProductionDayEntry.objects.select_related(
        "program__item__product",
        "program__item__machine__unit",
        "deviation_reason",
    ).all()


def _resolve_specs(data_source: str, column_specs: list[dict]) -> list[dict]:
    by_key = _getter_map(data_source)
    # Also allow file getters
    for k, label, getter in FILE_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    resolved = []
    for spec in column_specs:
        key = spec["key"]
        if key not in by_key and spec.get("source") and spec["source"] != data_source:
            # Try source-specific map (e.g. product keys on fitting already exist)
            alt = _getter_map(spec["source"])
            if key in alt:
                label, getter = alt[key]
                resolved.append({**spec, "label": spec.get("label") or label, "getter": getter})
                continue
        if key in by_key:
            label, getter = by_key[key]
            resolved.append(
                {
                    **spec,
                    "label": spec.get("label") or label,
                    "getter": getter or (lambda _r: ""),
                }
            )
    return resolved


def _build_records(data_source: str, specs: list[dict]) -> list[dict]:
    rows = []
    for record in _queryset(data_source):
        cell = {}
        for spec in specs:
            try:
                cell[spec["key"]] = spec["getter"](record) if spec.get("getter") else ""
            except Exception:
                cell[spec["key"]] = ""
        rows.append(cell)
    return rows


def run_report(
    data_source: str,
    columns,
    *,
    level: int = 1,
    filters: dict | None = None,
) -> tuple[list[str], list[list], list[dict], bool]:
    """Return headers, display rows, row filter payloads, and whether drill-down exists.

    Display columns are those with ``level == current level``.
    If deeper levels exist, rows are unique combinations of the current level.
    """
    specs = normalize_columns(columns)
    # Fill missing labels from catalog
    for spec in specs:
        if not spec.get("label") or spec["label"] == spec["key"]:
            src = spec.get("source") or data_source
            spec["label"] = column_label_map(src).get(spec["key"], spec["key"])
        if not spec.get("source"):
            spec["source"] = data_source

    if not specs:
        # Default all columns of source at level 1
        specs = [
            {"key": k, "source": data_source, "level": 1, "label": label}
            for k, label, _ in COLUMNS_BY_SOURCE.get(data_source, [])
        ]

    resolved = _resolve_specs(data_source, specs)
    if not resolved:
        return [], [], [], False

    level = max(1, min(10, int(level or 1)))
    filters = filters or {}
    all_records = _build_records(data_source, resolved)

    # Apply parent filters
    filtered = []
    for row in all_records:
        ok = True
        for fk, fv in filters.items():
            if str(row.get(fk, "")) != str(fv):
                ok = False
                break
        if ok:
            filtered.append(row)

    level_cols = [s for s in resolved if s["level"] == level]
    if not level_cols:
        # Fall back to deepest available ≤ level, or all
        available_levels = sorted({s["level"] for s in resolved})
        pick = None
        for lv in available_levels:
            if lv <= level:
                pick = lv
        if pick is None:
            level_cols = resolved
            level = available_levels[0] if available_levels else 1
        else:
            level_cols = [s for s in resolved if s["level"] == pick]
            level = pick

    deeper = any(s["level"] > level for s in resolved)
    headers = [s["label"] for s in level_cols]
    keys = [s["key"] for s in level_cols]

    display_rows: list[list] = []
    payloads: list[dict] = []
    seen = set()
    for row in filtered:
        values = tuple(str(row.get(k, "")) for k in keys)
        if deeper:
            if values in seen:
                continue
            seen.add(values)
        display_rows.append([row.get(k, "") for k in keys])
        payloads.append({k: row.get(k, "") for k in keys})

    return headers, display_rows, payloads, deeper


# Backward-compatible thin wrapper used by older call sites
def run_report_flat(data_source: str, column_keys: list) -> tuple[list[str], list[list]]:
    specs = column_keys
    if column_keys and isinstance(column_keys[0], str):
        specs = [{"key": k, "source": data_source, "level": 1} for k in column_keys]
    headers, rows, _payloads, _deeper = run_report(data_source, specs, level=1)
    return headers, rows
