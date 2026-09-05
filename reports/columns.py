"""Column catalogs and leveled report data resolution."""

from __future__ import annotations

import secrets

from catalog.models import Product
from production.models import PipeProduction, ProductionDayEntry


def new_column_uid() -> str:
    """Unique id so copied columns stay independent while sharing data_key."""
    return "c" + secrets.token_hex(4)


def storage_key(spec: dict) -> str:
    """Key used to store/read cell values (uid preferred, else data key)."""
    uid = str(spec.get("uid") or "").strip()
    if uid:
        return uid
    return str(spec.get("key") or "").strip()


def data_key(spec: dict) -> str:
    """Semantic column type key (shared by copies)."""
    return str(spec.get("key") or "").strip()


def _fit_material_used(r):
    w = r.program.item.product.unit_weight_grams or 0
    return round(float(w) * r.produced_quantity * r.active_cavities / 1000, 2)


def _fit_material_scrap(r):
    w = r.program.item.product.unit_weight_grams or 0
    return round(float(w) * r.scrap_quantity * r.active_cavities / 1000, 2)


def _dev_reason(r):
    return r.deviation_reason.label if r.deviation_reason_id else ""


FITTING_COLUMNS = [
    ("uid", "شناسه برنامه", lambda r: r.program.resolved_uid),
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


def _dict_get(key: str):
    return lambda r, _k=key: (r.get(_k, "") if isinstance(r, dict) else "")


HISTORY_COLUMNS = [
    ("plan_number", "شماره برنامه", _dict_get("plan_number")),
    ("plan_date", "تاریخ برنامه‌ریزی", _dict_get("plan_date_display")),
    ("machine", "شناسه دستگاه", _dict_get("machine")),
    ("product_name", "نام جنس", _dict_get("product_name")),
    ("product_code", "کد کالا", _dict_get("product_code")),
    ("mold_number", "شماره قالب", _dict_get("mold_number")),
    ("unique_code", "کد یکتا", _dict_get("unique_code")),
    ("plan_start", "تاریخ شروع برنامه", _dict_get("plan_start_display")),
    ("actual_start", "تاریخ شروع واقعی", _dict_get("actual_start_display")),
    ("actual_end", "تاریخ پایان تولید", _dict_get("actual_end_display")),
    ("planned_qty", "مقدار تولید برنامه (عدد)", _dict_get("planned_qty")),
    ("actual_qty", "مقدار تولید واقعی (عدد)", _dict_get("actual_qty")),
    ("planned_cycle", "سیکل تولید برنامه (ثانیه)", _dict_get("planned_cycle")),
    ("last_cycle", "آخرین سیکل تولید (ثانیه)", _dict_get("last_cycle")),
    ("planned_hours", "ساعت تولید برنامه", _dict_get("planned_hours_display")),
    ("active_cavities", "تعداد حفره فعال", _dict_get("active_cavities")),
    ("last_cavities", "آخرین وضعیت حفره", _dict_get("last_cavities")),
    ("scrap", "ضایعات تولید", _dict_get("scrap")),
    ("status_label", "وضعیت", _dict_get("status_label")),
    ("change_uid", "شناسه تعویض", _dict_get("change_uid")),
]


def is_excel_table_source(source: str) -> bool:
    return bool(source) and str(source).startswith("excel_table_")


def parse_excel_table_id(source: str) -> int | None:
    if not is_excel_table_source(source):
        return None
    raw = str(source).removeprefix("excel_table_")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_flex_source(source: str) -> bool:
    return bool(source) and str(source).startswith("flex__")


def parse_flex_source(source: str) -> tuple[str, str] | None:
    """Parse ``flex__{destination}__{level}`` → (destination_id, level_id)."""
    if not is_flex_source(source):
        return None
    parts = str(source).split("__", 2)
    if len(parts) != 3 or parts[0] != "flex":
        return None
    destination_id = (parts[1] or "").strip()
    level_id = (parts[2] or "").strip()
    if not destination_id or not level_id:
        return None
    return destination_id, level_id


def flex_source_id(destination_id: str, level_id: str) -> str:
    return f"flex__{destination_id}__{level_id}"


def _excel_table_column_tuples(table) -> list[tuple[str, str, object]]:
    cols = []
    for key, label in table.column_defs():
        cols.append((key, label, None))
    return cols


def _flex_column_tuples(destination_id: str, level_id: str) -> list[tuple[str, str, object]]:
    from catalog.flexible_data import load_schema_columns

    out: list[tuple[str, str, object]] = []
    for col in load_schema_columns(destination_id, level_id):
        key = str(col.get("key") or "").strip()
        if not key:
            continue
        label = str(col.get("label") or key)
        out.append((key, label, _dict_get(key)))
    return out


def get_product_data_flex_groups() -> list[dict]:
    """One source group per product-data tab that has a transferred schema."""
    from catalog.flexible_data import DEFAULT_PRODUCT_TABS, list_tab_levels

    groups: list[dict] = []
    for tab in list_tab_levels("product_data", DEFAULT_PRODUCT_TABS):
        level_id = tab["id"]
        tuples = _flex_column_tuples("product_data", level_id)
        if not tuples:
            continue
        groups.append({
            "id": flex_source_id("product_data", level_id),
            "label": f"دیتای محصولات — {tab['label']}",
            "hint": "فقط داده‌های منتقل‌شده به این تب (نه فایل اکسل خام).",
            "columns": [(k, label) for k, label, _ in tuples],
        })
    return groups


def get_column_groups() -> list[dict]:
    """Built-in sources + history + transferred product-data tabs (no raw Excel)."""
    groups = [g for g in COLUMN_GROUPS if g.get("id") not in ("file",)]
    groups.append({
        "id": "history",
        "label": "سوابق تولید",
        "hint": "ردیف‌های صفحه سوابق تولید (برنامه‌های زنده و بایگانی).",
        "columns": [(k, label) for k, label, _ in HISTORY_COLUMNS],
    })
    groups.extend(get_product_data_flex_groups())
    naming_widths = naming_default_width_map()
    return [enrich_column_group(g, naming_widths=naming_widths) for g in groups]


DATA_ENTRY_COLUMNS = [
    ("data_titles", "عناوین ورودی داده", None),
    ("awaiting_production", "قالب در انتظار تولید", None),
    ("running_production", "قالب در حال تولید", None),
    ("entry_notes", "توضیحات", None),
]

DATA_ENTRY_KEYS = {k for k, _, _ in DATA_ENTRY_COLUMNS}

DATA_ENTRY_FIELD_TYPES = {
    "data_titles": "text",
    "awaiting_production": "product_select",
    "running_production": "product_select",
    "entry_notes": "textarea",
}


def _list_products_by_program_status(status: str) -> list[dict]:
    """Unique product names from production programs in the given status."""
    from production.models import ProductionProgram

    programs = (
        ProductionProgram.objects.filter(status=status)
        .select_related("item__product")
        .order_by("item__product__name", "pk")
    )
    seen: set[str] = set()
    out: list[dict] = []
    for prog in programs:
        product = prog.item.product if prog.item_id and prog.item.product_id else None
        name = (product.name if product else "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "id": f"prod-{product.pk}",
            "label": name,
            "value": name,
            "product_id": product.pk,
        })
    return out


