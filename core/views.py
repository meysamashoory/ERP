"""Dashboard, reporting and export views."""

from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.http import JsonResponse
from django.shortcuts import render

from catalog.models import Machine, Product, ProductionUnit, StoppageReason
from planning.models import WeeklyPlan
from production.models import FittingProduction, PipeProduction, ProductionStoppage

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
    """Active products of a subgroup with their code (dependent dropdown)."""
    subgroup_id = request.GET.get("subgroup")
    qs = Product.objects.filter(is_active=True)
    if subgroup_id:
        qs = qs.filter(subgroup_id=subgroup_id)
    data = [
        {"id": p.id, "name": p.name, "code": p.code}
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
    fitting_qs = FittingProduction.objects.all()
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
        fitting_qs.values("unit__number")
        .annotate(total=Sum("produced_quantity"))
        .order_by("unit__number")
    )
    unit_max = max((row["total"] or 0 for row in by_unit), default=0)
    unit_bars = [
        {
            "label": f"واحد {row['unit__number']}",
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

    context = {
        "fitting_produced": fitting_produced,
        "fitting_planned": fitting_planned,
        "fitting_deviation": fitting_produced - fitting_planned,
        "fitting_scrap": fitting_scrap,
        "pipe_produced": pipe_produced,
        "stoppage_minutes": stoppage_minutes,
        "low_stock": low_stock[:8],
        "low_stock_count": len(low_stock),
        "pending_plans": WeeklyPlan.objects.filter(
            status=WeeklyPlan.Status.DRAFT
        ).count(),
        "unit_bars": unit_bars,
        "reason_bars": reason_bars,
        "recent_fittings": fitting_qs.select_related("unit", "machine", "product")[:6],
    }
    return render(request, "dashboard.html", context)


def _dev_reason(r):
    return r.deviation_reason.label if r.deviation_reason_id else ""


# Report columns: (key, label, getter). Users pick which to display.
FITTING_COLUMNS = [
    ("date", "تاریخ", lambda r: str(r.date)),
    ("unit", "واحد", lambda r: f"واحد {r.unit.number}"),
    ("machine", "دستگاه", lambda r: str(r.machine.number)),
    ("code", "کد کالا", lambda r: r.product.code),
    ("product", "نام محصول", lambda r: r.product.name),
    ("shot_cycle", "سیکل یک‌ضرب", lambda r: r.shot_cycle),
    ("produced", "تولیدشده", lambda r: r.produced_quantity),
    ("planned", "برنامه‌ریزی‌شده", lambda r: r.planned_quantity),
    ("scrap", "ضایعات", lambda r: r.scrap_quantity),
    ("material_used", "مواد مصرفی (kg)", lambda r: r.material_used),
    ("material_scrap", "مواد ضایعاتی (kg)", lambda r: r.material_scrap),
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
        columns = PIPE_COLUMNS
    else:
        report_type = "fitting"
        qs = FittingProduction.objects.select_related(
            "unit", "machine", "product", "deviation_reason"
        ).all()
        if keyword:
            qs = qs.filter(product__name__icontains=keyword)
        columns = FITTING_COLUMNS

    if unit_id:
        qs = qs.filter(unit_id=unit_id)
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
