"""Helpers for «سوابق تولید» list and detail views."""

from __future__ import annotations

from django.db.models import OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse

from core.natsort import natural_key
from planning.models import persian_weekday
from planning.utils import format_jdate
from production.sync import infer_history_status, status_label

from .models import ProductionDayEntry, ProductionHistoryRecord, ProductionProgram


def _fmt(value) -> str:
    if value in (None, ""):
        return "—"
    if hasattr(value, "strftime"):
        return format_jdate(value) or "—"
    return str(value)


def _num(value, default=0):
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _program_totals_from_annotated(program) -> dict:
    """Use list-query annotations when present; otherwise aggregate once."""
    produced = getattr(program, "agg_produced", None)
    planned = getattr(program, "agg_planned", None)
    seconds = getattr(program, "agg_seconds", None)
    if produced is None or planned is None or seconds is None:
        from .views import program_totals

        return program_totals(program)
    produced_i = int(produced or 0)
    planned_i = int(planned or 0)
    seconds_i = int(seconds or 0)
    return {
        "produced": produced_i,
        "planned": planned_i,
        "deviation": planned_i - produced_i,
        "hours": round(seconds_i / 3600, 1),
    }


def history_row_from_program(program: ProductionProgram) -> dict:
    item = program.item
    line = program.line
    totals = _program_totals_from_annotated(program)
    scrap = getattr(program, "agg_scrap", None)
    if scrap is None:
        scrap = program.entries.aggregate(s=Sum("scrap_quantity"))["s"]
    if scrap is None:
        scrap = 0
    last_cycle = getattr(program, "agg_last_cycle", None)
    last_cavities = getattr(program, "agg_last_cavities", None)
    if last_cycle is None or last_cavities is None:
        last_entry = program.entries.order_by("-date", "-id").first()
        if last_cycle is None:
            last_cycle = int(last_entry.cycle) if last_entry else 0
        if last_cavities is None:
            last_cavities = int(last_entry.active_cavities) if last_entry else 0
    planned_qty = int(line.quantity) if line else 0
    planned_cycle = int(line.cycle) if line and line.cycle else int(program.default_cycle or 0)
    active_cavities = (
        int(line.active_cavities)
        if line and line.active_cavities
        else int(item.active_cavities or 0)
    )
    planned_hours = float(line.production_hours) if line else 0.0
    mold_label = ""
    if program.mold_id:
        mold_label = str(program.mold)
    elif getattr(item, "mold_id", None):
        mold_label = str(item.mold)
    # Status for history list: date-based (end → finished; start → running; else awaiting).
    # Keep temp_stop from live program when that is the operational state.
    end_for_status = None
    if program.status == ProductionProgram.Status.FINISHED or program.stop_date:
        end_for_status = program.stop_date
    if program.status == ProductionProgram.Status.TEMP_STOP:
        status_code = ProductionProgram.Status.TEMP_STOP
    else:
        status_code = infer_history_status(
            actual_start=program.start_date,
            actual_end=end_for_status,
        )
    return {
        "kind": "live",
        "pk": program.pk,
        "detail_url": reverse("production_history_detail", args=[program.pk]),
        "change_uid": (program.resolved_uid or item.uid or "").strip(),
        "plan_number": item.plan.program_number,
        "plan_date": item.plan.date,
        "plan_date_display": _fmt(item.plan.date),
        "machine": program.machine_label,
        "unit_number": item.machine.unit.number,
        "machine_number": item.machine.number,
        "product_code": item.product.code,
        "product_name": item.product.name,
        "mold_number": "—",
        "unique_code": "—",
        "mold_label": mold_label or "—",
        "plan_start_date": item.mold_change_date,
        "plan_start_display": _fmt(item.mold_change_date),
        "actual_start_date": program.start_date,
        "actual_start_display": _fmt(program.start_date),
        "actual_end_date": end_for_status,
        "actual_end_display": _fmt(end_for_status) if end_for_status else "—",
        "planned_qty": planned_qty,
        "actual_qty": int(totals["produced"] or 0),
        "planned_cycle": planned_cycle,
        "last_cycle": int(last_cycle or 0),
        "planned_hours": planned_hours,
        "planned_hours_display": f"{planned_hours:g}" if planned_hours else "0",
        "active_cavities": active_cavities,
        "last_cavities": int(last_cavities or 0),
        "scrap": int(scrap or 0),
        "status_code": status_code,
        "status_label": status_label(status_code),
        "program": program,
        "archive": None,
    }