def list_awaiting_production_molds() -> list[dict]:
    """Product names currently awaiting production (legacy name kept for imports)."""
    from production.models import ProductionProgram
    return _list_products_by_program_status(ProductionProgram.Status.AWAITING)


def list_running_production_products() -> list[dict]:
    """Product names currently in production."""
    from production.models import ProductionProgram
    return _list_products_by_program_status(ProductionProgram.Status.RUNNING)


def awaiting_molds_display_text(molds: list[dict] | None = None) -> str:
    items = molds if molds is not None else list_awaiting_production_molds()
    return " ، ".join(item["label"] for item in items if item.get("label"))


def product_options_for_key(key: str) -> list[dict]:
    if key == "awaiting_production":
        return list_awaiting_production_molds()
    if key == "running_production":
        return list_running_production_products()
    return []


COLUMNS_BY_SOURCE = {
    "fitting": FITTING_COLUMNS,
    "pipe": PIPE_COLUMNS,
    "product": PRODUCT_COLUMNS,
    "history": HISTORY_COLUMNS,
    "file": [(k, label, getter) for k, label, getter in FILE_COLUMNS],
    "data_entry": [(k, label, getter) for k, label, getter in DATA_ENTRY_COLUMNS],
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
        "id": "data_entry",
        "label": "ثبت داده",
        "columns": [(k, label) for k, label, _ in DATA_ENTRY_COLUMNS],
        "hint": "ستون‌های قالب در انتظار/در حال تولید فقط نام کالای مرتبط با آن وضعیت را نشان می‌دهند.",
    },
    {
        "id": "file",
        "label": "ستون‌های فایل / داده خارجی",
        "columns": [(k, label) for k, label, _ in FILE_COLUMNS],
        "hint": "استفاده مستقیم از فایل اکسل پشتیبانی نمی‌شود؛ داده را به مقصد منتقل کنید.",
    },
]

# Prefer get_column_groups() at request time for history + transferred flex tabs.

# Default report column widths by value kind (px). Overridden by SystemNamingKey.default_width_px.
DEFAULT_WIDTH_BY_KIND = {
    "text": 160,
    "number": 96,
    "date": 112,
    "code": 120,
    "select": 140,
    "textarea": 220,
}

_DATE_KEY_FRAGMENTS = ("date", "_at", "start", "end")


def column_width_kind(source: str, key: str) -> str:
    """Classify a report column for default width selection."""
    key = str(key or "").strip()
    source = str(source or "").strip()
    if not key:
        return "text"
    if is_data_entry_key(key, source):
        ft = entry_field_type(key)
        if ft == "textarea":
            return "textarea"
        if ft in {"product_select", "select"}:
            return "select"
        return "text"
    low = key.lower()
    if low in {"cycle", "last_cycle", "planned_cycle"}:
        return "number"
    if any(frag in low for frag in _IDENTITY_KEY_FRAGMENTS):
        if any(frag in low for frag in ("code", "uid", "id", "sku", "barcode", "unique")):
            return "code"
        return "text"
    if key in _NUMERIC_METRIC_KEYS or any(frag in low for frag in _NUMERIC_KEY_FRAGMENTS):
        return "number"
    if "date" in low or low.endswith("_at"):
        return "date"
    if low in {"type", "unit", "line", "status_label", "subgroup", "deviation_reason"}:
        return "select"
    # Flex / unknown: prefer text unless clearly numeric.
    if is_flex_source(source):
        try:
            parsed = parse_flex_source(source)
            if parsed:
                for col_key, _label, _getter in _flex_column_tuples(parsed[0], parsed[1]):
                    if col_key != key:
                        continue
                    # Flex schemas use string/number-ish labels; fall through.
                    break
        except Exception:  # noqa: BLE001
            pass
    return "text"


def type_default_column_width(source: str, key: str) -> int:
    kind = column_width_kind(source, key)
    return int(DEFAULT_WIDTH_BY_KIND.get(kind, DEFAULT_WIDTH_BY_KIND["text"]))


def naming_default_width_map() -> dict[str, int]:
    """Map ``report.col.<source>.<key>`` → configured default width (px)."""
    out: dict[str, int] = {}
    try:
        from catalog.models import SystemNamingKey

        for row in SystemNamingKey.objects.filter(
            key__startswith="report.col.",
            category=SystemNamingKey.Category.COLUMN,
        ).only("key", "default_width_px"):
            try:
                w = int(row.default_width_px or 0)
            except (TypeError, ValueError):
                w = 0
            if w > 0:
                out[row.key] = max(40, min(800, w))
    except Exception:  # noqa: BLE001
        pass
    return out


