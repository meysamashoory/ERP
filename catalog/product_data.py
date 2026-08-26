"""Product data hub tabs, row payloads, and save helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from core.natsort import natural_key

from .models import (
    CountingUnit,
    Product,
    ProductBomLine,
    ProductConsumable,
    ProductGroup,
    ProductKind,
    ProductSubGroup,
)

TAB_INFO = "info"
TAB_BOM = "bom"
TAB_CONSUMABLES = "consumables"
TAB_PACKAGING = "packaging"
TAB_SPECS = "specs"

PRODUCT_DATA_TABS: list[dict[str, Any]] = [
    {"id": TAB_INFO, "label": "اطلاعات محصول", "editable": True},
    {"id": TAB_BOM, "label": "ساختار BOM", "editable": True},
    {"id": TAB_CONSUMABLES, "label": "مواد مصرفی", "editable": True},
    {"id": TAB_PACKAGING, "label": "بسته‌بندی", "editable": False, "coming_soon": True},
    {"id": TAB_SPECS, "label": "مشخصات فنی", "editable": False, "coming_soon": True},
]


def resolve_tab(tab_id: str | None) -> str:
    ids = {t["id"] for t in PRODUCT_DATA_TABS}
    if tab_id in ids:
        return tab_id or TAB_INFO
    return TAB_INFO


def ensure_default_subgroup() -> ProductSubGroup:
    group, _ = ProductGroup.objects.get_or_create(
        name="عمومی",
        defaults={"kind": ProductKind.FITTING, "order": 999},
    )
    subgroup, _ = ProductSubGroup.objects.get_or_create(
        group=group,
        name="عمومی",
        defaults={"order": 0},
    )
    return subgroup


def resolve_subgroup(*, group_name: str = "", subgroup_name: str = "") -> ProductSubGroup:
    group_name = (group_name or "").strip()
    subgroup_name = (subgroup_name or "").strip()
    if subgroup_name:
        qs = ProductSubGroup.objects.select_related("group")
        if group_name:
            found = qs.filter(name=subgroup_name, group__name=group_name).first()
            if found:
                return found
        found = qs.filter(name=subgroup_name).first()
        if found:
            return found
        group = None
        if group_name:
            group, _ = ProductGroup.objects.get_or_create(
                name=group_name,
                defaults={"kind": ProductKind.FITTING, "order": 100},
            )
        else:
            group, _ = ProductGroup.objects.get_or_create(
                name="عمومی",
                defaults={"kind": ProductKind.FITTING, "order": 999},
            )
        return ProductSubGroup.objects.create(group=group, name=subgroup_name, order=0)
    if group_name:
        group, _ = ProductGroup.objects.get_or_create(
            name=group_name,
            defaults={"kind": ProductKind.FITTING, "order": 100},
        )
        sub, _ = ProductSubGroup.objects.get_or_create(
            group=group, name="عمومی", defaults={"order": 0}
        )
        return sub
    return ensure_default_subgroup()


def _dec(value, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").replace("٬", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return default


def _int(value, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).replace(",", "").replace("٬", "").strip()))
    except (TypeError, ValueError):
        return default


def _bool(value, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "بله", "آری", "true", "✓"}:
        return True
    if text in {"0", "false", "no", "n", "خیر", "نه"}:
        return False
    return default


def product_info_rows() -> list[dict[str, Any]]:
    products = list(
        Product.objects.select_related("subgroup__group").filter(is_active=True)
    )
    products.sort(key=lambda p: (natural_key(p.code), p.id))
    rows = []
    for p in products:
        rows.append(
            {
                "id": p.pk,
                "code": p.code,
                "name": p.name,
                "group_name": p.subgroup.group.name if p.subgroup_id else "",
                "subgroup_name": p.subgroup.name if p.subgroup_id else "",
                "counting_unit": p.counting_unit,
                "unit_weight_grams": str(p.unit_weight_grams),
                "per_carton": p.per_carton if p.per_carton is not None else "",
                "per_bag": p.per_bag if p.per_bag is not None else "",
                "depot_ceiling": p.depot_ceiling if p.depot_ceiling is not None else "",
                "main_cavities": p.main_cavities if p.main_cavities is not None else "",
                "last_cycle": p.last_cycle if p.last_cycle is not None else "",
                "stock_finished": p.stock_finished,
                "stock_unassembled": p.stock_unassembled,
                "reorder_level": p.reorder_level,
                "needs_assembly": p.needs_assembly,
                "needs_machining": p.needs_machining,
                "needs_facing": p.needs_facing,
            }
        )
    return rows


def bom_rows() -> list[dict[str, Any]]:
    lines = list(
        ProductBomLine.objects.select_related("parent").all()
    )
    lines.sort(
        key=lambda L: (natural_key(L.parent.code), L.order, L.id)
    )
    return [
        {
            "id": L.pk,
            "parent_code": L.parent.code,
            "parent_name": L.parent.name,
            "component_code": L.component_code,
            "component_name": L.component_name,
            "quantity": str(L.quantity),
            "unit": L.unit,
            "notes": L.notes,
            "order": L.order,
        }
        for L in lines
    ]


def consumable_rows() -> list[dict[str, Any]]:
    rows = list(ProductConsumable.objects.select_related("product").all())
    rows.sort(key=lambda c: (natural_key(c.product.code), c.order, c.id))
    return [
        {
            "id": c.pk,
            "product_code": c.product.code,
            "product_name": c.product.name,
            "material_code": c.material_code,
            "material_name": c.material_name,
            "quantity_per_unit": str(c.quantity_per_unit),
            "unit": c.unit,
            "notes": c.notes,
            "order": c.order,
        }
        for c in rows
    ]


@transaction.atomic
def upsert_product_from_values(values: dict[str, Any]) -> Product:
    code = str(values.get("code") or "").strip()
    if not code:
        raise ValueError("کد کالا الزامی است.")
    name = str(values.get("name") or "").strip() or code
    subgroup = resolve_subgroup(
        group_name=str(values.get("group_name") or ""),
        subgroup_name=str(values.get("subgroup_name") or ""),
    )
    unit = str(values.get("counting_unit") or CountingUnit.COUNT).strip()
    valid_units = {c.value for c in CountingUnit}
    if unit not in valid_units:
        # accept Persian labels
        label_map = {c.label: c.value for c in CountingUnit}
        unit = label_map.get(unit, CountingUnit.COUNT)

    defaults = {
        "name": name,
        "subgroup": subgroup,
        "counting_unit": unit,
        "unit_weight_grams": _dec(values.get("unit_weight_grams"), Decimal("0")) or Decimal("0"),
        "per_carton": _int(values.get("per_carton")),
        "per_bag": _int(values.get("per_bag")),
        "depot_ceiling": _int(values.get("depot_ceiling")),
        "main_cavities": _int(values.get("main_cavities")),
        "last_cycle": _int(values.get("last_cycle")),
        "stock_finished": _int(values.get("stock_finished"), 0) or 0,
        "stock_unassembled": _int(values.get("stock_unassembled"), 0) or 0,
        "reorder_level": _int(values.get("reorder_level"), 0) or 0,
        "needs_assembly": _bool(values.get("needs_assembly")),
        "needs_machining": _bool(values.get("needs_machining")),
        "needs_facing": _bool(values.get("needs_facing")),
        "is_active": True,
    }
    product, _ = Product.objects.update_or_create(code=code, defaults=defaults)
    return product


@transaction.atomic
def upsert_bom_from_values(values: dict[str, Any]) -> ProductBomLine:
    parent_code = str(values.get("parent_code") or "").strip()
    if not parent_code:
        raise ValueError("کد محصول والد الزامی است.")
    parent = Product.objects.filter(code=parent_code).first()
    if not parent:
        raise ValueError(f"محصول والد «{parent_code}» یافت نشد. ابتدا اطلاعات محصول را منتقل کنید.")
    component_code = str(values.get("component_code") or "").strip()
    component_name = str(values.get("component_name") or "").strip() or component_code
    if not component_name:
        raise ValueError("نام یا کد جزء الزامی است.")
    qty = _dec(values.get("quantity"), Decimal("1")) or Decimal("1")
    unit = str(values.get("unit") or "عدد").strip() or "عدد"
    notes = str(values.get("notes") or "").strip()
    order = _int(values.get("order"), 0) or 0

    line = None
    if component_code:
        line = ProductBomLine.objects.filter(
            parent=parent, component_code=component_code
        ).first()
    if line is None and values.get("id"):
        line = ProductBomLine.objects.filter(pk=values["id"], parent=parent).first()

    if line:
        line.component_code = component_code
        line.component_name = component_name
        line.quantity = qty
        line.unit = unit
        line.notes = notes
        line.order = order
        line.save()
        return line
    return ProductBomLine.objects.create(
        parent=parent,
        component_code=component_code,
        component_name=component_name,
        quantity=qty,
        unit=unit,
        notes=notes,
        order=order,
    )


@transaction.atomic
def upsert_consumable_from_values(values: dict[str, Any]) -> ProductConsumable:
    product_code = str(values.get("product_code") or "").strip()
    if not product_code:
        raise ValueError("کد محصول الزامی است.")
    product = Product.objects.filter(code=product_code).first()
    if not product:
        raise ValueError(f"محصول «{product_code}» یافت نشد. ابتدا اطلاعات محصول را منتقل کنید.")
    material_code = str(values.get("material_code") or "").strip()
    material_name = str(values.get("material_name") or "").strip() or material_code
    if not material_name:
        raise ValueError("نام یا کد ماده الزامی است.")
    qty = _dec(values.get("quantity_per_unit"), Decimal("0")) or Decimal("0")
    unit = str(values.get("unit") or "گرم").strip() or "گرم"
    notes = str(values.get("notes") or "").strip()
    order = _int(values.get("order"), 0) or 0

    row = None
    if material_code:
        row = ProductConsumable.objects.filter(
            product=product, material_code=material_code
        ).first()
    if row is None and values.get("id"):
        row = ProductConsumable.objects.filter(pk=values["id"], product=product).first()
    if row:
        row.material_code = material_code
        row.material_name = material_name
        row.quantity_per_unit = qty
        row.unit = unit
        row.notes = notes
        row.order = order
        row.save()
        return row
    return ProductConsumable.objects.create(
        product=product,
        material_code=material_code,
        material_name=material_name,
        quantity_per_unit=qty,
        unit=unit,
        notes=notes,
        order=order,
    )


def save_tab_rows(tab_id: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Bulk save editable rows for a tab. Returns {saved, failed}."""
    tab_id = resolve_tab(tab_id)
    saved = 0
    failed = 0
    for raw in rows:
        if not isinstance(raw, dict):
            failed += 1
            continue
        try:
            if tab_id == TAB_INFO:
                upsert_product_from_values(raw)
            elif tab_id == TAB_BOM:
                upsert_bom_from_values(raw)
            elif tab_id == TAB_CONSUMABLES:
                upsert_consumable_from_values(raw)
            else:
                raise ValueError("این تب هنوز قابل ویرایش نیست.")
            saved += 1
        except Exception:  # noqa: BLE001
            failed += 1
    return {"saved": saved, "failed": failed}


def delete_tab_row(tab_id: str, row_id: int) -> None:
    tab_id = resolve_tab(tab_id)
    if tab_id == TAB_INFO:
        Product.objects.filter(pk=row_id).update(is_active=False)
    elif tab_id == TAB_BOM:
        ProductBomLine.objects.filter(pk=row_id).delete()
    elif tab_id == TAB_CONSUMABLES:
        ProductConsumable.objects.filter(pk=row_id).delete()
    else:
        raise ValueError("حذف برای این تب پشتیبانی نمی‌شود.")