def history_row_from_archive(rec: ProductionHistoryRecord) -> dict:
    machine_bits = []
    if rec.machine_number:
        machine_bits.append(f"دستگاه {rec.machine_number}")
    if rec.unit_number:
        machine_bits.append(f"واحد {rec.unit_number}")
    machine = " ".join(machine_bits) or "—"
    plan_start = rec.plan_start_date or rec.mold_change_date
    status_code = infer_history_status(
        actual_start=rec.actual_start_date,
        actual_end=rec.actual_end_date,
    )
    return {
        "kind": "archive",
        "pk": rec.pk,
        "detail_url": reverse("production_history_archive_detail", args=[rec.pk]),
        "change_uid": (rec.program_uid or "").strip(),
        "plan_number": rec.plan_number or "—",
        "plan_date": rec.plan_date,
        "plan_date_display": _fmt(rec.plan_date),
        "machine": machine,
        "unit_number": rec.unit_number,
        "machine_number": rec.machine_number,
        "product_code": rec.product_code or "—",
        "product_name": rec.product_name or "—",
        "mold_number": rec.mold_number or "—",
        "unique_code": rec.unique_code or "—",
        "plan_start_date": plan_start,
        "plan_start_display": _fmt(plan_start),
        "actual_start_date": rec.actual_start_date,
        "actual_start_display": _fmt(rec.actual_start_date),
        "actual_end_date": rec.actual_end_date,
        "actual_end_display": _fmt(rec.actual_end_date),
        "planned_qty": _num(rec.planned_qty, 0),
        "actual_qty": _num(rec.produced_qty, 0),
        "planned_cycle": _num(rec.planned_cycle, 0),
        "last_cycle": _num(rec.last_cycle, 0),
        "planned_hours": float(rec.planned_hours) if rec.planned_hours is not None else 0,
        "planned_hours_display": (
            f"{float(rec.planned_hours):g}" if rec.planned_hours is not None else "0"
        ),
        "active_cavities": _num(rec.active_cavities, 0),
        "last_cavities": _num(rec.last_cavities, 0),
        "scrap": _num(rec.scrap_qty, 0),
        "mold_label": rec.mold_name or "—",
        "status_code": status_code,
        "status_label": status_label(status_code),
        "program": None,
        "archive": rec,
    }


def build_history_rows() -> list[dict]:
    """All live programs (any status) + Excel archives not covered by live UIDs.

    Uses annotated aggregates (one query) instead of per-program N+1 aggregates.
    Does not sync planning or scan conflicts — those run on Excel transfer/update.
    """
    rows: list[dict] = []
    live_uids: set[str] = set()
    latest_entry = ProductionDayEntry.objects.filter(program_id=OuterRef("pk")).order_by(
        "-date", "-id"
    )
    programs = (
        ProductionProgram.objects.select_related(
            "item__product",
            "item__machine__unit",
            "item__plan",
            "item__mold",
            "mold",
        )
        .prefetch_related("item__lines")
        .annotate(
            agg_produced=Coalesce(Sum("entries__produced_quantity"), 0),
            agg_planned=Coalesce(Sum("entries__planned_quantity"), 0),
            agg_seconds=Coalesce(Sum("entries__active_seconds"), 0),
            agg_scrap=Coalesce(Sum("entries__scrap_quantity"), 0),
            agg_last_cycle=Subquery(latest_entry.values("cycle")[:1]),
            agg_last_cavities=Subquery(latest_entry.values("active_cavities")[:1]),
        )
    )
    for program in programs:
        row = history_row_from_program(program)
        if row["change_uid"]:
            live_uids.add(row["change_uid"])
        rows.append(row)

    for rec in ProductionHistoryRecord.objects.all().iterator(chunk_size=500):
        uid = (rec.program_uid or "").strip()
        if uid and uid in live_uids:
            continue
        rows.append(history_row_from_archive(rec))

    rows.sort(
        key=lambda r: (
            natural_key(r.get("plan_number") or ""),
            natural_key(r.get("change_uid") or ""),
            r.get("kind") or "",
            r.get("pk") or 0,
        )
    )
    return rows