def resolve_default_column_width(
    source: str,
    key: str,
    *,
    naming_widths: dict[str, int] | None = None,
) -> int:
    """Configured source default, else type-based fallback."""
    source = str(source or "").strip()
    key = str(key or "").strip()
    naming_key = f"report.col.{source}.{key}"
    widths = naming_widths if naming_widths is not None else naming_default_width_map()
    configured = int(widths.get(naming_key) or 0)
    if configured > 0:
        return max(40, min(800, configured))
    return type_default_column_width(source, key)


def enrich_column_group(group: dict, *, naming_widths: dict[str, int] | None = None) -> dict:
    """Attach default_widths map and optional 3rd tuple element for the builder UI."""
    sid = str(group.get("id") or "")
    widths: dict[str, int] = {}
    cols_out = []
    for pair in group.get("columns") or []:
        if not pair:
            continue
        key = str(pair[0])
        label = pair[1] if len(pair) > 1 else key
        width = resolve_default_column_width(sid, key, naming_widths=naming_widths)
        widths[key] = width
        cols_out.append((key, label, width))
    enriched = dict(group)
    enriched["columns"] = cols_out
    enriched["default_widths"] = widths
    return enriched


def is_data_entry_key(key: str, source: str = "") -> bool:
    return key in DATA_ENTRY_KEYS or source == "data_entry"


def entry_field_type(key: str) -> str:
    return DATA_ENTRY_FIELD_TYPES.get(key, "text")


def row_signature(row: dict, keys: list[str]) -> str:
    return "|".join(f"{k}={row.get(k, '')}" for k in keys)


def _columns_for_source(source: str) -> list[tuple[str, str, object]]:
    # Legacy excel_table_* sources: do not expose raw Excel rows anymore.
    if is_excel_table_source(source):
        return []
    if is_flex_source(source):
        parsed = parse_flex_source(source)
        if not parsed:
            return []
        return _flex_column_tuples(parsed[0], parsed[1])
    return list(COLUMNS_BY_SOURCE.get(source, []))


def column_label_map(source: str) -> dict[str, str]:
    mapping = {k: label for k, label, _ in _columns_for_source(source)}
    for k, label, _ in FILE_COLUMNS:
        mapping[k] = label
    for k, label, _ in DATA_ENTRY_COLUMNS:
        mapping[k] = label
    for k, label, _ in HISTORY_COLUMNS:
        mapping.setdefault(k, label)
    if is_flex_source(source):
        for k, label, _ in _columns_for_source(source):
            mapping[k] = label
    # Overlay editable system naming registry (report.col.<source>.<key>)
    try:
        from catalog.models import SystemNamingKey

        prefix = f"report.col.{source}."
        for row in SystemNamingKey.objects.filter(
            key__startswith=prefix, is_active=True
        ).only("key", "label", "column_key"):
            ck = row.column_key or row.key[len(prefix):]
            if ck and row.label:
                mapping[ck] = row.label
    except Exception:  # noqa: BLE001
        pass
    return mapping


def available_keys(source: str) -> set[str]:
    keys = {k for k, _, _ in _columns_for_source(source)}
    keys.update(k for k, _, _ in FILE_COLUMNS)
    keys.update(DATA_ENTRY_KEYS)
    return keys


# Measure / numeric fields that must not be used as drill-down keys.
_NUMERIC_METRIC_KEYS = frozenset({
    "cycle",
    "cavities",
    "produced",
    "planned",
    "scrap",
    "material_used",
    "material_scrap",
    "deviation",
    "stock_finished",
    "stock_unassembled",
    "reorder_level",
    "depot_ceiling",
    "per_carton",
    "per_bag",
    "main_cavities",
    "last_cycle",
    "unit_weight_grams",
    "planned_qty",
    "actual_qty",
    "planned_cycle",
    "planned_hours",
    "active_cavities",
    "last_cavities",
    "file_stock",
})

_NUMERIC_KEY_FRAGMENTS = (
    "qty",
    "quantity",
    "weight",
    "scrap",
    "stock",
    "hours",
    "cycle",
    "cavit",
    "material",
    "produced",
    "planned",
    "amount",
    "price",
    "count",
    "total",
    "sum",
    "kg",
    "gram",
)

_IDENTITY_KEY_FRAGMENTS = (
    "code",
    "uid",
    "id",
    "name",
    "title",
    "label",
    "machine",
    "product",
    "mold",
    "unique",
    "identifier",
    "sku",
    "barcode",
)


def column_can_be_key(source: str, key: str) -> bool:
    """Whether a column may be marked as a level key (identity, not a measure)."""
    key = str(key or "").strip()
    if not key:
        return False
    if key in _NUMERIC_METRIC_KEYS:
        return False
    if is_data_entry_key(key, source or ""):
        # Data-entry fields are textual identity/selectors — allow as keys.
        return True
    low = key.lower()
    if any(frag in low for frag in _IDENTITY_KEY_FRAGMENTS):
        # e.g. product_code, unique_code, change_uid — allow even if mixed with numbers
        if low in {"cycle", "last_cycle", "planned_cycle"}:
            return False
        return True
    if any(frag in low for frag in _NUMERIC_KEY_FRAGMENTS):
        return False
    # Dates / status / type / unit / line — usable parent context, allow
    if low in {
        "date",
        "document_date",
        "file_document_date",
        "plan_date",
        "plan_start",
        "actual_start",
        "actual_end",
        "status_label",
        "type",
        "unit",
        "line",
        "subgroup",
        "deviation_reason",
        "machine",
        "product",
        "code",
        "uid",
    }:
        return True
    # Unknown flex columns: allow unless clearly numeric-looking
    return True


