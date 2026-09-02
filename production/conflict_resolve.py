"""Apply conflict-resolution edits across history, live production, and planning."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from catalog.models import Machine, MoldOption, ProductionUnit
from catalog.jalali_dates import coerce_to_jalali_storage
from production.models import ProductionHistoryRecord, ProductionProgram
from production.sync import (
    delete_history_archive_and_live,
    infer_history_status,
    status_label,
)


def _parse_jdate(raw: str):
    text = (raw or "").strip()
    if not text:
        return None
    return coerce_to_jalali_storage(text)


def _find_live_and_history(ref: str):
    kind, _, pk_s = ref.partition(":")
    try:
        pk = int(pk_s)
    except (TypeError, ValueError):
        return None, None, "شناسه نامعتبر است."
    prog = None
    rec = None
    if kind == "live":
        prog = (
            ProductionProgram.objects.select_related(
                "item__product", "item__machine__unit", "item__plan", "item__mold"
            )
            .prefetch_related("item__lines")
            .filter(pk=pk)
            .first()
        )
        if prog is None:
            return None, None, "برنامه زنده یافت نشد."
        uid = (prog.resolved_uid or "").strip()
        if uid:
            rec = ProductionHistoryRecord.objects.filter(program_uid=uid).first()
    elif kind == "history":
        rec = ProductionHistoryRecord.objects.filter(pk=pk).first()
        if rec is None:
            return None, None, "سابقه یافت نشد."
        uid = (rec.program_uid or "").strip()
        if uid:
            prog = (
                ProductionProgram.objects.select_related(
                    "item__product", "item__machine__unit", "item__plan", "item__mold"
                )
                .prefetch_related("item__lines")
                .filter(item__lines__uid=uid)
                .distinct()
                .first()
            )
    else:
        return None, None, "نوع مرجع نامعتبر است."
    return prog, rec, ""


@transaction.atomic
def apply_conflict_fix(data, *, user=None) -> dict[str, Any]:
    action = (data.get("action") or "").strip()
    ref = (data.get("ref") or "").strip()
    if not ref:
        return {"ok": False, "message": "مورد انتخاب نشده است."}

    if action == "delete":
        return _delete_party(ref)

    if action != "save":
        return {"ok": False, "message": "عملیات نامعتبر است."}

    prog, rec, err = _find_live_and_history(ref)
    if err:
        return {"ok": False, "message": err}

    mold_id = (data.get("mold_id") or "").strip()
    mold = None
    if mold_id:
        mold = MoldOption.objects.filter(pk=mold_id).first()

    actual_start = _parse_jdate(data.get("actual_start") or "")
    actual_end = _parse_jdate(data.get("actual_end") or "")
    unit_raw = (data.get("unit_number") or "").strip()
    machine_raw = (data.get("machine_number") or "").strip()

    # Combined «6/1» support
    if "/" in machine_raw or "-" in machine_raw or "دستگاه" in machine_raw:
        from catalog.qty_parse import parse_unit_machine_label

        u, m = parse_unit_machine_label(machine_raw)
        if u is not None:
            unit_raw = str(u)
        if m:
            machine_raw = m
    if "/" in unit_raw:
        from catalog.qty_parse import parse_unit_machine_label

        u, m = parse_unit_machine_label(unit_raw)
        if u is not None:
            unit_raw = str(u)
        if m and not machine_raw:
            machine_raw = m

    unit_n = None
    if unit_raw:
        try:
            unit_n = int(unit_raw)
        except ValueError:
            return {"ok": False, "message": "شماره واحد نامعتبر است."}

    machine = None
    if unit_n is not None and machine_raw:
        unit = ProductionUnit.objects.filter(number=unit_n).first()
        if unit:
            digits = "".join(ch for ch in machine_raw if ch.isdigit())
            mach_n = str(int(digits)) if digits else machine_raw.strip()
            machine = (
                Machine.objects.filter(unit=unit, number=mach_n).order_by("id").first()
            )

    # Apply to live program / plan item
    if prog is not None:
        item = prog.item
        if mold is not None:
            item.mold = mold
            prog.mold = mold
            item.save(update_fields=["mold"])
            for line in item.lines.all():
                line.mold = mold
                line.save(update_fields=["mold"])
        if machine is not None:
            item.machine = machine
            item.unit = machine.unit
            item.save(update_fields=["machine", "unit"])
        if actual_start is not None:
            prog.start_date = actual_start
            if not prog.start_time:
                from datetime import time as dtime

                prog.start_time = dtime(8, 0)
        if actual_end is not None:
            prog.stop_date = actual_end
            if not prog.stop_time:
                from datetime import time as dtime

                prog.stop_time = dtime(20, 0)
            prog.status = ProductionProgram.Status.FINISHED
        elif actual_start is not None and prog.status == ProductionProgram.Status.AWAITING:
            prog.status = ProductionProgram.Status.RUNNING
        prog.save()

    # Apply to archive history
    if rec is not None:
        if mold is not None:
            rec.mold_name = str(mold)
            rec.mold_number = str(getattr(mold, "code", "") or mold.pk)
        if unit_n is not None:
            rec.unit_number = unit_n
        if machine_raw:
            digits = "".join(ch for ch in machine_raw if ch.isdigit())
            rec.machine_number = str(int(digits)) if digits else machine_raw
        if "actual_start" in data:
            rec.actual_start_date = actual_start
        if "actual_end" in data:
            rec.actual_end_date = actual_end
        # Refresh status label from dates
        inferred = infer_history_status(
            actual_start=rec.actual_start_date,
            actual_end=rec.actual_end_date,
            status_text=rec.status or "",
        )
        rec.status = status_label(inferred)
        rec.save()

    return {"ok": True, "message": "تغییرات در سوابق، ثبت تولید و برنامه‌ریزی اعمال شد."}


@transaction.atomic
def _delete_party(ref: str) -> dict[str, Any]:
    prog, rec, err = _find_live_and_history(ref)
    if err:
        return {"ok": False, "message": err}

    if rec is not None:
        delete_history_archive_and_live(rec)
        return {"ok": True, "message": "ردیف از سوابق تولید، ثبت تولید و برنامه‌ریزی حذف شد."}

    if prog is not None:
        item = prog.item
        plan = item.plan if item else None
        prog.delete()
        if item is not None and not ProductionProgram.objects.filter(item=item).exists():
            item.delete()
            if plan is not None and not plan.items.exists():
                # Keep weekly plan shell (date unique) — only remove empty excel stubs optionally
                pass
        return {"ok": True, "message": "ردیف از ثبت تولید و برنامه‌ریزی حذف شد."}

    return {"ok": False, "message": "موردی برای حذف یافت نشد."}