def entry_detail_rows(program: ProductionProgram) -> list[dict]:
    """Per-document rows for history detail, with calculated deviations."""
    out = []
    for entry in program.entries.select_related("deviation_reason").order_by("date", "id"):
        qty_dev = entry.deviation
        planned_time = int(entry.planned_quantity or 0) * int(entry.cycle or 0)
        actual_time = int(entry.active_seconds or 0)
        time_dev = actual_time - planned_time
        reason = entry.deviation_reason.label if entry.deviation_reason_id else "—"
        out.append(
            {
                "date": entry.date,
                "date_display": _fmt(entry.date),
                "produced": entry.produced_quantity or 0,
                "scrap": entry.scrap_quantity or 0,
                "qty_deviation": qty_dev,
                "qty_reason": reason,
                "time_deviation": time_dev,
                "time_reason": "—" if time_dev == 0 else reason,
                "description": (entry.description or "").strip() or "—",
                "planned": entry.planned_quantity or 0,
                "cycle": entry.cycle or 0,
                "active_cavities": entry.active_cavities or 0,
            }
        )
    return out


def program_summary_text(program: ProductionProgram) -> str:
    item = program.item
    line = program.line
    name = item.product.name
    actual = program.start_date
    if actual:
        day_name = persian_weekday(actual)
        date_part = f"{_fmt(actual)} ({day_name})"
    else:
        date_part = "تاریخ شروع واقعی ثبت نشده"
    machine = program.machine_label
    planned_qty = int(line.quantity) if line else 0
    planned_cycle = int(line.cycle) if line and line.cycle else int(program.default_cycle or 0)
    hours = float(line.production_hours) if line else 0.0
    cavities = (
        int(line.active_cavities)
        if line and line.active_cavities
        else int(item.active_cavities or 0)
    )
    return (
        f"نام جنس: {name} — تاریخ و روز تعویض واقعی: {date_part} — "
        f"دستگاه تولید: {machine} — آمار برنامه: مقدار {planned_qty} عدد، "
        f"سیکل {planned_cycle} ثانیه، ساعت تولید {hours:g}، حفره فعال {cavities}"
    )


def archive_summary_text(rec: ProductionHistoryRecord) -> str:
    name = rec.product_name or "—"
    actual = rec.actual_start_date
    if actual:
        day_name = persian_weekday(actual)
        date_part = f"{_fmt(actual)} ({day_name})"
    else:
        date_part = "ثبت نشده"
    machine_bits = []
    if rec.machine_number:
        machine_bits.append(f"دستگاه {rec.machine_number}")
    if rec.unit_number:
        machine_bits.append(f"واحد {rec.unit_number}")
    machine = " ".join(machine_bits) or "—"
    hours = float(rec.planned_hours) if rec.planned_hours is not None else 0
    return (
        f"نام جنس: {name} — تاریخ و روز تعویض واقعی: {date_part} — "
        f"دستگاه تولید: {machine} — آمار برنامه: مقدار {_num(rec.planned_qty, 0)} عدد، "
        f"سیکل {_num(rec.planned_cycle, 0)} ثانیه، ساعت تولید {hours:g}، "
        f"حفره فعال {_num(rec.active_cavities, 0)}"
    )


def entry_detail_rows_from_archive(rec: ProductionHistoryRecord) -> list[dict]:
    payload = rec.extra if isinstance(rec.extra, dict) else {}
    snaps = payload.get("day_entries") or []
    out = []
    for snap in snaps:
        if not isinstance(snap, dict):
            continue
        out.append(
            {
                "date": snap.get("date"),
                "date_display": snap.get("date_display") or _fmt(snap.get("date")) or "—",
                "produced": _num(snap.get("produced"), 0),
                "scrap": _num(snap.get("scrap"), 0),
                "qty_deviation": _num(snap.get("qty_deviation"), 0),
                "qty_reason": snap.get("qty_reason") or "—",
                "time_deviation": _num(snap.get("time_deviation"), 0),
                "time_reason": snap.get("time_reason") or "—",
                "description": (snap.get("description") or "").strip() or "—",
            }
        )
    return out