def column_keyability_map() -> dict[str, dict[str, bool]]:
    """source_id → {column_key: can_be_key} for the report builder UI."""
    out: dict[str, dict[str, bool]] = {}
    for group in get_column_groups():
        sid = str(group.get("id") or "")
        out[sid] = {
            str(pair[0]): column_can_be_key(sid, str(pair[0]))
            for pair in (group.get("columns") or [])
            if pair
        }
    return out


def clamp_column_width(raw) -> int:
    """Column width in px; 0 means auto/default."""
    try:
        width = int(raw or 0)
    except (TypeError, ValueError):
        width = 0
    if width <= 0:
        return 0
    return max(40, min(800, width))


# Level modes: exact 1-9, upto_2..upto_8, all. Legacy int level maps to exact.
_LEVEL_ORDINALS = {
    1: "اول",
    2: "دوم",
    3: "سوم",
    4: "چهارم",
    5: "پنجم",
    6: "ششم",
    7: "هفتم",
    8: "هشتم",
    9: "نهم",
}
LEVEL_MODE_CHOICES: list[tuple[str, str]] = (
    [(str(i), _LEVEL_ORDINALS[i]) for i in range(1, 10)]
    + [(f"upto_{i}", f"تا {_LEVEL_ORDINALS[i]}") for i in range(2, 9)]
    + [("all", "همه سطوح")]
)




def clamp_sort_priority(raw) -> int:
    try:
        n = int(raw or 1)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(9, n))


def normalize_cell_align(raw) -> str:
    text = str(raw or "right").strip().lower()
    return text if text in {"left", "center", "right"} else "right"


def props_apply_at_level(spec: dict, level: int) -> bool:
    """Whether column property flags apply at the given report level."""
    mode = normalize_level_mode(spec.get("props_level_mode") or "all", 1)
    level = max(1, min(9, int(level or 1)))
    if mode == "all":
        return True
    if mode.startswith("upto_"):
        return level <= level_mode_max(mode)
    return level_mode_max(mode) == level

def normalize_level_mode(raw, legacy_level=1) -> str:
    text = str(raw or "").strip().lower()
    if text in {c[0] for c in LEVEL_MODE_CHOICES}:
        return text
    try:
        lv = int(legacy_level if raw in (None, "") else raw)
    except (TypeError, ValueError):
        lv = 1
    lv = max(1, min(9, lv))
    return str(lv)


def level_mode_max(mode: str) -> int:
    mode = normalize_level_mode(mode)
    if mode == "all":
        return 9
    if mode.startswith("upto_"):
        try:
            return max(1, min(9, int(mode.split("_", 1)[1])))
        except (TypeError, ValueError):
            return 1
    try:
        return max(1, min(9, int(mode)))
    except (TypeError, ValueError):
        return 1


def column_visible_at_level(spec: dict, level: int) -> bool:
    mode = normalize_level_mode(spec.get("level_mode"), spec.get("level") or 1)
    level = max(1, min(9, int(level or 1)))
    if mode == "all":
        return True
    if mode.startswith("upto_"):
        return level <= level_mode_max(mode)
    return level_mode_max(mode) == level


def column_is_aggregatable(spec: dict) -> bool:
    """Numeric / calc columns roll up with SUM at parent levels."""
    if str(spec.get("kind") or "field") == "calc":
        return True
    source = str(spec.get("source") or "")
    key = str(spec.get("key") or "")
    if source == "_calc":
        return True
    return not column_can_be_key(source, key)


def validate_report_level_keys(columns) -> list[str]:
    """Return Persian error messages when multi-level reports lack keys."""
    specs = normalize_columns(columns)
    if not specs:
        return []
    # Distinct exact levels that appear (upto/all count as spanning).
    levels: set[int] = set()
    for s in specs:
        mode = normalize_level_mode(s.get("level_mode"), s.get("level") or 1)
        if mode == "all":
            levels.update(range(1, 10))
        elif mode.startswith("upto_"):
            levels.update(range(1, level_mode_max(mode) + 1))
        else:
            levels.add(level_mode_max(mode))
    errors: list[str] = []
    # Single-level reports do not require keys.
    if len(levels) <= 1:
        for spec in specs:
            if spec.get("is_key") and not column_can_be_key(
                spec.get("source") or "", spec.get("key") or ""
            ):
                label = spec.get("label") or spec.get("key")
                errors.append(f"ستون «{label}» مقدار عددی است و نمی‌تواند کلید باشد.")
            if spec.get("kind") == "calc" and spec.get("is_key"):
                label = spec.get("label") or spec.get("key")
                errors.append(f"ستون محاسباتی «{label}» نمی‌تواند کلید باشد.")
        return errors
    for level in sorted(levels):
        level_cols = [s for s in specs if column_visible_at_level(s, level)]
        key_cols = [s for s in level_cols if s.get("is_key")]
        if not key_cols:
            errors.append(
                f"سطح {level}: برای گزارش چندسطحی حداقل یک ستون کلید مشخص کنید."
            )
            continue
        for spec in key_cols:
            if spec.get("kind") == "calc" or not column_can_be_key(
                spec.get("source") or "", spec.get("key") or ""
            ):
                label = spec.get("label") or spec.get("key")
                errors.append(
                    f"سطح {level}: ستون «{label}» مقدار عددی/محاسباتی است و نمی‌تواند کلید باشد."
                )
    return errors


