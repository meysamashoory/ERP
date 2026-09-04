"""Import BOM sample CSVs into product-data flexible tabs.

File roles (Bom Version samples):

1. Parts BOM (has ``کد محصول`` + ``کد كالا مصرفی``)
   → tab ``bom`` / «BOM قطعات مصرفی»
   Parent = finished saleable product; child = assembly component.

2. Materials BOM (has ``کد مواد مصرفی`` + ``کد كالا مصرفی``, no ``کد محصول``)
   → tab ``bom_materials`` / «BOM مواد مصرفی»
   Parent = component/part being molded; child = raw material.

3. Material master rows extracted from materials BOM
   → tab ``consumables`` / «مشخصات مواد مصرفی»

4. Version changelog / recipe-change sheets are metadata (not loaded into BOM tabs).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.db import transaction

from catalog.flexible_data import (
    LEVEL_BOM,
    LEVEL_BOM_MATERIALS,
    LEVEL_CONSUMABLES,
    bootstrap_schema_from_headers,
    load_schema_columns,
    replace_all_rows,
)
from catalog.models import Product, ProductBomLine
from catalog.product_data import ensure_default_subgroup


DESTINATION_PRODUCT_DATA = "product_data"

FILE_PARTS_BOM = "parts_bom"
FILE_MATERIALS_BOM = "materials_bom"
FILE_VERSION_LOG = "version_log"
FILE_RECIPE_CHANGE = "recipe_change"
FILE_UNKNOWN = "unknown"


@dataclass
class BomImportStats:
    file_kind: str
    level_id: str
    headers: list[str]
    rows_loaded: int
    products_ensured: int = 0
    bom_lines_synced: int = 0
    notes: str = ""


def _norm_header(h: str) -> str:
    return " ".join(str(h or "").replace("\u200c", "").split()).strip()


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if text.count(";") > text.count(",") else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delim))
    if not rows:
        return [], []
    headers = [_norm_header(h) for h in rows[0]]
    body: list[list[str]] = []
    for row in rows[1:]:
        if not any(str(c).strip() for c in row):
            continue
        # pad / trim to header width
        padded = [(row[i] if i < len(row) else "") for i in range(len(headers))]
        body.append([str(c).strip() for c in padded])
    return headers, body


def classify_bom_csv(headers: list[str]) -> str:
    hs = set(headers)
    if "Bom Version x.x.x.x" in hs or any(h.startswith("Bom Version") for h in hs):
        return FILE_VERSION_LOG
    if "کد کالا قدیم" in hs and "کد کالا جدید" in hs:
        return FILE_RECIPE_CHANGE
    if "کد محصول" in hs and (
        "کد كالا مصرفی" in hs or "کد کالا مصرفی" in hs
    ):
        return FILE_PARTS_BOM
    if "کد مواد مصرفی" in hs and (
        "کد كالا مصرفی" in hs or "کد کالا مصرفی" in hs
    ):
        return FILE_MATERIALS_BOM
    return FILE_UNKNOWN


def _slug_keys(headers: list[str]) -> list[str]:
    """Mirror flexible_data.slugify_column_key order used at bootstrap."""
    from catalog.flexible_data import slugify_column_key

    used: set[str] = set()
    keys: list[str] = []
    for i, label in enumerate(headers):
        base = slugify_column_key(label, index=i)
        key = base
        n = 2
        while key in used:
            key = f"{base}_{n}"
            n += 1
        used.add(key)
        keys.append(key)
    return keys


def _rows_as_dicts(headers: list[str], body: list[list[str]]) -> list[dict[str, Any]]:
    keys = _slug_keys(headers)
    out: list[dict[str, Any]] = []
    for row in body:
        values = {keys[i]: row[i] for i in range(len(keys))}
        if any(str(v).strip() for v in values.values()):
            out.append(values)
    return out


def _mark_key_columns(destination_id: str, level_id: str, labels: set[str]) -> None:
    from catalog.models import FlexibleDataset

    ds = FlexibleDataset.objects.filter(
        destination_id=destination_id, level_id=level_id
    ).first()
    if not ds:
        return
    cols = list(ds.columns or [])
    changed = False
    for c in cols:
        want = _norm_header(str(c.get("label") or "")) in labels
        if bool(c.get("is_key")) != want:
            c["is_key"] = want
            changed = True
    if changed:
        ds.columns = cols
        ds.save(update_fields=["columns", "updated_at"])


def _dec(val: Any, default: Decimal | None = None) -> Decimal | None:
    try:
        text = str(val or "").replace(",", "").strip()
        if not text:
            return default
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return default


def _ensure_product(
    code: str,
    name: str,
    *,
    cycle: Any = None,
    per_carton: Any = None,
) -> Product | None:
    code = str(code or "").strip()
    if not code:
        return None
    name = str(name or "").strip() or code
    product = Product.objects.filter(code=code).first()
    subgroup = ensure_default_subgroup()
    if product is None:
        product = Product.objects.create(
            code=code,
            name=name,
            subgroup=subgroup,
            is_active=True,
        )
    elif name and product.name != name:
        product.name = name
        product.save(update_fields=["name"])
    updates: dict[str, Any] = {}
    if cycle is not None:
        cyc = _dec(cycle)
        if cyc is not None:
            updates["last_cycle"] = int(cyc)
    if per_carton is not None:
        pc = _dec(per_carton)
        if pc is not None and pc > 0:
            updates["per_carton"] = int(pc)
    if updates:
        for k, v in updates.items():
            setattr(product, k, v)
        product.save(update_fields=list(updates.keys()))
    return product


def _sync_parts_bom_lines(headers: list[str], body: list[list[str]]) -> tuple[int, int]:
    """Create/update Product + ProductBomLine from parts BOM rows."""
    idx = {h: i for i, h in enumerate(headers)}
    code_i = idx.get("کد محصول")
    name_i = idx.get("نام محصول")
    cycle_i = idx.get("سیکل محصول")
    carton_i = idx.get("ضریب کل")
    comp_code_i = idx.get("کد كالا مصرفی", idx.get("کد کالا مصرفی"))
    comp_name_i = idx.get("شرح كالا مصرفی", idx.get("شرح کالا مصرفی"))
    qty_i = idx.get("BOM(یک عدد)")
    unit_i = idx.get("واحد BOM")
    if code_i is None or comp_code_i is None:
        return 0, 0

    products_ensured = 0
    lines = 0
    seen_products: set[str] = set()
    for row in body:
        pcode = row[code_i]
        if pcode not in seen_products:
            _ensure_product(
                pcode,
                row[name_i] if name_i is not None else pcode,
                cycle=row[cycle_i] if cycle_i is not None else None,
                per_carton=row[carton_i] if carton_i is not None else None,
            )
            seen_products.add(pcode)
            products_ensured += 1
        parent = Product.objects.filter(code=pcode).first()
        if not parent:
            continue
        ccode = row[comp_code_i]
        cname = row[comp_name_i] if comp_name_i is not None else ccode
        qty = _dec(row[qty_i] if qty_i is not None else "1", Decimal("1")) or Decimal("1")
        unit = (row[unit_i] if unit_i is not None else "عدد") or "عدد"
        line = ProductBomLine.objects.filter(parent=parent, component_code=ccode).first()
        if line:
            line.component_name = cname or ccode
            line.quantity = qty
            line.unit = unit
            line.save()
        else:
            ProductBomLine.objects.create(
                parent=parent,
                component_code=ccode,
                component_name=cname or ccode,
                quantity=qty,
                unit=unit,
            )
        lines += 1
    return products_ensured, lines


@transaction.atomic
def import_bom_csv(path: Path | str, *, sync_relational: bool = True) -> BomImportStats:
    """Load one BOM-related CSV into the matching product-data tab."""
    path = Path(path)
    headers, body = _read_csv(path)
    if not headers:
        raise ValueError(f"فایل خالی است: {path.name}")

    kind = classify_bom_csv(headers)
    if kind == FILE_VERSION_LOG:
        return BomImportStats(
            file_kind=kind,
            level_id="",
            headers=headers,
            rows_loaded=0,
            notes="فایل رجیستر نسخه BOM — در تب‌های BOM بارگذاری نمی‌شود.",
        )
    if kind == FILE_RECIPE_CHANGE:
        return BomImportStats(
            file_kind=kind,
            level_id="",
            headers=headers,
            rows_loaded=0,
            notes="فایل تاریخچه تغییر ترکیب مواد — در تب‌های BOM بارگذاری نمی‌شود.",
        )
    if kind == FILE_UNKNOWN:
        raise ValueError(f"نوع فایل BOM شناخته نشد: {path.name}")

    if kind == FILE_PARTS_BOM:
        level_id = LEVEL_BOM
        level_label = "BOM قطعات مصرفی"
        key_labels = {"کد محصول", "کد كالا مصرفی", "کد کالا مصرفی"}
    elif kind == FILE_MATERIALS_BOM:
        level_id = LEVEL_BOM_MATERIALS
        level_label = "BOM مواد مصرفی"
        key_labels = {"کد كالا مصرفی", "کد کالا مصرفی", "کد مواد مصرفی"}
    else:
        raise ValueError(kind)

    indexes = list(range(len(headers)))
    bootstrap_schema_from_headers(
        DESTINATION_PRODUCT_DATA,
        level_id,
        headers,
        selected_indexes=indexes,
        dest_label="دیتای محصولات",
        level_label=level_label,
    )
    _mark_key_columns(DESTINATION_PRODUCT_DATA, level_id, key_labels)

    row_dicts = _rows_as_dicts(headers, body)
    key_fields = [
        c["key"]
        for c in load_schema_columns(DESTINATION_PRODUCT_DATA, level_id)
        if c.get("is_key")
    ]
    loaded = replace_all_rows(
        DESTINATION_PRODUCT_DATA,
        level_id,
        row_dicts,
        key_fields=key_fields,
    )

    products_ensured = 0
    bom_lines = 0
    if sync_relational and kind == FILE_PARTS_BOM:
        products_ensured, bom_lines = _sync_parts_bom_lines(headers, body)

    # Materials master → consumables tab (unique by material code)
    notes = ""
    if kind == FILE_MATERIALS_BOM:
        notes = _import_material_master(headers, body)

    return BomImportStats(
        file_kind=kind,
        level_id=level_id,
        headers=headers,
        rows_loaded=loaded,
        products_ensured=products_ensured,
        bom_lines_synced=bom_lines,
        notes=notes,
    )


def _import_material_master(headers: list[str], body: list[list[str]]) -> str:
    idx = {h: i for i, h in enumerate(headers)}
    code_i = idx.get("کد مواد مصرفی")
    name_i = idx.get("مشخصات مواد مصرفی")
    gcode_i = idx.get("کد گروه مواد")
    gname_i = idx.get("گروه مواد مصرفی")
    unit_i = idx.get("واحد وزن مواد")
    if code_i is None:
        return ""

    master_headers = [
        "کد مواد مصرفی",
        "مشخصات مواد مصرفی",
        "کد گروه مواد",
        "گروه مواد مصرفی",
        "واحد وزن مواد",
    ]
    seen: dict[str, list[str]] = {}
    for row in body:
        code = row[code_i]
        if not code or code in seen:
            continue
        seen[code] = [
            code,
            row[name_i] if name_i is not None else "",
            row[gcode_i] if gcode_i is not None else "",
            row[gname_i] if gname_i is not None else "",
            row[unit_i] if unit_i is not None else "گرم",
        ]

    bootstrap_schema_from_headers(
        DESTINATION_PRODUCT_DATA,
        LEVEL_CONSUMABLES,
        master_headers,
        selected_indexes=list(range(len(master_headers))),
        dest_label="دیتای محصولات",
        level_label="مشخصات مواد مصرفی",
    )
    _mark_key_columns(DESTINATION_PRODUCT_DATA, LEVEL_CONSUMABLES, {"کد مواد مصرفی"})
    row_dicts = _rows_as_dicts(master_headers, list(seen.values()))
    key_fields = [
        c["key"]
        for c in load_schema_columns(DESTINATION_PRODUCT_DATA, LEVEL_CONSUMABLES)
        if c.get("is_key")
    ]
    n = replace_all_rows(
        DESTINATION_PRODUCT_DATA,
        LEVEL_CONSUMABLES,
        row_dicts,
        key_fields=key_fields,
    )
    return f"مشخصات مواد مصرفی: {n} ماده یکتا"


def import_bom_paths(paths: list[Path | str], *, sync_relational: bool = True) -> list[BomImportStats]:
    """Import many CSVs; order materials/parts independently."""
    results: list[BomImportStats] = []
    for p in paths:
        results.append(import_bom_csv(p, sync_relational=sync_relational))
    return results
