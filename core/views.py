"""Dashboard, reporting and export views."""

from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.http import JsonResponse
from django.shortcuts import render

from catalog.models import Machine, Product, ProductionUnit, StoppageReason
from planning.models import WeeklyPlan
from production.models import (
    PipeProduction,
    ProductionDayEntry,
    ProductionProgram,
    ProductionStoppage,
)

from .exports import export_excel, export_pdf


@login_required
def machines_json(request):
    """Machines belonging to a unit, filtered by type (dependent dropdown)."""
    unit_id = request.GET.get("unit")
    mtype = request.GET.get("type", "injection")
    qs = Machine.objects.filter(is_active=True)
    if unit_id:
        qs = qs.filter(unit_id=unit_id)
    if mtype:
        qs = qs.filter(machine_type=mtype)
    data = [
        {"id": m.id, "label": f"{m.get_machine_type_display()} {m.number}"}
        for m in qs.order_by("id")
    ]
    return JsonResponse({"results": data})


@login_required
def products_json(request):
    """Active products, optionally filtered by subgroup / product kind."""
    from catalog.models import ProductKind

    subgroup_id = request.GET.get("subgroup")
    kind = request.GET.get("kind")
    qs = Product.objects.filter(is_active=True).select_related("subgroup")
    if subgroup_id:
        qs = qs.filter(subgroup_id=subgroup_id)
    if kind:
        qs = qs.filter(subgroup__group__kind=kind)
    data = [
        {
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "subgroup_id": p.subgroup_id,
        }
        for p in qs.order_by("name")
    ]
    return JsonResponse({"results": data})


def _parse_jdate(value: str):
    """Parse a Jalali 'YYYY-MM-DD' string into a jdatetime.date, or None."""
    if not value:
        return None
    import jdatetime

    for sep in ("-", "/"):
        parts = value.strip().split(sep)
        if len(parts) == 3:
            try:
                return jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, TypeError):
                return None
    return None


@login_required
def dashboard(request):
    fitting_qs = ProductionDayEntry.objects.all()
    pipe_qs = PipeProduction.objects.all()

    fitting_produced = fitting_qs.aggregate(t=Sum("produced_quantity"))["t"] or 0
    fitting_planned = fitting_qs.aggregate(t=Sum("planned_quantity"))["t"] or 0
    fitting_scrap = fitting_qs.aggregate(t=Sum("scrap_quantity"))["t"] or 0
    pipe_produced = pipe_qs.aggregate(t=Sum("produced_quantity"))["t"] or 0

    stoppage_minutes = (
        ProductionStoppage.objects.aggregate(t=Sum("minutes"))["t"] or 0
    )

    products = list(Product.objects.all())
    low_stock = [p for p in products if p.needs_reorder]

    # Production by unit (fittings) for a simple bar chart.
    by_unit = (
        fitting_qs.values("program__item__machine__unit__number")
        .annotate(total=Sum("produced_quantity"))
        .order_by("program__item__machine__unit__number")
    )
    unit_max = max((row["total"] or 0 for row in by_unit), default=0)
    unit_bars = [
        {
            "label": f"واحد {row['program__item__machine__unit__number']}",
            "value": row["total"] or 0,
            "pct": round((row["total"] or 0) / unit_max * 100) if unit_max else 0,
        }
        for row in by_unit
    ]

    # Stoppage minutes by reason.
    by_reason = (
        ProductionStoppage.objects.values("reason__label")
        .annotate(total=Sum("minutes"))
        .order_by("-total")[:6]
    )
    reason_max = max((row["total"] or 0 for row in by_reason), default=0)
    reason_bars = [
        {
            "label": row["reason__label"],
            "value": row["total"] or 0,
            "pct": round((row["total"] or 0) / reason_max * 100) if reason_max else 0,
        }
        for row in by_reason
    ]

    # Efficiency / OEE proxy: actual vs planned
    fitting_efficiency = round(fitting_produced / fitting_planned * 100) if fitting_planned else 0
    scrap_rate = round(fitting_scrap / fitting_produced * 100, 1) if fitting_produced else 0

    # Active programs + machines
    active_programs = ProductionProgram.objects.filter(
        status__in=["producing", "setup", "temp_stop"]
    ).count()
    total_machines = Machine.objects.count() if "Machine" in dir() else 0
    try:
        from catalog.models import Machine as MachineModel
        total_machines = MachineModel.objects.count()
    except Exception:
        pass
    active_machines = ProductionProgram.objects.filter(
        status="producing"
    ).values("item__machine").distinct().count()

    # Top 5 products by production volume
    from django.db.models import F
    top_products = (
        fitting_qs.values(
            name=F("program__item__product__name"),
            code=F("program__item__product__code"),
        )
        .annotate(total=Sum("produced_quantity"), scrap=Sum("scrap_quantity"))
        .order_by("-total")[:5]
    )
    top_max = max((row["total"] or 0 for row in top_products), default=0)
    top_product_bars = [
        {
            "label": f"{row['code']} — {row['name']}" if row.get("code") else (row.get("name") or "—"),
            "value": row["total"] or 0,
            "scrap": row["scrap"] or 0,
            "pct": round((row["total"] or 0) / top_max * 100) if top_max else 0,
        }
        for row in top_products
    ]

    # Deviation trend: per-unit deviation
    from collections import defaultdict
    deviation_by_unit: dict[str, list[int]] = defaultdict(list)
    for entry in fitting_qs.values(
        unit=F("program__item__machine__unit__number")
    ).annotate(dev=Sum(F("produced_quantity") - F("planned_quantity"))):
        label = f"واحد {entry['unit']}"
        deviation_by_unit[label].append(entry["dev"] or 0)

    context = {
        "fitting_produced": fitting_produced,
        "fitting_planned": fitting_planned,
        "fitting_deviation": fitting_produced - fitting_planned,
        "fitting_scrap": fitting_scrap,
        "fitting_efficiency": fitting_efficiency,
        "scrap_rate": scrap_rate,
        "pipe_produced": pipe_produced,
        "stoppage_minutes": stoppage_minutes,
        "low_stock": low_stock[:8],
        "low_stock_count": len(low_stock),
        "pending_plans": WeeklyPlan.objects.filter(
            status=WeeklyPlan.Status.DRAFT
        ).count(),
        "active_programs": active_programs,
        "total_machines": total_machines,
        "active_machines": active_machines,
        "unit_bars": unit_bars,
        "reason_bars": reason_bars,
        "top_product_bars": top_product_bars,
        "recent_fittings": fitting_qs.select_related(
            "program__item__product", "program__item__machine__unit"
        )[:8],
    }
    return render(request, "dashboard.html", context)