def normalize_columns(raw) -> list[dict]:
    """Accept legacy string keys or structured dicts → list of dicts.

    Each column gets a stable ``uid`` so copies of the same ``key`` stay
    independent for editing/storage while sharing field type/options.
    Missing uids are assigned deterministically from position+key so values
    survive reloads before the report is re-saved.
    """
    from reports.formula import assign_missing_col_codes

    out = []
    if not raw:
        return out
    seen_uids: set[str] = set()
    for index, item in enumerate(raw):
        if isinstance(item, str):
            key = item
            uid = f"col{index}_{key}"
            if uid in seen_uids:
                uid = new_column_uid()
            seen_uids.add(uid)
            out.append({
                "key": key,
                "source": "",
                "level": 1,
                "level_mode": "1",
                "label": key,
                "uid": uid,
                "width": 0,
                "is_key": False,
                "kind": "field",
                "col_code": "",
                "number_format": "General",
                "formula": "",
                "sort_priority": 1,
                "sort_asc": True,
                "is_hidden": False,
                "cell_align": "right",
                "props_level_mode": "all",
            })
            continue
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "field").strip().lower()
        if kind not in {"field", "calc"}:
            kind = "field"
        key = str(item.get("key") or "").strip()
        if kind == "calc":
            key = key or "calc"
            source = "_calc"
        else:
            if not key:
                continue
            source = str(item.get("source") or "").strip()
        level_mode = normalize_level_mode(item.get("level_mode"), item.get("level") or 1)
        level = level_mode_max(level_mode)
        label = str(item.get("label") or key)[:120]
        if not label:
            if kind == "calc":
                label = "محاسبات"
            else:
                label = column_label_map(source).get(key, key) if source else key
        uid = str(item.get("uid") or "").strip()
        if not uid:
            uid = f"col{index}_{key}"
        if uid in seen_uids:
            uid = new_column_uid()
        seen_uids.add(uid)
        width = clamp_column_width(item.get("width"))
        is_key = bool(item.get("is_key"))
        if kind == "calc" or (is_key and not column_can_be_key(source, key)):
            is_key = False
        number_format = str(item.get("number_format") or "General").strip()[:40] or "General"
        formula = str(item.get("formula") or "").strip()[:500]
        if kind == "calc" and formula and not formula.startswith("="):
            formula = "=" + formula
        col_code = str(item.get("col_code") or "").strip().lower()[:8]
        sort_priority = clamp_sort_priority(item.get("sort_priority"))
        sort_asc = item.get("sort_asc", True)
        if isinstance(sort_asc, str):
            sort_asc = sort_asc.strip().lower() not in {"0", "false", "no", ""}
        else:
            sort_asc = bool(sort_asc)
        is_hidden = bool(item.get("is_hidden"))
        cell_align = normalize_cell_align(item.get("cell_align"))
        props_level_mode = normalize_level_mode(item.get("props_level_mode") or "all", 1)
        out.append({
            "key": key,
            "source": source,
            "level": level,
            "level_mode": level_mode,
            "label": label,
            "uid": uid,
            "width": width,
            "is_key": is_key,
            "kind": kind,
            "col_code": col_code,
            "number_format": number_format,
            "formula": formula if kind == "calc" else "",
            "sort_priority": sort_priority,
            "sort_asc": sort_asc,
            "is_hidden": is_hidden,
            "cell_align": cell_align,
            "props_level_mode": props_level_mode,
        })
    return assign_missing_col_codes(out)


def level_display_meta(columns, level: int = 1) -> list[dict]:
    """Width / key metadata for columns shown at a report level."""
    specs = normalize_columns(columns)
    level = max(1, min(9, int(level or 1)))
    level_specs = [s for s in specs if column_visible_at_level(s, level)]
    if not level_specs:
        available = sorted({level_mode_max(s.get("level_mode") or "1") for s in specs})
        pick = None
        for lv in available:
            if lv <= level:
                pick = lv
        if pick is not None:
            level_specs = [s for s in specs if column_visible_at_level(s, pick)]
    visible = [
        s for s in level_specs
        if not (s.get("is_hidden") and props_apply_at_level(s, level))
    ]
    return [
        {
            "key": storage_key(s),
            "data_key": data_key(s),
            "label": s.get("label") or s.get("key") or "",
            "width": int(s.get("width") or 0),
            "is_key": bool(s.get("is_key")),
            "col_code": s.get("col_code") or "",
            "number_format": s.get("number_format") or "General",
            "kind": s.get("kind") or "field",
            "formula": s.get("formula") or "",
            "cell_align": normalize_cell_align(s.get("cell_align")),
            "sort_priority": clamp_sort_priority(s.get("sort_priority")),
            "sort_asc": bool(s.get("sort_asc", True)),
            "is_hidden": False,
        }
        for s in visible
    ]


def columns_need_uid_persist(raw) -> bool:
    """True when stored columns are missing uid and should be rewritten."""
    if not raw:
        return False
    for item in raw:
        if isinstance(item, str):
            return True
        if isinstance(item, dict) and not str(item.get("uid") or "").strip():
            return True
    return False


def persist_column_uids(report) -> list[dict]:
    """Normalize columns and save uids back onto the report when missing."""
    cols = report.columns or []
    normalized = normalize_columns(cols)
    if columns_need_uid_persist(cols):
        report.columns = normalized
        report.save(update_fields=["columns", "updated_at"])
    return normalized


def _getter_map(source: str) -> dict:
    by_key = {}
    for k, label, getter in _columns_for_source(source):
        if is_flex_source(source) or is_excel_table_source(source) or source == "history":
            by_key[k] = (label, getter or _dict_get(k))
        else:
            by_key[k] = (label, getter)
    for k, label, getter in FILE_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    for k, label, getter in DATA_ENTRY_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    for k, label, getter in HISTORY_COLUMNS:
        by_key.setdefault(k, (label, getter))
    return by_key


def _queryset(data_source: str):
    if is_excel_table_source(data_source) or is_flex_source(data_source) or data_source == "history":
        return []
    if data_source == "pipe":
        return PipeProduction.objects.select_related(
            "unit", "line", "product", "deviation_reason"
        ).all()
    if data_source == "product":
        return Product.objects.select_related("subgroup").filter(is_active=True)
    if data_source == "data_entry":
        return []
    return ProductionDayEntry.objects.select_related(
        "program__item__product",
        "program__item__machine__unit",
        "deviation_reason",
    ).all()


