"""Detect in-production overlaps (running / temp_stop only) with precise fix links.

Conflict rule (business):
A machine may have at most one mold that currently occupies it.

Occupying statuses:
- در حال تولید (running): has actual start, no actual end
- توقف موقت (temp_stop): same date shape, explicit temp-stop status

Non-occupying (never a conflict by themselves):
- در انتظار تولید (awaiting): no actual start and no actual end
- اتمام تولید (finished): has actual end
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from .models import ProductionHistoryRecord, ProductionProgram
from .sync import _normalize_status_label, resolve_machine, status_label


OCCUPYING = frozenset({"running", "temp_stop"})


@dataclass
class ConflictLink:
    label: str
    url: str
    status: str
    uid: str = ""
    machine_label: str = ""
    product: str = ""
    actual_start: str = ""
    kind: str = ""  # live | history


@dataclass
class ConflictItem:
    machine_label: str
    message: str
    links: list[dict]


def occupancy_status(
    *,
    actual_start,
    actual_end,
    status_text: str = "",
) -> str | None:
    """Return ``running`` / ``temp_stop`` if the mold occupies the machine, else None."""
    hinted = _normalize_status_label(status_text or "")
    if actual_end or hinted == "finished":
        return None
    if hinted == "temp_stop":
        # Temp stop occupies the machine even if start is missing in messy Excel rows.
        return "temp_stop"
    if hinted == "awaiting" and not actual_start:
        return None
    if actual_start and not actual_end:
        return "running"
    return None


def _fmt_date(value) -> str:
    if value is None:
        return "—"
    try:
        from catalog.jalali_dates import storage_to_jalali

        j = storage_to_jalali(value)
        if j is not None:
            return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
    except Exception:  # noqa: BLE001
        pass
    return str(value)


def _live_occupying_qs():
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


def _entry_dict(
    *,
    kind: str,
    uid: str,
    label: str,
    url: str,
    machine_label: str,
    status_code: str,
    product: str = "",
    actual_start=None,
) -> dict:
    return {
        "kind": kind,
        "uid": uid,
        "label": label,
        "url": url,
        "machine_label": machine_label,
        "status": status_label(status_code),
        "status_code": status_code,
        "product": product,
        "actual_start": _fmt_date(actual_start),
    }


def collect_machine_occupancy() -> dict[int, list[dict]]:
    """Map machine_id → occupying live/history entries (running/temp_stop only)."""
    by_machine: dict[int, list[dict]] = {}

    for prog in _live_occupying_qs():
        mid = prog.item.machine_id
        if not mid:
            continue
        status_code = prog.status
        if status_code not in OCCUPYING:
            continue
        uid = (prog.resolved_uid or "").strip() or f"#{prog.pk}"
        product = ""
        try:
            product = prog.item.product.name
        except Exception:  # noqa: BLE001
            product = ""
        by_machine.setdefault(mid, []).append(
            _entry_dict(
                kind="live",
                uid=uid,
                label=(
                    f"برنامه زنده «{uid}» — {product or '—'} "
                    f"[{status_label(status_code)}] · شروع واقعی {_fmt_date(prog.start_date)}"
                ),
                url=_program_fix_url(prog),
                machine_label=prog.machine_label,
                status_code=status_code,
                product=product,
                actual_start=prog.start_date,
            )
        )

    for rec in ProductionHistoryRecord.objects.filter(
        actual_end_date__isnull=True
    ).iterator(chunk_size=400):
        status_code = occupancy_status(
            actual_start=rec.actual_start_date,
            actual_end=rec.actual_end_date,
            status_text=getattr(rec, "status", "") or "",
        )
        if status_code not in OCCUPYING:
            continue
        machine = resolve_machine(
            unit_number=rec.unit_number, machine_number=rec.machine_number
        )
        if not machine:
            continue
        uid = (rec.program_uid or "").strip()
        existing = by_machine.get(machine.pk, [])
        if uid and any(e.get("uid") == uid and e.get("kind") == "live" for e in existing):
            # Same mold already represented by live program
            continue
        if uid and any(e.get("uid") == uid and e.get("kind") == "history" for e in existing):
            continue
        product = (rec.product_name or rec.product_code or "").strip() or "—"
        machine_label = f"دستگاه {machine.number} واحد {machine.unit.number}"
        by_machine.setdefault(machine.pk, []).append(
            _entry_dict(
                kind="history",
                uid=uid or f"H{rec.pk}",
                label=(
                    f"سابقه اکسل «{uid or rec.pk}» — {product} "
                    f"[{status_label(status_code)}] · شروع واقعی {_fmt_date(rec.actual_start_date)} "
                    f"· ویرایش: /production/history/archive/{rec.pk}/"
                ),
                url=_history_fix_url(rec),
                machine_label=machine_label,
                status_code=status_code,
                product=product,
                actual_start=rec.actual_start_date,
            )
        )

    return by_machine


def collect_in_production_conflicts() -> list[ConflictItem]:
    """Machines with more than one occupying mold (running / temp_stop)."""
    by_machine = collect_machine_occupancy()
    conflicts: list[ConflictItem] = []
    for _mid, entries in by_machine.items():
        if len(entries) < 2:
            continue
        machine_label = entries[0]["machine_label"]
        bits = []
        for i, e in enumerate(entries, start=1):
            bits.append(
                f"{i}) شناسه «{e['uid']}» · {e.get('product') or '—'} · "
                f"{e['status']} · شروع واقعی {e.get('actual_start') or '—'}"
            )
        conflicts.append(
            ConflictItem(
                machine_label=machine_label,
                message=(
                    f"تداخل روی «{machine_label}»: بیش از یک قالب در وضعیت "
                    f"«در حال تولید» یا «توقف موقت» هم‌زمان روی این دستگاه است. "
                    f"موارد متداخل: " + " | ".join(bits)
                ),
                links=[
                    {
                        "label": e["label"],
                        "url": e["url"],
                        "status": e["status"],
                        "uid": e["uid"],
                        "product": e.get("product") or "",
                        "actual_start": e.get("actual_start") or "",
                        "kind": e.get("kind") or "",
                    }
                    for e in entries
                ],
            )
        )
    return conflicts


def conflicts_as_dicts(conflicts: list[ConflictItem] | None = None) -> list[dict]:
    items = conflicts if conflicts is not None else collect_in_production_conflicts()
    return [
        {
            "machine_label": c.machine_label,
            "message": c.message,
            "links": c.links,
        }
        for c in items
    ]


def history_conflict_uids() -> set[str]:
    """UIDs involved in any current occupancy conflict (for list highlighting)."""
    out: set[str] = set()
    for c in collect_in_production_conflicts():
        for link in c.links:
            uid = (link.get("uid") or "").strip()
            if uid and not uid.startswith("#") and not uid.startswith("H"):
                out.add(uid)
            elif uid.startswith("H"):
                out.add(uid)
    return out
