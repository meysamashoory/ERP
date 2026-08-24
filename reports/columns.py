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
        "hint": "پس از اتصال فایل، این ستون‌ها از اکسل خوانده می‌شوند.",
    },
]


def is_data_entry_key(key: str, source: str = "") -> bool:
    return key in DATA_ENTRY_KEYS or source == "data_entry"


def entry_field_type(key: str) -> str:
    return DATA_ENTRY_FIELD_TYPES.get(key, "text")


def row_signature(row: dict, keys: list[str]) -> str:
    return "|".join(f"{k}={row.get(k, '')}" for k in keys)


def column_label_map(source: str) -> dict[str, str]:
    mapping = {k: label for k, label, _ in COLUMNS_BY_SOURCE.get(source, [])}
    for k, label, _ in FILE_COLUMNS:
        mapping[k] = label
    for k, label, _ in DATA_ENTRY_COLUMNS:
        mapping[k] = label
    return mapping


def available_keys(source: str) -> set[str]:
    keys = {k for k, _, _ in COLUMNS_BY_SOURCE.get(source, [])}
    keys.update(k for k, _, _ in FILE_COLUMNS)
    keys.update(DATA_ENTRY_KEYS)
    return keys


def normalize_columns(raw) -> list[dict]:
    """Accept legacy string keys or structured dicts → list of dicts.

    Each column gets a stable ``uid`` so copies of the same ``key`` stay
    independent for editing/storage while sharing field type/options.
    Missing uids are assigned deterministically from position+key so values
    survive reloads before the report is re-saved.
    """
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
                "label": key,
                "uid": uid,
            })
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
        uid = str(item.get("uid") or "").strip()
        if not uid:
            uid = f"col{index}_{key}"
        if uid in seen_uids:
            uid = new_column_uid()
        seen_uids.add(uid)
        out.append({
            "key": key,
            "source": source,
            "level": level,
            "label": label,
            "uid": uid,
        })
    return out


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
    for k, label, getter in COLUMNS_BY_SOURCE.get(source, []):
        by_key[k] = (label, getter)
    for k, label, getter in FILE_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    for k, label, getter in DATA_ENTRY_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    return by_key


def _queryset(data_source: str):
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


def _resolve_specs(data_source: str, column_specs: list[dict]) -> list[dict]:
    by_key = _getter_map(data_source)
    for k, label, getter in FILE_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    for k, label, getter in DATA_ENTRY_COLUMNS:
        by_key.setdefault(k, (label, getter or (lambda _r: "")))
    resolved = []
    for spec in column_specs:
        key = spec["key"]
        if key not in by_key and spec.get("source") and spec["source"] != data_source:
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


def _entry_rows_from_data(entry_data: dict | None) -> list[dict]:
    """Normalize stored entry_data into a list of row dicts."""
    if not entry_data or not isinstance(entry_data, dict):
        return [{}]
    rows = entry_data.get("rows")
    if isinstance(rows, list) and rows:
        out = []
        for row in rows:
            if isinstance(row, dict):
                out.append(dict(row))
        return out or [{}]
    stored = _lookup_entry_values(entry_data, "")
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
            cell = {}
            legacy_used: set[str] = set()
            for spec in specs:
                sk = storage_key(spec)
                dk = data_key(spec)
                if is_data_entry_key(dk, spec.get("source") or ""):
                    cell[sk] = _read_stored_value(stored, spec, legacy_used=legacy_used)
                else:
                    cell[sk] = ""
            rows_out.append(cell)
        return rows_out or [{}]

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
            if is_data_entry_key(spec["key"]):
                spec["source"] = "data_entry"
            else:
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
    all_records = _build_records(data_source, resolved, entry_data=entry_data)

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
    keys = [storage_key(s) for s in level_cols]
    entry_keys_level = {
        storage_key(s)
        for s in level_cols
        if is_data_entry_key(data_key(s), s.get("source") or "")
    }
    non_entry_level = [k for k in keys if k not in entry_keys_level]

    display_rows: list[list] = []
    payloads: list[dict] = []
    seen = set()
    for row_i, row in enumerate(filtered):
        values = tuple(str(row.get(k, "")) for k in keys)
        if deeper:
            if values in seen:
                continue
            seen.add(values)
        display_rows.append([row.get(k, "") for k in keys])
        payload = {k: row.get(k, "") for k in keys}
        # Also expose semantic keys when unique (forms bound before uid).
        key_counts: dict[str, int] = {}
        for spec in level_cols:
            dk = data_key(spec)
            key_counts[dk] = key_counts.get(dk, 0) + 1
        for spec in level_cols:
            dk = data_key(spec)
            sk = storage_key(spec)
            if dk and key_counts.get(dk, 0) == 1 and dk not in payload:
                payload[dk] = row.get(sk, "")
        if data_source == "data_entry" and not non_entry_level:
            payload["_entry_sig"] = f"__row_{row_i}__"
            payload["_row_index"] = row_i
        else:
            payload["_entry_sig"] = row_signature(row, non_entry_level)
        payloads.append(payload)

    return headers, display_rows, payloads, deeper


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
    level = max(1, min(10, int(level or 1)))
    options_cache: dict[str, list[dict]] = {}
    level_specs = [s for s in specs if int(s.get("level") or 1) == level]
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