def _flex_row_dicts(destination_id: str, level_id: str) -> list[dict]:
    from catalog.models import FlexibleDataset

    ds = FlexibleDataset.objects.filter(
        destination_id=destination_id, level_id=level_id
    ).first()
    if not ds:
        return []
    out: list[dict] = []
    for row in ds.rows.all()[:10000]:
        values = row.values if isinstance(row.values, dict) else {}
        cell = dict(values)
        cell["_row_id"] = row.pk
        out.append(cell)
    return out


def _excel_row_dicts(table) -> list[dict]:
    # Intentionally unused for report data — raw Excel must not feed reports.
    return []


def _resolve_specs(data_source: str, column_specs: list[dict]) -> list[dict]:
    by_key = _getter_map(data_source)
    for k, label, getter in FILE_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    for k, label, getter in DATA_ENTRY_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    resolved = []
    for spec in column_specs:
        if str(spec.get("kind") or "field") == "calc" or spec.get("source") == "_calc":
            resolved.append({
                **spec,
                "kind": "calc",
                "source": "_calc",
                "label": spec.get("label") or "محاسبات",
                "getter": None,
                "is_key": False,
            })
            continue
        key = spec["key"]
        src = spec.get("source") or ""
        if key not in by_key and src and src != data_source:
            alt = _getter_map(src)
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
        elif is_flex_source(src or data_source) and key:
            resolved.append({
                **spec,
                "label": spec.get("label") or key,
                "getter": _dict_get(key),
            })
    return resolved


def _apply_formulas(rows: list[dict], specs: list[dict]) -> None:
    """Evaluate calc columns in-place using col_code references."""
    from reports.formula import evaluate_formula, normalize_col_code

    calc_specs = [s for s in specs if str(s.get("kind") or "") == "calc"]
    if not calc_specs:
        return
    code_to_key = {
        normalize_col_code(s.get("col_code") or ""): storage_key(s)
        for s in specs
        if s.get("col_code")
    }
    for row in rows:
        values_by_code = {
            normalize_col_code(s.get("col_code") or ""): row.get(storage_key(s), "")
            for s in specs
            if s.get("col_code") and str(s.get("kind") or "field") != "calc"
        }
        for spec in calc_specs:
            sk = storage_key(spec)
            result = evaluate_formula(
                spec.get("formula") or "",
                values_by_code,
                row_list=rows,
                code_to_key=code_to_key,
            )
            row[sk] = result
            code = normalize_col_code(spec.get("col_code") or "")
            if code:
                values_by_code[code] = result


def _aggregate_group(rows: list[dict], level_cols: list[dict]) -> dict:
    """First-wins for identity/text; SUM for aggregatable numeric/calc columns."""
    from reports.formula import to_number

    if not rows:
        return {}
    base = dict(rows[0])
    for spec in level_cols:
        sk = storage_key(spec)
        if not column_is_aggregatable(spec):
            continue
        total = 0.0
        for r in rows:
            total += to_number(r.get(sk, 0))
        # Keep int when whole
        base[sk] = int(total) if float(total).is_integer() else total
    return base


def _lookup_entry_values(entry_data: dict | None, signature: str) -> dict:
    if not entry_data or not isinstance(entry_data, dict):
        return {}
    cells = entry_data.get("cells") or {}
    if isinstance(cells, dict) and signature in cells and isinstance(cells[signature], dict):
        return dict(cells[signature])
    if signature == "" or signature == "__empty__":
        values = entry_data.get("values") or {}
        if isinstance(values, dict):
            return dict(values)
    return {}


def row_sheet_number(row: dict | None) -> int:
    """Return 1-based sheet index stored on an entry row (default 1)."""
    if not isinstance(row, dict):
        return 1
    try:
        n = int(row.get("sheet") or 1)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(200, n))


def entry_sheet_count(entry_data: dict | None) -> int:
    """How many sheets exist for an editable report's entry data."""
    if not entry_data or not isinstance(entry_data, dict):
        return 1
    try:
        declared = int(entry_data.get("sheet_count") or 0)
    except (TypeError, ValueError):
        declared = 0
    max_from_rows = 1
    rows = entry_data.get("rows")
    if isinstance(rows, list):
        for row in rows:
            max_from_rows = max(max_from_rows, row_sheet_number(row))
    return max(1, declared, max_from_rows)


def _entry_rows_from_data(
    entry_data: dict | None,
    *,
    sheet: int | None = None,
) -> list[dict]:
    """Normalize stored entry_data into a list of row dicts.

    When ``sheet`` is set, only rows belonging to that sheet are returned.
    View/run_report pass ``sheet=None`` so all sheets appear stacked.
    """
    if not entry_data or not isinstance(entry_data, dict):
        return [{}]
    rows = entry_data.get("rows")
    if isinstance(rows, list) and rows:
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if sheet is not None and row_sheet_number(row) != int(sheet):
                continue
            out.append(dict(row))
        return out or ([{}] if sheet is None else [])
    stored = _lookup_entry_values(entry_data, "")
    if sheet is not None and sheet != 1:
        return []
    return [stored] if stored else [{}]


def _read_stored_value(stored: dict, spec: dict, *, legacy_used: set[str]) -> str:
    """Read value for a column instance; fall back to legacy data_key once."""
    sk = storage_key(spec)
    dk = data_key(spec)
    if sk in stored and stored.get(sk) not in (None,):
        return str(stored.get(sk) or "")
    # Legacy rows stored by semantic key only (before per-column uid).
    if dk and dk in stored and dk not in legacy_used:
        legacy_used.add(dk)
        return str(stored.get(dk) or "")
    return ""


