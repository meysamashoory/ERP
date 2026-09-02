"""Systemic (auto) weekly planning from orders + inventory + BOM + depot ceiling.

Forecast is loaded/stored but intentionally not applied yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from catalog.models import Machine, Product
from production.models import FittingProduction

from .models import CustomerOrder, WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
from .uid import refresh_plan_uids
from .utils import mold_change_date_candidates


@dataclass
class SystemicProposal:
    product: Product
    order_qty: int
    stock: int
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


def _bom_feasible(product: Product, produce_qty: int) -> tuple[bool, str]:
    lines = list(product.bom_lines.all())
    if not lines:
        return True, "BOM تعریف نشده — بدون محدودیت مواد."
    shortages: list[str] = []
    for line in lines:
        need = float(line.quantity or 0) * produce_qty
        if need <= 0:
            continue
        comp = None
        if line.component_code:
            comp = Product.objects.filter(code=line.component_code).first()
        if comp is None:
            shortages.append(
                f"جزء «{line.component_code or line.component_name}» در محصولات یافت نشد"
            )
            continue
        have = int(comp.stock_finished or 0) + int(comp.stock_unassembled or 0)
        if have < need:
            shortages.append(
                f"{comp.code}: نیاز {need:g} / موجود {have}"
            )
    if shortages:
        return False, "کسری BOM: " + "؛ ".join(shortages[:4])
    return True, "مواد BOM کافی است."


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

    # Sort by priority then code
    items = sorted(agg.items(), key=lambda kv: (kv[1]["priority"], kv[0]))
    for code, data in items:
        product = data.get("product") or Product.objects.filter(code=code).first()
        if product is None:
            # Skip unknown products — cannot place on plan without catalog product
            continue
        order_qty = int(data["quantity"])
        stock = int(product.stock_finished or 0)
        ceiling = product.depot_ceiling
        net = max(order_qty - stock, 0)
        produce = net
        warnings: list[str] = []
        if ceiling is not None:
            room = max(int(ceiling) - stock, 0)
            if produce > room:
                warnings.append(
                    f"سقف دپو {ceiling}: تولید از {produce} به {room} محدود شد."
                )
                produce = room
        if produce <= 0:
            continue

        bom_ok, bom_msg = _bom_feasible(product, produce)
        if not bom_ok:
            # Reduce to max feasible by materials (simple: skip if any shortage)
            warnings.append(bom_msg)
            # Still propose with warning — planner can review; qty kept but flagged
        machine = _suggest_machine(product, used_machines)
        if machine:
            used_machines.add(machine.pk)
        else:
            warnings.append("دستگاه تزریق آزاد یافت نشد.")

        proposals.append(
            SystemicProposal(
                product=product,
                order_qty=order_qty,
                stock=stock,
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
