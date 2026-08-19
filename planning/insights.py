"""Resolve configurable planning insight metrics for a product."""

from __future__ import annotations

from catalog.models import PlanningInsightField, Product
from production.models import FittingProduction


def _last_fitting(product: Product):
    return (
        FittingProduction.objects.filter(product=product)
        .select_related("machine", "machine__unit")
        .order_by("-date", "-id")
        .first()
    )


def _product_value(product: Product, key: str):
    mapping = {
        "last_cycle": product.last_cycle,
        "main_cavities": product.main_cavities,
        "per_carton": product.per_carton,
        "per_bag": product.per_bag,
        "depot_ceiling": product.depot_ceiling,
        "stock_finished": product.stock_finished,
        "unit_weight_grams": product.unit_weight_grams,
    }
    return mapping.get(key)


def _last_production_value(product: Product, key: str):
    last = _last_fitting(product)
    if not last:
        return None
    if key == "shot_cycle":
        return last.shot_cycle
    if key == "machine_unit":
        return f"دستگاه {last.machine.number} · واحد {last.machine.unit.number}"
    if key == "active_cavities":
        return last.active_cavities
    if key == "produced_quantity":
        return last.produced_quantity
    if key == "date":
        return str(last.date)
    return None


def resolve_insights(product: Product | None) -> list[dict]:
    """Return active insight cards as ``{label, value, source}`` dicts."""
    fields = PlanningInsightField.objects.filter(is_active=True)
    cards = []
    for field in fields:
        value = None
        if product is not None:
            if field.source == PlanningInsightField.Source.PRODUCT:
                value = _product_value(product, field.source_key)
            elif field.source == PlanningInsightField.Source.LAST_PRODUCTION:
                value = _last_production_value(product, field.source_key)
            elif field.source == PlanningInsightField.Source.FILE_COLUMN:
                # File/Excel mapping will be wired when the user provides the file.
                value = None
        cards.append({
            "label": field.label,
            "value": "—" if value in (None, "") else value,
            "source": field.source,
            "key": field.source_key,
        })
    return cards


def resolve_insight_details(product: Product | None) -> list[dict]:
    """Full history rows per insight field (for the جزئیات dialog)."""
    from planning.utils import format_jdate

    fields = PlanningInsightField.objects.filter(is_active=True)
    sections: list[dict] = []
    if product is None:
        for field in fields:
            sections.append({"label": field.label, "rows": []})
        return sections

    productions = list(
        FittingProduction.objects.filter(product=product)
        .select_related("machine", "machine__unit")
        .order_by("-date", "-id")
    )

    for field in fields:
        rows = []
        if field.source == PlanningInsightField.Source.PRODUCT:
            value = _product_value(product, field.source_key)
            rows.append({
                "title": product.name,
                "value": "—" if value in (None, "") else value,
            })
        elif field.source == PlanningInsightField.Source.LAST_PRODUCTION:
            for rec in productions:
                if field.source_key == "shot_cycle":
                    value = rec.shot_cycle
                elif field.source_key == "machine_unit":
                    value = f"دستگاه {rec.machine.number} · واحد {rec.machine.unit.number}"
                elif field.source_key == "active_cavities":
                    value = rec.active_cavities
                elif field.source_key == "produced_quantity":
                    value = rec.produced_quantity
                elif field.source_key == "date":
                    value = format_jdate(rec.date)
                else:
                    value = None
                rows.append({
                    "title": format_jdate(rec.date) or str(rec.date),
                    "value": "—" if value in (None, "") else value,
                })
        sections.append({"label": field.label, "rows": rows})
    return sections
