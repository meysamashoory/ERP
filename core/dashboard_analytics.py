"""Dashboard analytics payloads for Chart.js / Power-BI-like controls."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from django.db.models import Sum

from catalog.models import FlexibleDataset, FlexibleRow, Product
from production.models import ProductionDayEntry


SEASON_LABELS = {
    1: "بهار",
    2: "تابستان",
    3: "پاییز",
    4: "زمستان",
}


def _jalali_parts(value) -> tuple[int, int, int] | None:
    """Normalize jDateField / date values to (year, month, day) Jalali parts."""
    if not value:
        return None
    # django-jalali stores jdatetime.date on the model instance.
    year = getattr(value, "year", None)
    month = getattr(value, "month", None)
    day = getattr(value, "day", None)
    if year is not None and month is not None and day is not None:
        # Already Jalali (jdatetime.date) — year typically >= 1300.
        if int(year) >= 1300:
            return int(year), int(month), int(day)
        try:
            import jdatetime

            jd = jdatetime.date.fromgregorian(date=value)
            return jd.year, jd.month, jd.day
        except Exception:
            return int(year), int(month), int(day)
    try:
        import jdatetime

        jd = jdatetime.date.fromgregorian(date=value)
        return jd.year, jd.month, jd.day
    except Exception:
        return None


def _season(month: int) -> int:
    if month <= 3:
        return 1
    if month <= 6:
        return 2
    if month <= 9:
        return 3
    return 4


def _voucher_qty_rows() -> list[dict[str, Any]]:
    """Use product-data vouchers flexible table as sales proxy when present."""
    ds = FlexibleDataset.objects.filter(
        destination_id="product_data", level_id="vouchers"
    ).first()
    if not ds:
        return []
    cols = ds.columns or []
    qty_keys = []
    code_keys = []
    name_keys = []
    for c in cols:
        label = str(c.get("label") or c.get("key") or "")
        key = str(c.get("key") or "")
        if any(x in label for x in ("مقدار", "تعداد", "فروش")):
            qty_keys.append(key)
        if "کد" in label:
            code_keys.append(key)
        if "نام" in label:
            name_keys.append(key)
    out: list[dict[str, Any]] = []
    for row in FlexibleRow.objects.filter(dataset=ds)[:5000]:
        vals = row.values or {}
        qty = 0.0
        for k in qty_keys:
            try:
                qty = float(str(vals.get(k, "0")).replace(",", "") or 0)
                break
            except (TypeError, ValueError):
                continue
        if qty <= 0:
            continue
        code = ""
        for k in code_keys:
            code = str(vals.get(k) or "").strip()
            if code:
                break
        name = ""
        for k in name_keys:
            name = str(vals.get(k) or "").strip()
            if name:
                break
        out.append({"code": code or "—", "name": name or code or "—", "qty": qty})
    return out


def build_dashboard_charts() -> dict[str, Any]:
    """Return JSON-serializable chart datasets + comparison metrics."""
    fitting_qs = ProductionDayEntry.objects.select_related(
        "program__item__product"
    ).all()

    # --- Seasonal / yearly production (proxy until dedicated sales ledger) ---
    year_totals: dict[int, float] = defaultdict(float)
    season_totals: dict[str, float] = defaultdict(float)
    season_year: dict[tuple[int, int], float] = defaultdict(float)
    product_totals: dict[str, dict[str, Any]] = {}

    for entry in fitting_qs.iterator():
        qty = float(entry.produced_quantity or 0)
        if qty <= 0:
            continue
        parts = _jalali_parts(getattr(entry, "date", None))
        if parts:
            y, m, _d = parts
            season = _season(m)
            year_totals[y] += qty
            season_totals[SEASON_LABELS[season]] += qty
            season_year[(y, season)] += qty
        product = getattr(getattr(getattr(entry, "program", None), "item", None), "product", None)
        if product is not None:
            key = product.code or str(product.pk)
            bucket = product_totals.setdefault(
                key, {"code": product.code, "name": product.name, "qty": 0.0}
            )
            bucket["qty"] += qty

    # Prefer voucher quantities as "sales" when available.
    voucher_rows = _voucher_qty_rows()
    sales_by_product: dict[str, dict[str, Any]] = {}
    if voucher_rows:
        for row in voucher_rows:
            key = row["code"]
            bucket = sales_by_product.setdefault(
                key, {"code": row["code"], "name": row["name"], "qty": 0.0}
            )
            bucket["qty"] += float(row["qty"])
            if row["name"] and bucket["name"] in ("—", key):
                bucket["name"] = row["name"]
        ranked = sorted(sales_by_product.values(), key=lambda x: x["qty"], reverse=True)
        sales_source = "vouchers"
    else:
        ranked = sorted(product_totals.values(), key=lambda x: x["qty"], reverse=True)
        sales_source = "production"

    top = ranked[:8]
    bottom = list(reversed(ranked[-8:])) if len(ranked) > 1 else []

    years_sorted = sorted(year_totals.keys())
    year_labels = [str(y) for y in years_sorted]
    year_values = [round(year_totals[y], 2) for y in years_sorted]

    # Season stacked by recent years (up to 4).
    recent_years = years_sorted[-4:] or years_sorted
    season_order = [1, 2, 3, 4]
    season_datasets = []
    palette = ["#0e7490", "#2563eb", "#ca8a04", "#be123c"]
    for idx, y in enumerate(recent_years):
        season_datasets.append(
            {
                "label": str(y),
                "data": [
                    round(season_year.get((y, s), 0.0), 2) for s in season_order
                ],
                "backgroundColor": palette[idx % len(palette)],
            }
        )

    # Point-to-point comparison: last two years if possible, else last two seasons aggregate.
    compare = {"label_a": "—", "label_b": "—", "value_a": 0, "value_b": 0, "pct": None}
    if len(years_sorted) >= 2:
        a, b = years_sorted[-2], years_sorted[-1]
        va, vb = year_totals[a], year_totals[b]
        compare = {
            "label_a": str(a),
            "label_b": str(b),
            "value_a": round(va, 2),
            "value_b": round(vb, 2),
            "pct": round(((vb - va) / va) * 100, 1) if va else None,
        }
    elif season_totals:
        ordered = [(SEASON_LABELS[s], season_totals[SEASON_LABELS[s]]) for s in season_order if SEASON_LABELS[s] in season_totals]
        if len(ordered) >= 2:
            (la, va), (lb, vb) = ordered[-2], ordered[-1]
            compare = {
                "label_a": la,
                "label_b": lb,
                "value_a": round(va, 2),
                "value_b": round(vb, 2),
                "pct": round(((vb - va) / va) * 100, 1) if va else None,
            }

    stock_alerts = [
        {
            "code": p.code,
            "name": p.name,
            "stock": p.stock_finished,
            "reorder": p.reorder_level,
        }
        for p in Product.objects.filter(is_active=True).order_by("stock_finished")[:12]
        if p.needs_reorder
    ]

    return {
        "sales_source": sales_source,
        "years": {"labels": year_labels, "values": year_values},
        "seasons": {
            "labels": [SEASON_LABELS[s] for s in season_order],
            "datasets": season_datasets,
            "totals": [round(season_totals.get(SEASON_LABELS[s], 0.0), 2) for s in season_order],
        },
        "top_products": {
            "labels": [f"{r['code']}" for r in top],
            "names": [r["name"] for r in top],
            "values": [round(r["qty"], 2) for r in top],
        },
        "low_products": {
            "labels": [f"{r['code']}" for r in bottom],
            "names": [r["name"] for r in bottom],
            "values": [round(r["qty"], 2) for r in bottom],
        },
        "compare": compare,
        "stock_alerts": stock_alerts,
    }


def charts_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
