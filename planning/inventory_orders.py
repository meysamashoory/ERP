"""Helpers for «بررسی موجودی و سفارشات» hub and Excel upserts."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from catalog.models import Product
from catalog.product_data import _bool, _int
from catalog.jalali_dates import coerce_to_jalali_storage

from .models import CustomerOrder, SalesForecast

TAB_ORDERS = "orders"
TAB_STOCK = "stock"
TAB_BOM = "bom"
TAB_FORECAST = "forecast"

INVENTORY_ORDER_TABS: list[dict[str, Any]] = [
    {"id": TAB_ORDERS, "label": "سفارشات", "editable": False},
    {"id": TAB_STOCK, "label": "موجودی و سقف دپو", "editable": False},
    {"id": TAB_BOM, "label": "ساختار BOM", "editable": False},
    {
        "id": TAB_FORECAST,
        "label": "پیش‌بینی فروش",
        "editable": False,
        "hint": "در تراز تقاضا و ساخت برنامه سیستمی به‌عنوان تقاضای تکمیل ظرفیت (MTS) لحاظ می‌شود.",
    },
]


def resolve_tab(tab_id: str | None) -> str:
    ids = {t["id"] for t in INVENTORY_ORDER_TABS}
    if tab_id in ids:
        return tab_id or TAB_ORDERS
    return TAB_ORDERS


def _parse_jdate(raw):
    if raw is None or raw == "":
        return None
    return coerce_to_jalali_storage(raw)


@transaction.atomic
def upsert_order_from_values(
    values: dict[str, Any], *, update_only: bool = False, source_table: str = ""
) -> CustomerOrder | None:
    code = str(values.get("product_code") or "").strip()
    if not code:
        raise ValueError("کد کالا الزامی است.")
    qty = _int(values.get("quantity"), 0) or 0
    if qty <= 0:
        raise ValueError("مقدار سفارش باید بزرگ‌تر از صفر باشد.")

    order_ref = str(values.get("order_ref") or "").strip()
    product = Product.objects.filter(code=code).first()
    name = str(values.get("product_name") or "").strip()
    if not name and product:
        name = product.name

    defaults = {
        "product_name": name,
        "quantity": qty,
        "delivery_date": _parse_jdate(values.get("delivery_date")),
        "priority": _int(values.get("priority"), 100) or 100,
        "is_backlog": _bool(values.get("is_backlog")),
        "customer_name": str(values.get("customer_name") or "").strip(),
        "notes": str(values.get("notes") or "").strip(),
        "product": product,
        "is_active": True,
        "source_table_name": source_table or "",
    }

    qs = CustomerOrder.objects.filter(product_code=code, order_ref=order_ref)
    existing = qs.order_by("-updated_at").first()
    if existing is None:
        if update_only:
            return None
        return CustomerOrder.objects.create(product_code=code, order_ref=order_ref, **defaults)

    for key, val in defaults.items():
        setattr(existing, key, val)
    existing.save()
    return existing


@transaction.atomic
def upsert_stock_from_values(
    values: dict[str, Any], *, update_only: bool = False
) -> Product | None:
    """Update inventory / depot ceiling on an existing product (create if allowed)."""
    code = str(values.get("code") or values.get("product_code") or "").strip()
    if not code:
        raise ValueError("کد کالا الزامی است.")
    product = Product.objects.filter(code=code).first()
    name = str(values.get("name") or values.get("product_name") or "").strip()

    if product is None:
        if update_only:
            return None
        from catalog.product_data import ensure_default_subgroup

        product = Product.objects.create(
            code=code,
            name=name or code,
            subgroup=ensure_default_subgroup(),
        )
    elif name:
        product.name = name

    if "stock_finished" in values and values.get("stock_finished") is not None:
        product.stock_finished = _int(values.get("stock_finished"), 0) or 0
    if "stock_unassembled" in values and values.get("stock_unassembled") is not None:
        product.stock_unassembled = _int(values.get("stock_unassembled"), 0) or 0
    if "depot_ceiling" in values and values.get("depot_ceiling") not in (None, ""):
        product.depot_ceiling = _int(values.get("depot_ceiling"))
    product.save()
    return product


@transaction.atomic
def upsert_forecast_from_values(
    values: dict[str, Any], *, update_only: bool = False, source_table: str = ""
) -> SalesForecast | None:
    code = str(values.get("product_code") or "").strip()
    if not code:
        raise ValueError("کد کالا الزامی است.")
    qty = _int(values.get("quantity"), 0) or 0
    period = str(values.get("period_label") or "").strip()
    product = Product.objects.filter(code=code).first()
    name = str(values.get("product_name") or "").strip()
    if not name and product:
        name = product.name

    defaults = {
        "product_name": name,
        "quantity": qty,
        "notes": str(values.get("notes") or "").strip(),
        "product": product,
        "is_active": True,
        "source_table_name": source_table or "",
    }
    existing = (
        SalesForecast.objects.filter(product_code=code, period_label=period)
        .order_by("-updated_at")
        .first()
    )
    if existing is None:
        if update_only:
            return None
        return SalesForecast.objects.create(
            product_code=code, period_label=period, **defaults
        )
    for key, val in defaults.items():
        setattr(existing, key, val)
    existing.save()
    return existing


def order_rows() -> list[dict[str, Any]]:
    rows = []
    for o in CustomerOrder.objects.filter(is_active=True).select_related("product")[:2000]:
        rows.append(
            {
                "id": o.pk,
                "order_ref": o.order_ref or "—",
                "product_code": o.product_code,
                "product_name": o.product_name or (o.product.name if o.product else "—"),
                "quantity": o.quantity,
                "delivery_date": o.delivery_date,
                "priority": o.priority,
                "is_backlog": o.is_backlog,
                "customer_name": o.customer_name or "—",
                "stock": o.product.stock_finished if o.product else None,
                "depot_ceiling": o.product.depot_ceiling if o.product else None,
            }
        )
    return rows


def stock_rows() -> list[dict[str, Any]]:
    rows = []
    for p in Product.objects.filter(is_active=True).select_related("subgroup__group").order_by("code")[:3000]:
        rows.append(
            {
                "id": p.pk,
                "code": p.code,
                "name": p.name,
                "stock_finished": p.stock_finished,
                "stock_unassembled": p.stock_unassembled,
                "depot_ceiling": p.depot_ceiling if p.depot_ceiling is not None else "—",
                "reorder_level": p.reorder_level,
            }
        )
    return rows


def forecast_rows() -> list[dict[str, Any]]:
    rows = []
    for f in SalesForecast.objects.filter(is_active=True).order_by("product_code")[:2000]:
        rows.append(
            {
                "id": f.pk,
                "product_code": f.product_code,
                "product_name": f.product_name or "—",
                "period_label": f.period_label or "—",
                "quantity": f.quantity,
                "notes": f.notes or "—",
            }
        )
    return rows
