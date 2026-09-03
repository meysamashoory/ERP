"""Systemic (auto) weekly planning from orders, forecast, inventory, BOM, capacity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from catalog.models import Machine, Product
from production.models import FittingProduction

from .intelligence import HOURS_PER_MACHINE_WEEK, machine_load, open_planned_qty_for_product
from .models import CustomerOrder, SalesForecast, WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
from .uid import refresh_plan_uids
from .utils import mold_change_date_candidates


@dataclass
class SystemicProposal:
    product: Product
    order_qty: int
    forecast_qty: int
    stock: int
    open_plan_qty: int
    depot_ceiling: int | None
    net_need: int
    produce_qty: int
    bom_ok: bool
    bom_message: str = ""
    machine: Machine | None = None
    warnings: list[str] = field(default_factory=list)


def _aggregate_orders() -> dict[str, dict[str, Any]]:
    """Sum active orders by product_code; keep best (lowest) priority."""
    agg: dict[str, dict[str, Any]] = {}
    qs = (
        CustomerOrder.objects.filter(is_active=True, quantity__gt=0)
        .select_related("product")
        .order_by("priority", "delivery_date", "id")
    )
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
                "priority": row.priority,
                "backlog": False,
            },
        )
        bucket["quantity"] += int(row.quantity or 0)
        bucket["priority"] = min(bucket["priority"], int(row.priority or 100))
        bucket["backlog"] = bucket["backlog"] or bool(row.is_backlog)
        if row.product is not None:
            bucket["product"] = row.product
        if not bucket.get("product_name") and row.product_name:
            bucket["product_name"] = row.product_name
    return agg


def _forecast_qty(code: str) -> int:
    total = 0
    for row in SalesForecast.objects.filter(is_active=True, product_code=code, quantity__gt=0):
        total += int(row.quantity or 0)
    return total


def _max_bom_qty(product: Product, wanted: int) -> tuple[int, str]:
    """Largest produce qty that current BOM + consumable stocks can support."""
    lines = list(product.bom_lines.all())
    consumables = list(product.consumables.all())
    if not lines and not consumables:
        return wanted, "BOM تعریف نشده — بدون محدودیت مواد."
    max_q = wanted
    notes: list[str] = []
    for line in lines:
        per = float(line.quantity or 0)
        if per <= 0:
            continue
        ccode = (line.component_code or "").strip()
        comp = Product.objects.filter(code=ccode).first() if ccode else None
        if comp is None:
            notes.append(f"جزء «{ccode or line.component_name}» در کاتالوگ نیست")
            max_q = 0
            continue
        have = int(comp.stock_finished or 0) + int(comp.stock_unassembled or 0)
        feasible = int(have // per) if per else wanted
        if feasible < max_q:
            notes.append(f"{comp.code}: حداکثر {feasible} (موجود {have})")
            max_q = max(feasible, 0)
    for cons in consumables:
        per = float(cons.quantity_per_unit or 0)
        if per <= 0:
            continue
        ccode = (cons.material_code or "").strip()
        comp = Product.objects.filter(code=ccode).first() if ccode else None
        if comp is None:
            continue
        have = int(comp.stock_finished or 0) + int(comp.stock_unassembled or 0)
        feasible = int(have // per)
        if feasible < max_q:
            notes.append(f"مصرفی {comp.code}: حداکثر {feasible}")
            max_q = max(feasible, 0)
    max_q = max(int(max_q), 0)
    if max_q >= wanted:
        return wanted, "مواد کافی است."
    if max_q == 0:
        return 0, "کسری مواد: " + ("؛ ".join(notes[:4]) or "موجودی جزء صفر است.")
    return max_q, "تولید به خاطر مواد به " + str(max_q) + " محدود شد. " + "؛ ".join(notes[:3])


def _suggest_machine(product: Product, used: set[int]) -> Machine | None:
    """Prefer last fitting machine for this product, else first free injection machine."""
    last = (
        FittingProduction.objects.filter(product=product)
        .select_related("machine__unit")
        .order_by("-id")
        .first()
    )
    if last and last.machine_id and last.machine_id not in used:
        return last.machine
    for m in (
        Machine.objects.filter(machine_type="injection")
        .select_related("unit")
        .order_by("unit__number", "number")
    ):
        if m.pk not in used:
            return m
    return (
        Machine.objects.filter(machine_type="injection")
        .select_related("unit")
        .order_by("unit__number", "number")
        .first()
    )


def build_systemic_proposals() -> list[SystemicProposal]:
    agg = _aggregate_orders()
    proposals: list[SystemicProposal] = []
    used_machines: set[int] = set()
    load_now = {row.machine_id: row.hours for row in machine_load()}

    # Codes with forecast-only demand (MTS top-up) also participate
    forecast_codes = {
        (r.product_code or "").strip()
        for r in SalesForecast.objects.filter(is_active=True, quantity__gt=0)
        if (r.product_code or "").strip()
    }
    codes = set(agg.keys()) | forecast_codes

    def sort_key(code: str):
        data = agg.get(code) or {}
        return (int(data.get("priority") or 100), code)

    for code in sorted(codes, key=sort_key):
        data = agg.get(code) or {}
        product = data.get("product") or Product.objects.filter(code=code).first()
        if product is None:
            continue
        order_qty = int(data.get("quantity") or 0)
        forecast_qty = _forecast_qty(code)
        stock = int(product.stock_finished or 0)
        open_qty = open_planned_qty_for_product(product)
        ceiling = product.depot_ceiling
        demand = order_qty + forecast_qty
        net = max(demand - stock - open_qty, 0)
        produce = net
        warnings: list[str] = []
        if open_qty:
            warnings.append(f"{open_qty} عدد از قبل در برنامه‌های باز است.")
        if ceiling is not None:
            room = max(int(ceiling) - stock, 0)
            if produce > room:
                warnings.append(
                    f"سقف دپو {ceiling}: تولید از {produce} به {room} محدود شد."
                )
                produce = room
        if produce <= 0:
            continue

        capped, bom_msg = _max_bom_qty(product, produce)
        bom_ok = capped >= produce
        if capped < produce:
            warnings.append(bom_msg)
            produce = capped
        if produce <= 0:
            warnings.append(bom_msg or "به‌خاطر کسری مواد ردیف ساخته نشد.")
            continue

        machine = _suggest_machine(product, used_machines)
        if machine:
            used_machines.add(machine.pk)
            cycle = int(product.last_cycle or 0) or 30
            cavities = max(int(product.main_cavities or 1), 1)
            est_hours = (produce / cavities) * cycle / 3600.0
            remaining = HOURS_PER_MACHINE_WEEK - float(load_now.get(machine.pk, 0) or 0)
            if est_hours > remaining > 0:
                max_by_hours = int((remaining * 3600.0 * cavities) / cycle)
                if max_by_hours < produce:
                    warnings.append(
                        f"ظرفیت دستگاه محدود کرد: {produce} → {max(max_by_hours, 0)}."
                    )
                    produce = max(max_by_hours, 0)
                    load_now[machine.pk] = load_now.get(machine.pk, 0) + remaining
            else:
                load_now[machine.pk] = load_now.get(machine.pk, 0) + est_hours
        else:
            warnings.append("دستگاه تزریق آزاد یافت نشد.")

        if produce <= 0:
            continue

        proposals.append(
            SystemicProposal(
                product=product,
                order_qty=order_qty,
                forecast_qty=forecast_qty,
                stock=stock,
                open_plan_qty=open_qty,
                depot_ceiling=int(ceiling) if ceiling is not None else None,
                net_need=net,
                produce_qty=produce,
                bom_ok=bom_ok,
                bom_message=bom_msg,
                machine=machine,
                warnings=warnings,
            )
        )
    return proposals


@transaction.atomic
def create_systemic_plan(
    *,
    program_number: str,
    plan_date,
    user,
) -> tuple[WeeklyPlan, list[str]]:
    """Create a draft weekly plan populated from systemic proposals."""
    alarms: list[str] = []
    proposals = build_systemic_proposals()
    if not proposals:
        alarms.append(
            "هیچ قلم قابل برنامه‌ریزی یافت نشد. ابتدا سفارشات و موجودی را از اکسل منتقل کنید."
        )

    plan = WeeklyPlan.objects.create(
        program_number=program_number,
        date=plan_date,
        status=WeeklyPlan.Status.DRAFT,
        planning_mode=WeeklyPlan.PlanningMode.SYSTEMIC,
        created_by=user,
        alarms="\n".join(alarms),
    )

    # Default mold-change: first Saturday (or plan weekday) on/after plan date
    target_weekday = 0  # شنبه
    candidates = mold_change_date_candidates(plan_date, target_weekday) or []
    change_date = candidates[0] if candidates else plan_date
    weekday = change_date.weekday() if hasattr(change_date, "weekday") else target_weekday

    seq_by_machine: dict[int, int] = {}
    created = 0
    for prop in proposals:
        if prop.machine is None:
            alarms.append(
                f"{prop.product.code}: بدون دستگاه — ردیف ساخته نشد."
            )
            continue
        mid = prop.machine.pk
        seq_by_machine[mid] = seq_by_machine.get(mid, 0) + 1
        item = WeeklyPlanItem.objects.create(
            plan=plan,
            subgroup=prop.product.subgroup,
            unit=prop.machine.unit,
            machine=prop.machine,
            product=prop.product,
            mold=None,
            mold_change_weekday=weekday,
            mold_change_date=change_date,
            active_cavities=prop.product.main_cavities or 1,
            sequence=seq_by_machine[mid],
            history_alarm=not FittingProduction.objects.filter(
                machine=prop.machine
            ).exists(),
        )
        cycle = int(prop.product.last_cycle or 0) or 30
        WeeklyPlanLine.objects.create(
            item=item,
            production_type=None,
            quantity=prop.produce_qty,
            cycle=cycle,
            active_cavities=prop.product.main_cavities or 1,
        )
        created += 1
        for w in prop.warnings:
            alarms.append(f"{prop.product.code}: {w}")
        if not prop.bom_ok:
            alarms.append(f"{prop.product.code}: {prop.bom_message}")

    refresh_plan_uids(plan)
    plan.alarms = "\n".join(alarms)
    if created == 0 and not alarms:
        plan.alarms = "برنامه سیستمی خالی ایجاد شد."
    plan.save(update_fields=["alarms"])
    return plan, alarms
