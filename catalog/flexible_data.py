"""Dynamic destination tables: schema bootstrap, replace transfer, keyed update."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from django.db import transaction
from django.urls import reverse

from catalog.models import FlexibleDataset, FlexibleRow, SystemNamingKey

# Product-data tabs (raw by default — no columns until Excel bootstrap).
LEVEL_PRODUCTS = "products"
LEVEL_BOM = "bom"
LEVEL_BOM_MATERIALS = "bom_materials"
LEVEL_CONSUMABLES = "consumables"
LEVEL_SPECS = "specs"
LEVEL_INVENTORY = "inventory"
LEVEL_VOUCHERS = "vouchers"

DEFAULT_PRODUCT_TABS: list[dict[str, str]] = [
    {"id": LEVEL_PRODUCTS, "label": "مشخصات کالاها"},
    {"id": LEVEL_BOM, "label": "BOM قطعات مصرفی"},
    {"id": LEVEL_BOM_MATERIALS, "label": "BOM مواد مصرفی"},
    {"id": LEVEL_CONSUMABLES, "label": "مشخصات مواد مصرفی"},
    {"id": LEVEL_SPECS, "label": "مشخصات فنی دستگاه/قالب"},
    {"id": LEVEL_INVENTORY, "label": "موجودی محصول"},
    {"id": LEVEL_VOUCHERS, "label": "حواله‌ها"},
]

# Previous default labels — used to refresh uncustomized naming keys.
LEGACY_PRODUCT_TAB_LABELS = {
    LEVEL_PRODUCTS: {"محصولات", "مشخصات کالاها"},
    LEVEL_BOM: {"BOM", "BOM قطعات مصرفی", "ساختار BOM"},
    LEVEL_BOM_MATERIALS: {"BOM مواد مصرفی"},
    LEVEL_CONSUMABLES: {"مواد مصرفی", "مشخصات مواد مصرفی"},
    LEVEL_SPECS: {"مشخصات فنی", "مشخصات فنی دستگاه/قالب"},
    LEVEL_INVENTORY: {"موجودی محصول"},
    LEVEL_VOUCHERS: {"حواله‌ها", "لیست حواله‌ها"},
}

OBSOLETE_PRODUCT_LEVELS = {
    "product_info",
    "product_bom",
    "product_consumables",
    "info",
    "packaging",
    "voucher_list",
}

# Legacy destination id — kept for backward compat with naming keys
DESTINATION_VOUCHERS = "vouchers"
LEVEL_VOUCHERS_LIST = "voucher_list"

DEFAULT_VOUCHER_TABS: list[dict[str, str]] = [
    {"id": LEVEL_VOUCHERS_LIST, "label": "لیست حواله‌ها"},
]

# Labels that suggest identity keys after bootstrap (voucher-oriented).
SUGGESTED_KEY_LABELS = {
    "شماره حواله",
    "شماره‌ی حواله",
    "شماره حواله انبار",
    "کد کالا",
    "کد محصول",
    "کد جنس",
}


def slugify_column_key(label: str, *, index: int) -> str:
    text = (label or "").strip()
    if not text:
        return f"col_{index + 1}"
    # Keep Persian/Latin letters and digits; collapse others to underscore.
    cleaned = re.sub(r"[^\w\u0600-\u06ff]+", "_", text, flags=re.UNICODE)
    cleaned = cleaned.strip("_").lower()
    if not cleaned:
        return f"col_{index + 1}"
    if cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    return cleaned[:80]


def get_or_create_dataset(destination_id: str, level_id: str, *, title: str = "") -> FlexibleDataset:
    ds, _ = FlexibleDataset.objects.get_or_create(
        destination_id=destination_id,
        level_id=level_id,
        defaults={"title": title or "", "columns": []},
    )
    if title and not ds.title:
        ds.title = title
        ds.save(update_fields=["title"])
    return ds


def dataset_has_rows(destination_id: str, level_id: str) -> bool:
    ds = FlexibleDataset.objects.filter(
        destination_id=destination_id, level_id=level_id
    ).first()
    if not ds:
        return False
    return ds.rows.exists()


def dataset_has_schema(destination_id: str, level_id: str) -> bool:
    """True when destination already has columns (naming keys or stored schema)."""
    cols = load_schema_columns(destination_id, level_id)
    return bool(cols)


def naming_field_key(destination_id: str, level_id: str, column_key: str) -> str:
    return f"transfer.field.{destination_id}.{level_id}.{column_key}"


def naming_level_key(destination_id: str, level_id: str) -> str:
    return f"transfer.level.{destination_id}.{level_id}"


def load_schema_columns(destination_id: str, level_id: str) -> list[dict[str, Any]]:
    """Active columns from naming registry, falling back to FlexibleDataset.columns."""
    table_key = f"transfer.{destination_id}.{level_id}"
    prefix = f"transfer.field.{destination_id}.{level_id}."
    rows = list(
        SystemNamingKey.objects.filter(
            key__startswith=prefix,
            is_active=True,
        ).order_by("order", "id")
    )
    if rows:
        out: list[dict[str, Any]] = []
        for r in rows:
            col = (r.column_key or r.key[len(prefix) :]).strip()
            if not col:
                continue
            out.append(
                {
                    "key": col,
                    "label": r.label or col,
                    "type": "string",
                    "required": False,
                    "is_key": bool(r.is_key),
                }
            )
        return out

    ds = FlexibleDataset.objects.filter(
        destination_id=destination_id, level_id=level_id
    ).first()
    if not ds or not isinstance(ds.columns, list):
        return []
    out = []
    for c in ds.columns:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").strip()
        if not key:
            continue
        out.append(
            {
                "key": key,
                "label": str(c.get("label") or key),
                "type": str(c.get("type") or "string"),
                "required": False,
                "is_key": bool(c.get("is_key")),
            }
        )
    return out


def sync_columns_to_naming(
    destination_id: str,
    level_id: str,
    columns: list[dict[str, Any]],
    *,
    dest_label: str = "",
    level_label: str = "",
) -> None:
    """Upsert SystemNamingKey rows for dynamic columns (preserves is_key / label edits)."""
    table_key = f"transfer.{destination_id}.{level_id}"
    dest_label = dest_label or destination_id
    level_label = level_label or level_id
    for i, col in enumerate(columns, start=1):
        key = str(col.get("key") or "").strip()
        if not key:
            continue
        label = str(col.get("label") or key)[:200]
        nk = naming_field_key(destination_id, level_id, key)
        row = SystemNamingKey.objects.filter(key=nk).first()
        if row is None:
            SystemNamingKey.objects.create(
                key=nk,
                label=label,
                default_label=label,
                address=(
                    f"دیالوگ انتقال داده ← {dest_label} ← {level_label} ← فیلد «{label}»"
                ),
                category=SystemNamingKey.Category.COLUMN,
                section_key="transfer_dialog_labels",
                table_key=table_key,
                column_key=key,
                order=i,
                is_active=True,
                is_custom=True,
                is_key=bool(col.get("is_key")),
            )
        else:
            # Keep user label/is_key; refresh order/address defaults if unused.
            updates = []
            if row.order != i:
                row.order = i
                updates.append("order")
            if not row.column_key:
                row.column_key = key
                updates.append("column_key")
            if updates:
                row.save(update_fields=updates)


def bootstrap_schema_from_headers(
    destination_id: str,
    level_id: str,
    headers: list[Any],
    *,
    selected_indexes: list[int] | None = None,
    dest_label: str = "",
    level_label: str = "",
) -> list[dict[str, Any]]:
    """Create schema from Excel headers (all or selected indexes)."""
    cols: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    indexes = (
        list(selected_indexes)
        if selected_indexes is not None
        else list(range(len(headers)))
    )
    for order_i, idx in enumerate(indexes):
        if idx < 0 or idx >= len(headers):
            continue
        label = str(headers[idx] if headers[idx] is not None else "").strip() or f"ستون {idx + 1}"
        base = slugify_column_key(label, index=idx)
        key = base
        n = 2
        while key in used_keys:
            key = f"{base}_{n}"
            n += 1
        used_keys.add(key)
        is_key = label.strip() in SUGGESTED_KEY_LABELS
        cols.append(
            {
                "key": key,
                "label": label[:200],
                "type": "string",
                "required": False,
                "is_key": is_key,
                "order": order_i + 1,
            }
        )

    ds = get_or_create_dataset(destination_id, level_id, title=level_label)
    ds.columns = cols
    if level_label:
        ds.title = level_label
    ds.save(update_fields=["columns", "title", "updated_at"])
    sync_columns_to_naming(
        destination_id,
        level_id,
        cols,
        dest_label=dest_label,
        level_label=level_label,
    )
    return cols


def add_columns_from_headers(
    destination_id: str,
    level_id: str,
    headers: list[Any],
    indexes: list[int],
    *,
    dest_label: str = "",
    level_label: str = "",
) -> list[dict[str, Any]]:
    """Append new columns (from extra Excel headers) to an existing schema."""
    existing = load_schema_columns(destination_id, level_id)
    used = {c["key"] for c in existing}
    new_cols: list[dict[str, Any]] = []
    for idx in indexes:
        if idx < 0 or idx >= len(headers):
            continue
        label = str(headers[idx] if headers[idx] is not None else "").strip() or f"ستون {idx + 1}"
        base = slugify_column_key(label, index=idx)
        key = base
        n = 2
        while key in used:
            key = f"{base}_{n}"
            n += 1
        used.add(key)
        col = {
            "key": key,
            "label": label[:200],
            "type": "string",
            "required": False,
            "is_key": label.strip() in SUGGESTED_KEY_LABELS,
            "order": len(existing) + len(new_cols) + 1,
        }
        new_cols.append(col)
        existing.append(col)

    ds = get_or_create_dataset(destination_id, level_id, title=level_label)
    ds.columns = existing
    ds.save(update_fields=["columns", "updated_at"])
    sync_columns_to_naming(
        destination_id,
        level_id,
        existing,
        dest_label=dest_label,
        level_label=level_label,
    )
    return new_cols


def make_identity_key(values: dict[str, Any], key_fields: list[str]) -> str:
    parts = []
    for k in key_fields:
        parts.append(str(values.get(k) or "").strip())
    raw = "\u001f".join(parts)
    if not any(parts):
        return ""
    if len(raw) <= 480:
        return raw
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@transaction.atomic
def replace_all_rows(
    destination_id: str,
    level_id: str,
    rows_values: list[dict[str, Any]],
    *,
    key_fields: list[str] | None = None,
) -> int:
    """Wipe destination rows and insert new ones (transfer mode)."""
    ds = get_or_create_dataset(destination_id, level_id)
    ds.rows.all().delete()
    key_fields = key_fields or [c["key"] for c in load_schema_columns(destination_id, level_id) if c.get("is_key")]
    bulk: list[FlexibleRow] = []
    for i, values in enumerate(rows_values):
        if not isinstance(values, dict):
            continue
        if not any(str(v).strip() for v in values.values() if v is not None):
            continue
        bulk.append(
            FlexibleRow(
                dataset=ds,
                values=values,
                identity_key=make_identity_key(values, key_fields),
                order=i,
            )
        )
    if bulk:
        FlexibleRow.objects.bulk_create(bulk, batch_size=500)
    return len(bulk)


@transaction.atomic
def keyed_update_rows(
    destination_id: str,
    level_id: str,
    rows_values: list[dict[str, Any]],
    *,
    key_fields: list[str],
) -> tuple[int, int, int]:
    """Update/insert by identity keys; delete old keys missing from the new file.

    Returns (updated_or_inserted, deleted, skipped).
    """
    if not key_fields:
        raise ValueError("هیچ ستون کلیدی برای این مقصد تعریف نشده است.")

    ds = get_or_create_dataset(destination_id, level_id)
    schema_keys = {c["key"] for c in load_schema_columns(destination_id, level_id)}
    existing = {r.identity_key: r for r in ds.rows.all() if r.identity_key}
    seen: set[str] = set()
    transferred = 0
    skipped = 0

    for i, values in enumerate(rows_values):
        if not isinstance(values, dict):
            skipped += 1
            continue
        # Only keep known schema columns (no new columns in update mode).
        filtered = {k: v for k, v in values.items() if k in schema_keys}
        ident = make_identity_key(filtered, key_fields)
        if not ident:
            skipped += 1
            continue
        seen.add(ident)
        row = existing.get(ident)
        if row is None:
            FlexibleRow.objects.create(
                dataset=ds,
                values=filtered,
                identity_key=ident,
                order=i,
            )
        else:
            # Replace values for mapped fields; keep unmapped old cells if absent in payload.
            merged = dict(row.values or {})
            merged.update(filtered)
            row.values = merged
            row.identity_key = ident
            row.order = i
            row.save(update_fields=["values", "identity_key", "order", "updated_at"])
        transferred += 1

    deleted = 0
    for ident, row in existing.items():
        if ident not in seen:
            row.delete()
            deleted += 1
    return transferred, deleted, skipped


def sync_default_product_tab_labels() -> None:
    """Refresh uncustomized naming-key labels when default tab titles change."""
    prefix = "transfer.level.product_data."
    defaults = {t["id"]: t["label"] for t in DEFAULT_PRODUCT_TABS}
    rows = SystemNamingKey.objects.filter(key__startswith=prefix)
    for r in rows:
        level_id = r.key[len(prefix) :].strip()
        if level_id not in defaults:
            continue
        new_label = defaults[level_id]
        legacy = LEGACY_PRODUCT_TAB_LABELS.get(level_id, set())
        updates: list[str] = []
        if (r.default_label or "") != new_label:
            r.default_label = new_label
            updates.append("default_label")
        # Only rewrite label if it still matches a known stock/legacy title.
        if (r.label or "") in legacy or (r.label or "") == (r.default_label or ""):
            if (r.label or "") != new_label:
                r.label = new_label
                updates.append("label")
        if updates:
            updates.append("updated_at")
            r.save(update_fields=updates)


def list_tab_levels(
    destination_id: str,
    defaults: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Active levels/tabs for a dynamic destination (defaults + custom naming keys)."""
    if destination_id == "product_data":
        sync_default_product_tab_labels()

    prefix = f"transfer.level.{destination_id}."
    by_id: dict[str, dict[str, Any]] = {}
    for d in defaults:
        by_id[d["id"]] = {"id": d["id"], "label": d["label"]}

    rows = list(
        SystemNamingKey.objects.filter(key__startswith=prefix).order_by("order", "id")
    )
    for r in rows:
        level_id = r.key[len(prefix) :].strip() if r.key.startswith(prefix) else ""
        if not level_id:
            continue
        if destination_id == "product_data" and level_id in OBSOLETE_PRODUCT_LEVELS:
            if r.is_active:
                r.is_active = False
                r.save(update_fields=["is_active", "updated_at"])
            continue
        if not r.is_active:
            # Allow hiding a default tab via naming registry
            if level_id in by_id:
                by_id.pop(level_id, None)
            continue
        by_id[level_id] = {"id": level_id, "label": r.label or level_id}

    # Preserve default order, then append custom tabs
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in defaults:
        if d["id"] in by_id:
            ordered.append(by_id[d["id"]])
            seen.add(d["id"])
    for lid, meta in by_id.items():
        if lid not in seen:
            ordered.append(meta)
    return ordered


def hub_table_payload(destination_id: str, level_id: str) -> dict[str, Any]:
    columns = load_schema_columns(destination_id, level_id)
    ds = FlexibleDataset.objects.filter(
        destination_id=destination_id, level_id=level_id
    ).first()
    rows_out: list[dict[str, Any]] = []
    if ds:
        for r in ds.rows.all()[:5000]:
            rows_out.append({"id": r.pk, **(r.values or {})})
    return {
        "columns": columns,
        "rows": rows_out,
        "has_schema": bool(columns),
        "row_count": len(rows_out),
    }


def redirect_for_destination(destination_id: str, level_id: str = "") -> str:
    url = reverse("product_data")
    if level_id:
        return f"{url}?tab={level_id}"
    return url
