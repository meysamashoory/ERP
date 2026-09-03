"""Native planning intelligence: demand/supply, shortages, capacity, variance.

Inspired by manufacturing-planning practices (netting, exceptions, load) but
shaped around this ERP's weekly mold programs — not an SAP screen clone.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from catalog.models import Machine, Product
from production.models import ProductionHistoryRecord, ProductionProgram

from .models import CustomerOrder, SalesForecast, WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine

# Weekly available hours per injection machine (2 shifts × 6 days).
HOURS_PER_MACHINE_WEEK = 96.0
QTY_DEVIATION_PCT = 10.0
CYCLE_DEVIATION_PCT = 15.0


@dataclass
class BalanceRow:
    product_code: str
    product_name: str
    order_qty: int
    forecast_qty: int
    stock: int
    unassembled: int
    open_plan_qty: int
    depot_ceiling: int | None
    net_gap: int  # positive = shortage vs demand
    surplus: int
    priority: int
    backlog: bool
    status: str  # shortage | covered | surplus | reorder
    severity: str  # serious | watch | ok


@dataclass
class MaterialRow:
    component_code: str
    component_name: str
    need: float
    have: float
    gap: float
    parents: list[str] = field(default_factory=list)


@dataclass
class CapacityRow:
    machine_id: int
    machine_label: str
    unit_number: int | None
    hours: float
    available: float
    load_pct: float
    item_count: int
    status: str  # overload | tight | ok | idle


@dataclass
class VarianceRow:
    uid: str
    plan_number: str
    product_name: str
    planned_qty: int | None
    produced_qty: int | None
    qty_gap: int | None
    planned_cycle: int | None
    last_cycle: int | None
    scrap_qty: int | None
    status: str


@dataclass
class ExceptionMsg:
    code: str
    severity: str  # serious | watch
    title: str
    detail: str
    product_code: str = ""


def _open_plan_qty_by_code() -> dict[str, int]:
    """Quantity already sitting on draft/approved weekly plans (not finished)."""
    finished_item_ids = set(
        ProductionProgram.objects.filter(status=ProductionProgram.Status.FINISHED).values_list(
            "item_id", flat=True
        )
    )
    qs = WeeklyPlanLine.objects.filter(
        item__plan__status__in=[WeeklyPlan.Status.DRAFT, WeeklyPlan.Status.APPROVED],
        quantity__gt=0,
    ).select_related("item__product")
    out: dict[str, int] = defaultdict(int)
    for line in qs:
        if line.item_id in finished_item_ids:
            continue
        product = getattr(line.item, "product", None)
        code = (getattr(product, "code", None) or "").strip()
        if not code:
            continue
        out[code] += int(line.quantity or 0)
    return dict(out)


def _forecast_qty_by_code() -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for row in SalesForecast.objects.filter(is_active=True, quantity__gt=0):
        code = (row.product_code or "").strip()
        if code:
            out[code] += int(row.quantity or 0)
    return dict(out)


def _orders_by_code() -> dict[str, dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    qs = CustomerOrder.objects.filter(is_active=True, quantity__gt=0).select_related("product")
    for row in qs:
        code = (row.product_code or "").strip()
        if not code:
            continue
        bucket = agg.setdefault(
            code,
            {
                "product": row.product,
                "product_name": row.product_name,
                "quantity": 0,
                "priority": int(row.priority or 100),
                "backlog": False,
            },
        )
        bucket["quantity"] += int(row.quantity or 0)
        bucket["priority"] = min(bucket["priority"], int(row.priority or 100))
        bucket["backlog"] = bucket["backlog"] or bool(row.is_backlog)
        if row.product is not None:
            bucket["product"] = row.product
        if row.product_name and not bucket.get("product_name"):
            bucket["product_name"] = row.product_name
    return agg


def demand_balance() -> list[BalanceRow]:
    orders = _orders_by_code()
    forecast = _forecast_qty_by_code()
    open_plan = _open_plan_qty_by_code()
    codes = set(orders) | set(forecast) | set(open_plan)

    products = {p.code: p for p in Product.objects.filter(code__in=codes)}
    rows: list[BalanceRow] = []
    for code in sorted(codes):
        product = products.get(code) or (orders.get(code) or {}).get("product")
        name = (
            (getattr(product, "name", None) or "")
            or (orders.get(code) or {}).get("product_name")
            or code
        )
        order_qty = int((orders.get(code) or {}).get("quantity") or 0)
        forecast_qty = int(forecast.get(code) or 0)
        stock = int(getattr(product, "stock_finished", 0) or 0) if product else 0
        unassembled = int(getattr(product, "stock_unassembled", 0) or 0) if product else 0
        planned = int(open_plan.get(code) or 0)
        ceiling = getattr(product, "depot_ceiling", None) if product else None
        demand = order_qty + forecast_qty
        cover = stock + planned
        net_gap = max(demand - cover, 0)
        surplus = max(cover - demand, 0)
        reorder = bool(product and getattr(product, "needs_reorder", False))
        backlog = bool((orders.get(code) or {}).get("backlog"))
        if net_gap > 0:
            status, severity = "shortage", "serious"
        elif backlog:
            status, severity = "backlog", "watch"
        elif reorder:
            status, severity = "reorder", "watch"
        elif surplus > 0:
            status, severity = "surplus", "ok"
        else:
            status, severity = "covered", "ok"
        rows.append(
            BalanceRow(
                product_code=code,
                product_name=name,
                order_qty=order_qty,
                forecast_qty=forecast_qty,
                stock=stock,
                unassembled=unassembled,
                open_plan_qty=planned,
                depot_ceiling=int(ceiling) if ceiling is not None else None,
                net_gap=net_gap,
                surplus=surplus,
                priority=int((orders.get(code) or {}).get("priority") or 100),
                backlog=backlog,
                status=status,
                severity=severity,
            )
        )
    rows.sort(key=lambda r: (0 if r.severity == "serious" else 1 if r.severity == "watch" else 2, r.priority, r.product_code))
    return rows


def material_shortages(produce_by_code: dict[str, int] | None = None) -> list[MaterialRow]:
    """BOM + consumable shortfalls for proposed or open production quantities."""
    if produce_by_code is None:
        produce_by_code = {}
        for row in demand_balance():
            extra = row.net_gap
            if extra > 0:
                produce_by_code[row.product_code] = extra
            elif row.open_plan_qty > 0:
                produce_by_code[row.product_code] = row.open_plan_qty

    need: dict[str, dict[str, Any]] = {}
    products = {p.code: p for p in Product.objects.filter(code__in=produce_by_code.keys()).prefetch_related("bom_lines", "consumables")}
    catalog_by_code = {p.code: p for p in Product.objects.all().only("id", "code", "name", "stock_finished", "stock_unassembled")}

    for code, qty in produce_by_code.items():
        if qty <= 0:
            continue
        product = products.get(code)
        if product is None:
            continue
        parent_label = f"{product.code}"
        for line in product.bom_lines.all():
            ccode = (line.component_code or "").strip() or (line.component_name or "").strip()
            if not ccode:
                continue
            amount = float(line.quantity or 0) * qty
            bucket = need.setdefault(
                ccode,
                {"name": line.component_name or ccode, "need": 0.0, "parents": []},
            )
            bucket["need"] += amount
            if parent_label not in bucket["parents"]:
                bucket["parents"].append(parent_label)
        for cons in product.consumables.all():
            ccode = (cons.material_code or "").strip() or (cons.material_name or "").strip()
            if not ccode:
                continue
            amount = float(cons.quantity_per_unit or 0) * qty
            bucket = need.setdefault(
                ccode,
                {"name": cons.material_name or ccode, "need": 0.0, "parents": []},
            )
            bucket["need"] += amount
            if parent_label not in bucket["parents"]:
                bucket["parents"].append(parent_label)

    rows: list[MaterialRow] = []
    for ccode, data in need.items():
        comp = catalog_by_code.get(ccode)
        have = 0.0
        name = data["name"]
        if comp is not None:
            have = float(comp.stock_finished or 0) + float(comp.stock_unassembled or 0)
            name = comp.name or name
        gap = max(data["need"] - have, 0)
        if gap <= 0:
            continue
        rows.append(
            MaterialRow(
                component_code=ccode,
                component_name=name,
                need=round(data["need"], 3),
                have=round(have, 3),
                gap=round(gap, 3),
                parents=data["parents"][:6],
            )
        )
    rows.sort(key=lambda r: -r.gap)
    return rows


def machine_load() -> list[CapacityRow]:
    finished_item_ids = set(
        ProductionProgram.objects.filter(status=ProductionProgram.Status.FINISHED).values_list(
            "item_id", flat=True
        )
    )
    hours_by_machine: dict[int, float] = defaultdict(float)
    count_by_machine: dict[int, int] = defaultdict(int)
    items = WeeklyPlanItem.objects.filter(
        plan__status__in=[WeeklyPlan.Status.DRAFT, WeeklyPlan.Status.APPROVED]
    ).select_related("machine__unit").prefetch_related("lines")
    for item in items:
        if item.pk in finished_item_ids:
            continue
        mid = item.machine_id
        if not mid:
            continue
        h = sum(float(line.production_hours or 0) for line in item.lines.all())
        hours_by_machine[mid] += h
        count_by_machine[mid] += 1

    machines = list(
        Machine.objects.filter(is_active=True, machine_type="injection").select_related("unit")
    )
    rows: list[CapacityRow] = []
    for m in machines:
        hours = round(hours_by_machine.get(m.pk, 0.0), 2)
        available = HOURS_PER_MACHINE_WEEK
        pct = round((hours / available) * 100, 1) if available else 0
        if hours <= 0:
            status = "idle"
        elif pct > 100:
            status = "overload"
        elif pct >= 85:
            status = "tight"
        else:
            status = "ok"
        rows.append(
            CapacityRow(
                machine_id=m.pk,
                machine_label=str(m),
                unit_number=getattr(m.unit, "number", None),
                hours=hours,
                available=available,
                load_pct=pct,
                item_count=count_by_machine.get(m.pk, 0),
                status=status,
            )
        )
    rows.sort(key=lambda r: (-r.load_pct, r.unit_number or 0, r.machine_label))
    return rows


def plan_vs_actual(*, limit: int = 80) -> list[VarianceRow]:
    rows: list[VarianceRow] = []
    qs = ProductionHistoryRecord.objects.exclude(planned_qty__isnull=True).order_by("-id")[:limit]
    for rec in qs:
        planned = rec.planned_qty
        produced = rec.produced_qty
        gap = None
        if planned is not None and produced is not None:
            gap = int(produced) - int(planned)
        status = "ok"
        if gap is not None and planned:
            if abs(gap) >= max(1, int(abs(planned) * QTY_DEVIATION_PCT / 100)):
                status = "qty"
        if status == "ok" and rec.planned_cycle and rec.last_cycle:
            drift = abs(int(rec.last_cycle) - int(rec.planned_cycle))
            if drift >= max(1, int(rec.planned_cycle * CYCLE_DEVIATION_PCT / 100)):
                status = "cycle"
        if rec.scrap_qty and rec.scrap_qty > 0 and status == "ok":
            status = "scrap"
        rows.append(
            VarianceRow(
                uid=rec.unique_code or rec.program_uid,
                plan_number=rec.plan_number or "",
                product_name=rec.product_name or rec.product_code,
                planned_qty=planned,
                produced_qty=produced,
                qty_gap=gap,
                planned_cycle=rec.planned_cycle,
                last_cycle=rec.last_cycle,
                scrap_qty=rec.scrap_qty,
                status=status,
            )
        )
    return rows


def exception_messages(
    *,
    balance: list[BalanceRow] | None = None,
    materials: list[MaterialRow] | None = None,
    capacity: list[CapacityRow] | None = None,
    variance: list[VarianceRow] | None = None,
) -> list[ExceptionMsg]:
    if balance is None:
        balance = demand_balance()
    if materials is None:
        materials = material_shortages()
    if capacity is None:
        capacity = machine_load()
    if variance is None:
        variance = plan_vs_actual(limit=40)
    msgs: list[ExceptionMsg] = []
    for row in balance:
        if row.net_gap > 0:
            msgs.append(
                ExceptionMsg(
                    code="NET_SHORT",
                    severity="serious",
                    title="کسری خالص نسبت به تقاضا",
                    detail=f"سفارش {row.order_qty} + پیش‌بینی {row.forecast_qty} در برابر موجودی {row.stock} و برنامه باز {row.open_plan_qty} — کسری {row.net_gap}.",
                    product_code=row.product_code,
                )
            )
        if row.backlog:
            msgs.append(
                ExceptionMsg(
                    code="BACKLOG",
                    severity="watch" if row.net_gap == 0 else "serious",
                    title="سفارش معوق",
                    detail=f"{row.product_name} هنوز معوق است.",
                    product_code=row.product_code,
                )
            )
        if row.status == "reorder":
            msgs.append(
                ExceptionMsg(
                    code="REORDER",
                    severity="watch",
                    title="زیر سطح سفارش مجدد",
                    detail=f"موجودی {row.stock} برای {row.product_code} به سطح سفارش مجدد رسیده.",
                    product_code=row.product_code,
                )
            )
        ceiling = row.depot_ceiling
        if ceiling is not None and row.stock >= ceiling:
            msgs.append(
                ExceptionMsg(
                    code="DEPOT_FULL",
                    severity="watch",
                    title="سقف دپو پر است",
                    detail=f"{row.product_code}: موجودی {row.stock} ≥ سقف {ceiling}.",
                    product_code=row.product_code,
                )
            )
    for mat in materials[:40]:
        msgs.append(
            ExceptionMsg(
                code="BOM_SHORT",
                severity="serious",
                title="کسری ماده / جزء BOM",
                detail=f"{mat.component_code}: نیاز {mat.need:g} / موجود {mat.have:g} (والد: {'، '.join(mat.parents)}).",
                product_code=mat.component_code,
            )
        )
    for cap in capacity:
        if cap.status == "overload":
            msgs.append(
                ExceptionMsg(
                    code="CAP_OVER",
                    severity="serious",
                    title="اضافه بار دستگاه",
                    detail=f"{cap.machine_label}: {cap.hours:g} ساعت از {cap.available:g} ({cap.load_pct}٪).",
                )
            )
        elif cap.status == "tight":
            msgs.append(
                ExceptionMsg(
                    code="CAP_TIGHT",
                    severity="watch",
                    title="نزدیک به ظرفیت دستگاه",
                    detail=f"{cap.machine_label}: {cap.load_pct}٪ بار.",
                )
            )
    for var in variance:
        if var.status == "qty":
            msgs.append(
                ExceptionMsg(
                    code="QTY_DEV",
                    severity="watch",
                    title="انحراف مقدار تولید",
                    detail=f"{var.product_name} ({var.uid}): برنامه {var.planned_qty} / واقعی {var.produced_qty}.",
                    product_code=var.uid,
                )
            )
        elif var.status == "cycle":
            msgs.append(
                ExceptionMsg(
                    code="CYCLE_DEV",
                    severity="watch",
                    title="انحراف سیکل",
                    detail=f"{var.product_name}: سیکل برنامه {var.planned_cycle} / آخرین {var.last_cycle}.",
                    product_code=var.uid,
                )
            )
    severity_rank = {"serious": 0, "watch": 1}
    msgs.sort(key=lambda m: (severity_rank.get(m.severity, 9), m.code, m.product_code))
    return msgs


def cockpit_payload() -> dict[str, Any]:
    balance = demand_balance()
    materials = material_shortages()
    capacity = machine_load()
    variance = plan_vs_actual()
    exceptions = exception_messages(
        balance=balance, materials=materials, capacity=capacity, variance=variance
    )
    kpis = {
        "open_orders": sum(1 for r in balance if r.order_qty > 0),
        "net_shortage_skus": sum(1 for r in balance if r.net_gap > 0),
        "net_shortage_qty": sum(r.net_gap for r in balance),
        "material_gaps": len(materials),
        "overloaded_machines": sum(1 for c in capacity if c.status == "overload"),
        "qty_deviations": sum(1 for v in variance if v.status == "qty"),
        "serious_exceptions": sum(1 for e in exceptions if e.severity == "serious"),
        "hours_loaded": round(sum(c.hours for c in capacity), 1),
        "hours_available": round(sum(c.available for c in capacity), 1),
    }
    return {
        "kpis": kpis,
        "balance": [asdict(r) for r in balance],
        "materials": [asdict(r) for r in materials],
        "capacity": [asdict(r) for r in capacity],
        "variance": [asdict(r) for r in variance],
        "exceptions": [asdict(r) for r in exceptions],
        "hours_per_machine": HOURS_PER_MACHINE_WEEK,
    }


def open_planned_qty_for_product(product: Product) -> int:
    code = (product.code or "").strip()
    if not code:
        return 0
    return int(_open_plan_qty_by_code().get(code) or 0)