def _dev_reason(r):
    return r.deviation_reason.label if r.deviation_reason_id else ""


def _fit_material_used(r):
    w = r.program.item.product.unit_weight_grams or 0
    return round(float(w) * r.produced_quantity * r.active_cavities / 1000, 2)


def _fit_material_scrap(r):
    w = r.program.item.product.unit_weight_grams or 0
    return round(float(w) * r.scrap_quantity * r.active_cavities / 1000, 2)


# Fitting report reads plan-driven day entries. (key, label, getter)
FITTING_COLUMNS = [
    ("uid", "شناسه برنامه", lambda r: r.program.resolved_uid),
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
]

PIPE_COLUMNS = [
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
]


@login_required
def reports(request):
    report_type = request.GET.get("type", "fitting")
    unit_id = request.GET.get("unit") or ""
    date_from = _parse_jdate(request.GET.get("from", ""))
    date_to = _parse_jdate(request.GET.get("to", ""))
    keyword = request.GET.get("q", "").strip()

    if report_type == "pipe":
        qs = PipeProduction.objects.select_related("unit", "line", "product", "deviation_reason").all()
        if keyword:
            qs = qs.filter(pipe_type__icontains=keyword)
        if unit_id:
            qs = qs.filter(unit_id=unit_id)
        columns = PIPE_COLUMNS
    else:
        report_type = "fitting"
        qs = ProductionDayEntry.objects.select_related(
            "program__item__product", "program__item__machine__unit", "deviation_reason"
        ).all()
        if keyword:
            qs = qs.filter(program__item__product__name__icontains=keyword)
        if unit_id:
            qs = qs.filter(program__item__machine__unit_id=unit_id)
        columns = FITTING_COLUMNS

    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    # Column selection (default: all columns).
    all_keys = [c[0] for c in columns]
    selected = request.GET.getlist("cols") or all_keys
    active = [c for c in columns if c[0] in selected]
    headers = [label for _key, label, _getter in active]
    rows = [[getter(r) for _k, _l, getter in active] for r in qs]

    export = request.GET.get("export")
    if export == "excel":
        return export_excel(f"report_{report_type}", headers, rows, "گزارش تولید")
    if export == "pdf":
        return export_pdf(f"report_{report_type}", headers, rows, "گزارش تولید")

    context = {
        "report_type": report_type,
        "headers": headers,
        "rows": rows,
        "units": ProductionUnit.objects.all(),
        "column_choices": [(key, label, key in selected) for key, label, _g in columns],
        "filters": {
            "unit": unit_id,
            "from": request.GET.get("from", ""),
            "to": request.GET.get("to", ""),
            "q": keyword,
        },
        "total_produced": sum((r.produced_quantity for r in qs), 0),
    }
    return render(request, "reports.html", context)
