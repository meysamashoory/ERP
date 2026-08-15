"""Column catalogs and report data resolution."""

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


# Per data-source column definitions: (key, label, getter)
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

# File / external columns (keys reserved for future Excel wiring).
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


def run_report(data_source: str, column_keys: list[str]) -> tuple[list[str], list[list]]:
    """Resolve headers and rows for a saved report definition."""
    columns = COLUMNS_BY_SOURCE.get(data_source, FITTING_COLUMNS)
    by_key = {k: (label, getter) for k, label, getter in columns}
    # File columns are not yet wired — show empty cells if selected.
    for k, label, _ in FILE_COLUMNS:
        by_key.setdefault(k, (label, lambda _r: ""))

    active = []
    for key in column_keys:
        if key in by_key:
            active.append((key, by_key[key][0], by_key[key][1]))
    if not active:
        active = [(k, label, getter) for k, label, getter in columns]

    headers = [label for _k, label, _g in active]

    if data_source == "pipe":
        qs = PipeProduction.objects.select_related(
            "unit", "line", "product", "deviation_reason"
        ).all()
    elif data_source == "product":
        qs = Product.objects.select_related("subgroup").filter(is_active=True)
    else:
        qs = ProductionDayEntry.objects.select_related(
            "program__item__product",
            "program__item__machine__unit",
            "deviation_reason",
        ).all()

    rows = []
    for record in qs:
        row = []
        for _k, _label, getter in active:
            try:
                row.append(getter(record) if getter else "")
            except Exception:
                row.append("")
        rows.append(row)
    return headers, rows