def _build_records(data_source: str, specs: list[dict], entry_data: dict | None = None) -> list[dict]:
    entry_specs = [s for s in specs if is_data_entry_key(data_key(s), s.get("source") or "")]
    entry_sk = {storage_key(s) for s in entry_specs}
    non_entry_specs = [s for s in specs if storage_key(s) not in entry_sk]
    non_entry_keys = [storage_key(s) for s in non_entry_specs]

    if data_source == "data_entry":
        rows_out = []
        for stored in _entry_rows_from_data(entry_data):
            cell = {"_sheet": row_sheet_number(stored)}
            legacy_used: set[str] = set()
            for spec in specs:
                sk = storage_key(spec)
                dk = data_key(spec)
                if is_data_entry_key(dk, spec.get("source") or ""):
                    cell[sk] = _read_stored_value(stored, spec, legacy_used=legacy_used)
                else:
                    cell[sk] = ""
            rows_out.append(cell)
        return rows_out or [{"_sheet": 1}]

    if is_excel_table_source(data_source):
        # Reports must not read Excel files directly — only transferred destinations.
        return []

    if is_flex_source(data_source):
        parsed = parse_flex_source(data_source)
        records = _flex_row_dicts(parsed[0], parsed[1]) if parsed else []
        rows = []
        for record in records:
            cell = {}
            for spec in specs:
                sk = storage_key(spec)
                dk = data_key(spec)
                if is_data_entry_key(dk, spec.get("source") or ""):
                    cell[sk] = ""
                    continue
                try:
                    cell[sk] = spec["getter"](record) if spec.get("getter") else record.get(dk, "")
                except Exception:
                    cell[sk] = ""
            rows.append(cell)
        return rows

    if data_source == "history":
        from production.history import build_history_rows

        records = build_history_rows()
        rows = []
        for record in records:
            cell = {}
            for spec in specs:
                sk = storage_key(spec)
                dk = data_key(spec)
                if is_data_entry_key(dk, spec.get("source") or ""):
                    cell[sk] = ""
                    continue
                try:
                    cell[sk] = spec["getter"](record) if spec.get("getter") else ""
                except Exception:
                    cell[sk] = ""
            rows.append(cell)
        return rows

    rows = []
    for record in _queryset(data_source):
        cell = {}
        for spec in specs:
            sk = storage_key(spec)
            dk = data_key(spec)
            if is_data_entry_key(dk, spec.get("source") or ""):
                cell[sk] = ""
                continue
            try:
                cell[sk] = spec["getter"](record) if spec.get("getter") else ""
            except Exception:
                cell[sk] = ""
        if entry_specs:
            sig = row_signature(cell, non_entry_keys)
            stored = _lookup_entry_values(entry_data, sig)
            legacy_used = set()
            for spec in entry_specs:
                cell[storage_key(spec)] = _read_stored_value(
                    stored, spec, legacy_used=legacy_used
                )
        rows.append(cell)
    return rows


def run_report(
    data_source: str,
    columns,
    *,
    level: int = 1,
    filters: dict | None = None,
    entry_data: dict | None = None,
) -> tuple[list[str], list[list], list[dict], bool]:
    """Return headers, display rows, row filter payloads, and whether drill-down exists.

    Display columns are those visible at ``level`` (exact / upto / all).
    When deeper levels exist, rows are unique by key columns and numeric/calc
    columns are summed (Excel-like roll-up for «تا سطح N»).
    """
    from collections import OrderedDict

    from reports.formula import format_excel_number

    specs = normalize_columns(columns)
    for spec in specs:
        if not spec.get("label") or spec["label"] == spec["key"]:
            src = spec.get("source") or data_source
            if spec.get("kind") == "calc":
                spec["label"] = spec.get("label") or "محاسبات"
            else:
                spec["label"] = column_label_map(src).get(spec["key"], spec["key"])
        if not spec.get("source"):
            if spec.get("kind") == "calc":
                spec["source"] = "_calc"
            elif is_data_entry_key(spec["key"]):
                spec["source"] = "data_entry"
            else:
                spec["source"] = data_source

    if not specs:
        # Empty report definition must not invent system columns.
        return [], [], [], False

    resolved = _resolve_specs(data_source, specs)
    if not resolved:
        return [], [], [], False

    level = max(1, min(9, int(level or 1)))
    filters = filters or {}
    all_records = _build_records(data_source, resolved, entry_data=entry_data)
    _apply_formulas(all_records, resolved)

    filtered = []
    for row in all_records:
        ok = True
        for fk, fv in filters.items():
            if str(row.get(fk, "")) != str(fv):
                ok = False
                break
        if ok:
            filtered.append(row)

    level_cols = [s for s in resolved if column_visible_at_level(s, level)]
    if not level_cols:
        available_levels = sorted({level_mode_max(s.get("level_mode") or "1") for s in resolved})
        pick = None
        for lv in available_levels:
            if lv <= level:
                pick = lv
        if pick is None:
            level_cols = resolved
            level = available_levels[0] if available_levels else 1
        else:
            level_cols = [s for s in resolved if column_visible_at_level(s, pick)]
            level = pick

    deeper = any(level_mode_max(s.get("level_mode") or "1") > level for s in resolved)
    # Also deeper if any column uses upto/all spanning past current and other exact levels exist
    if not deeper:
        for s in resolved:
            mode = normalize_level_mode(s.get("level_mode"), s.get("level") or 1)
            if mode.startswith("upto_") or mode == "all":
                if level_mode_max(mode) > level:
                    deeper = True
                    break
            elif level_mode_max(mode) > level:
                deeper = True
                break

    headers = [s["label"] for s in level_cols]
    keys = [storage_key(s) for s in level_cols]
    key_specs = [s for s in level_cols if s.get("is_key")]
    identity_keys = [storage_key(s) for s in key_specs] if key_specs else list(keys)
    entry_keys_level = {
        storage_key(s)
        for s in level_cols
        if is_data_entry_key(data_key(s), s.get("source") or "")
    }
    non_entry_level = [k for k in keys if k not in entry_keys_level]

    # Group by identity for roll-up when deeper
    groups: OrderedDict[tuple, list[dict]] = OrderedDict()
    for row in filtered:
        identity_values = tuple(str(row.get(k, "")) for k in identity_keys)
        groups.setdefault(identity_values, []).append(row)

    display_rows: list[list] = []
    payloads: list[dict] = []
    row_i = 0
    for identity_values, group_rows in groups.items():
        if deeper:
            row = _aggregate_group(group_rows, level_cols)
            work_rows = [row]
        else:
            work_rows = group_rows
        for row in work_rows:
            cells = []
            for spec in level_cols:
                sk = storage_key(spec)
                raw = row.get(sk, "")
                fmt = spec.get("number_format") or "General"
                if (
                    str(spec.get("kind") or "") == "calc"
                    or column_is_aggregatable(spec)
                    or (fmt and fmt.lower() != "general")
                ):
                    cells.append(format_excel_number(raw, fmt) if fmt.lower() != "general" else raw)
                else:
                    cells.append(raw if fmt.lower() == "general" else format_excel_number(raw, fmt))
            display_rows.append(cells)
            payload = {k: row.get(k, "") for k in keys}
            key_counts: dict[str, int] = {}
            for spec in level_cols:
                dk = data_key(spec)
                key_counts[dk] = key_counts.get(dk, 0) + 1
            for spec in level_cols:
                dk = data_key(spec)
                sk = storage_key(spec)
                if dk and key_counts.get(dk, 0) == 1 and dk not in payload:
                    payload[dk] = row.get(sk, "")
            drill_keys = {k: row.get(k, "") for k in identity_keys}
            payload["_drill_keys"] = drill_keys
            if data_source == "data_entry" and not non_entry_level:
                payload["_entry_sig"] = f"__row_{row_i}__"
                payload["_row_index"] = row_i
            else:
                payload["_entry_sig"] = row_signature(row, non_entry_level)
            try:
                payload["_sheet"] = int(row.get("_sheet") or 1)
            except (TypeError, ValueError):
                payload["_sheet"] = 1
            payloads.append(payload)
            row_i += 1

    display_rows, payloads = _sort_report_rows(level_cols, display_rows, payloads)
    headers, display_rows = _filter_hidden_display(level_cols, level, headers, display_rows)

    return headers, display_rows, payloads, deeper


