"""Detect in-production overlaps and build fix links (live + Excel history)."""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from .models import ProductionHistoryRecord, ProductionProgram
from .sync import infer_history_status, resolve_machine


@dataclass
class ConflictItem:
    machine_label: str
    message: str
    links: list[dict]  # {label, url}


def _live_in_production_qs():
    """Programs considered in production / temp stop (no finished end)."""
    return (
        ProductionProgram.objects.filter(
            status__in=[
                ProductionProgram.Status.RUNNING,
                ProductionProgram.Status.TEMP_STOP,
            ]
        )
        .select_related("item__machine__unit", "item__product", "item__plan")
        .prefetch_related("item__lines")
    )


def _program_fix_url(program: ProductionProgram) -> str:
    return reverse("program_status", args=[program.pk])


def _history_fix_url(rec: ProductionHistoryRecord) -> str:
    return reverse("production_history_archive_detail", args=[rec.pk])


def collect_in_production_conflicts() -> list[ConflictItem]:
    """Find machines with more than one in-production program/history row."""
    by_machine: dict[int, list[dict]] = {}

    for prog in _live_in_production_qs():
        mid = prog.item.machine_id
        if not mid:
            continue
        by_machine.setdefault(mid, []).append(
            {
                "kind": "live",
                "uid": (prog.resolved_uid or "").strip() or f"#{prog.pk}",
                "label": f"برنامه زنده «{prog.resolved_uid}» — {prog.item.product.name}",
                "url": _program_fix_url(prog),
                "machine_label": prog.machine_label,
                "status": prog.get_status_display(),
            }
        )

    for rec in ProductionHistoryRecord.objects.filter(
        actual_end_date__isnull=True,
        actual_start_date__isnull=False,
    ).exclude(plan_number="").iterator(chunk_size=300):
        # In production from Excel: started and no actual end date
        status = infer_history_status(
            actual_start=rec.actual_start_date, actual_end=rec.actual_end_date
        )
        if status != "running":
            continue
        machine = resolve_machine(
            unit_number=rec.unit_number, machine_number=rec.machine_number
        )
        if not machine:
            continue
        uid = (rec.program_uid or "").strip()
        # Skip if already represented by live program with same UID
        existing = by_machine.get(machine.pk, [])
        if uid and any(e.get("uid") == uid for e in existing):
            continue
        by_machine.setdefault(machine.pk, []).append(
            {
                "kind": "history",
                "uid": uid or f"H{rec.pk}",
                "label": f"سابقه اکسل «{uid or rec.pk}» — {rec.product_name or rec.product_code}",
                "url": _history_fix_url(rec),
                "machine_label": f"دستگاه {machine.number} واحد {machine.unit.number}",
                "status": "در حال تولید (اکسل)",
            }
        )

    conflicts: list[ConflictItem] = []
    for _mid, entries in by_machine.items():
        if len(entries) < 2:
            continue
        machine_label = entries[0]["machine_label"]
        uids = "، ".join(e["uid"] for e in entries)
        conflicts.append(
            ConflictItem(
                machine_label=machine_label,
                message=(
                    f"تداخل تولید روی «{machine_label}»: بیش از یک برنامه بدون تاریخ "
                    f"پایان واقعی هم‌زمان فعال است ({uids})."
                ),
                links=[
                    {"label": e["label"], "url": e["url"], "status": e["status"]}
                    for e in entries
                ],
            )
        )
    return conflicts