def _sort_value_key(raw, ascending: bool):
    """Build a comparable sort key; blanks last; numbers before text."""
    blank = raw is None or raw == ""
    if blank:
        primary = (1, 0, "")
    else:
        try:
            from reports.formula import to_number
            import math

            num = to_number(raw, default=float("nan"))
            if not math.isnan(num):
                primary = (0, 0, num)
            else:
                primary = (0, 1, str(raw))
        except Exception:
            primary = (0, 1, str(raw))
    if ascending:
        return primary
    # Invert for descending while keeping blanks last.
    if primary[0] == 1:
        return primary
    if primary[1] == 0:
        return (0, 0, -primary[2])
    return (0, 1, "".join(chr(0x10FFFF - ord(ch)) for ch in primary[2]))


def _sort_report_rows(
    level_cols: list[dict],
    display_rows: list[list],
    payloads: list[dict],
) -> tuple[list[list], list[dict]]:
    """Sort rows by column sort_priority (1 first). Same priority → rightmost column first (RTL)."""
    if not display_rows or not level_cols:
        return display_rows, payloads
    # RTL: index 0 is rightmost → earlier among equal priorities.
    order = sorted(
        range(len(level_cols)),
        key=lambda i: (
            clamp_sort_priority(level_cols[i].get("sort_priority")),
            i,
        ),
    )
    paired = list(zip(display_rows, payloads))

    def row_sort_key(item):
        row = item[0]
        keys = []
        for idx in order:
            asc = bool(level_cols[idx].get("sort_asc", True))
            val = row[idx] if idx < len(row) else ""
            keys.append(_sort_value_key(val, asc))
        return keys

    paired.sort(key=row_sort_key)
    if not paired:
        return [], []
    rows_out, payloads_out = zip(*paired)
    return list(rows_out), list(payloads_out)


def _filter_hidden_display(
    level_cols: list[dict],
    level: int,
    headers: list[str],
    display_rows: list[list],
) -> tuple[list[str], list[list]]:
    """Drop columns marked is_hidden when props apply at this level (still sorted/formula-ready)."""
    show_idx = [
        i
        for i, spec in enumerate(level_cols)
        if not (spec.get("is_hidden") and props_apply_at_level(spec, level))
    ]
    if len(show_idx) == len(level_cols):
        return headers, display_rows
    new_headers = [headers[i] for i in show_idx] if headers else [level_cols[i]["label"] for i in show_idx]
    new_rows = [[row[i] for i in show_idx] for row in display_rows]
    return new_headers, new_rows


# Backward-compatible thin wrapper used by older call sites
def run_report_flat(data_source: str, column_keys: list) -> tuple[list[str], list[list]]:
    specs = column_keys
    if column_keys and isinstance(column_keys[0], str):
        specs = [{"key": k, "source": data_source, "level": 1} for k in column_keys]
    headers, rows, _payloads, _deeper = run_report(data_source, specs, level=1)
    return headers, rows


def level_entry_meta(columns, level: int = 1) -> list[dict]:
    """Return editable meta for data-entry columns at a report level.

    ``key`` is the per-instance storage id (uid). ``data_key`` is the shared
    semantic type used for field widgets/options.
    """
    specs = normalize_columns(columns)
    level = max(1, min(9, int(level or 1)))
    options_cache: dict[str, list[dict]] = {}
    level_specs = [s for s in specs if column_visible_at_level(s, level)]
    out = []
    for idx, spec in enumerate(level_specs):
        dk = data_key(spec)
        if not is_data_entry_key(dk, spec.get("source") or ""):
            continue
        field_type = entry_field_type(dk)
        item = {
            "key": storage_key(spec),
            "data_key": dk,
            "label": spec.get("label") or column_label_map("data_entry").get(dk, dk),
            "type": field_type,
            "col_index": idx,
        }
        if field_type == "product_select":
            if dk not in options_cache:
                options_cache[dk] = product_options_for_key(dk)
            item["options"] = options_cache[dk]
        out.append(item)
    return out
