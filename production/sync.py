"""Sync production history ↔ weekly planning and conflict alarms."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import jdatetime
from django.db import transaction

from catalog.alarms import register_alarm
from catalog.models import Machine, Product, ProductionUnit, SystemAlarm


def infer_history_status(*, actual_start, actual_end) -> str:
    """Status from dates: end → finished; start only → running; else awaiting."""
    if actual_end:
        return "finished"
    if actual_start:
        return "running"
    return "awaiting"


def status_label(code: str) -> str:
    return {
        "finished": "اتمام تولید",
        "running": "در حال تولید",
        "awaiting": "در انتظار تولید",
        "temp_stop": "توقف موقت",
    }.get(code or "", code or "—")


def _to_jdate(value):
    """Convert history DateField / jDateField values to ``jdatetime.date``."""
    from catalog.jalali_dates import storage_to_jalali

    return storage_to_jalali(value)


def _to_gdate(value):
    j = _to_jdate(value)
    if j is None:
        return None
    return j.togregorian()


def resolve_machine(*, unit_number, machine_number) -> Machine | None:
    if unit_number is None or machine_number in (None, ""):
        return None
    unit = ProductionUnit.objects.filter(number=int(unit_number)).first()
    if not unit:
        return None
    return (
        Machine.objects.filter(unit=unit, number=str(machine_number).strip())
        .order_by("id")
        .first()
    )


def resolve_product(*, code: str, name: str = "") -> Product | None:
    code = (code or "").strip()
    if code:
        product = Product.objects.filter(code=code).first()
        if product:
            return product
    name = (name or "").strip()
    if name:
        return Product.objects.filter(name=name).first()
    return None


def _next_free_plan_date(preferred):
    """WeeklyPlan.date is unique — bump until free."""
    d = _to_jdate(preferred) or jdatetime.date.today()
    from planning.models import WeeklyPlan

    for _ in range(370):
        if not WeeklyPlan.objects.filter(date=d).exists():
            return d
        d = d + timedelta(days=1)
    return d


def _live_program_uids() -> set[str]:
    from production.models import ProductionProgram

    uids: set[str] = set()
    for prog in ProductionProgram.objects.select_related("item").prefetch_related(
        "item__lines"
    ):
        uid = (prog.resolved_uid or "").strip()
        if uid:
            uids.add(uid)
    return uids


def _planning_line_uids() -> set[str]:
    from planning.models import WeeklyPlanLine

    return {
        (u or "").strip()
        for u in WeeklyPlanLine.objects.exclude(uid="").values_list("uid", flat=True)
        if (u or "").strip()
    }


def _normalize_status_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.replace("ي", "ی").replace("ك", "ک").lower()
    mapping = {
        "finished": "finished",
        "اتمام": "finished",
        "اتمام تولید": "finished",
        "پایان": "finished",
        "running": "running",
        "در حال تولید": "running",
        "درحال تولید": "running",
        "awaiting": "awaiting",
        "در انتظار": "awaiting",
        "در انتظار تولید": "awaiting",
        "temp_stop": "temp_stop",
        "توقف موقت": "temp_stop",
    }
    if low in mapping:
        return mapping[low]
    for key, code in mapping.items():
        if key in low:
            return code
    return text


def _apply_program_state_from_history(rec, program) -> None:
    """Update live ProductionProgram status/dates from archive history row."""
    from production.models import ProductionProgram

    status_hint = _normalize_status_label(getattr(rec, "status", "") or "")
    if status_hint in {
        ProductionProgram.Status.FINISHED,
        ProductionProgram.Status.RUNNING,
        ProductionProgram.Status.AWAITING,
        ProductionProgram.Status.TEMP_STOP,
    }:
        inferred = status_hint
    else:
        inferred = infer_history_status(
            actual_start=rec.actual_start_date,
            actual_end=rec.actual_end_date,
        )
    if inferred == "finished":
        program.status = ProductionProgram.Status.FINISHED
    elif inferred == "running":
        program.status = ProductionProgram.Status.RUNNING
    elif inferred == "temp_stop":
        program.status = ProductionProgram.Status.TEMP_STOP
    else:
        program.status = ProductionProgram.Status.AWAITING

    start_j = _to_jdate(rec.actual_start_date)
    end_j = _to_jdate(rec.actual_end_date)
    if start_j:
        program.start_date = start_j
        if not program.start_time:
            from datetime import time as dtime

            program.start_time = dtime(8, 0)
    if end_j:
        program.stop_date = end_j
        if not program.stop_time:
            from datetime import time as dtime

            program.stop_time = dtime(20, 0)
    program.save()


def _sync_history_quantities_to_program(rec, program, *, user=None) -> int:
    """Mirror archive day_entries / produced totals into ProductionDayEntry rows.

    Returns number of day entries written/updated.
    """
    from catalog.jalali_dates import coerce_to_jalali_storage, storage_to_jalali
    from production.models import ProductionDayEntry

    extra = rec.extra if isinstance(rec.extra, dict) else {}
    snaps = list(extra.get("day_entries") or [])
    written = 0

    def _upsert(work_j, produced: int, scrap: int, description: str = "") -> None:
        nonlocal written
        if work_j is None:
            return
        entry, _created = ProductionDayEntry.objects.get_or_create(
            program=program,
            date=work_j,
            defaults={
                "produced_quantity": max(0, int(produced or 0)),
                "scrap_quantity": max(0, int(scrap or 0)),
                "description": (description or "").strip(),
                "created_by": user,
            },
        )
        if not _created:
            entry.produced_quantity = max(0, int(produced or 0))
            entry.scrap_quantity = max(0, int(scrap or 0))
            if description:
                entry.description = description.strip()
            entry.save()
        try:
            entry.recompute()
            entry.save()
        except Exception:  # noqa: BLE001
            pass
        written += 1

    if snaps:
        for snap in snaps:
            if not isinstance(snap, dict):
                continue
            raw_date = snap.get("date") or snap.get("date_display")
            work_j = storage_to_jalali(coerce_to_jalali_storage(raw_date) or raw_date)
            if work_j is None and isinstance(raw_date, str) and raw_date:
                # try jalali slash already-encoded ISO-like 1405-06-01
                try:
                    parts = raw_date.replace("/", "-").split("-")
                    if len(parts) == 3:
                        work_j = storage_to_jalali(
                            __import__("datetime").date(
                                int(parts[0]), int(parts[1]), int(parts[2])
                            )
                        )
                except Exception:  # noqa: BLE001
                    work_j = None
            _upsert(
                work_j,
                int(snap.get("produced") or 0),
                int(snap.get("scrap") or 0),
                str(snap.get("description") or ""),
            )
    elif rec.produced_qty or rec.scrap_qty:
        work_j = _to_jdate(rec.actual_start_date) or _to_jdate(rec.plan_date) or program.start_date
        _upsert(work_j, int(rec.produced_qty or 0), int(rec.scrap_qty or 0))

    return written


def _find_program_by_uid(uid: str):
    from production.models import ProductionProgram

    if not uid:
        return None
    prog = (
        ProductionProgram.objects.select_related("item")
        .filter(item__lines__uid=uid)
        .distinct()
        .first()
    )
    if prog is not None:
        return prog
    for p in ProductionProgram.objects.select_related("item").prefetch_related("item__lines"):
        if (p.resolved_uid or "").strip() == uid:
            return p
    return None


@transaction.atomic
def sync_history_record_to_planning(
    rec, *, user=None, live_uids: set[str] | None = None
) -> dict[str, Any]:
    """Ensure a WeeklyPlan + item + program exist for this archive row.

    Plans are keyed by ``plan_number`` (شماره برنامه): multiple history rows with
    the same plan number become items under that single weekly plan.

    Returns {ok, plan_id, program_id, created, error}.
    """
    from catalog.jalali_dates import coerce_to_jalali_storage
    from planning.models import WeeklyPlan, WeeklyPlanItem, WeeklyPlanLine
    from planning.models import Weekday
    from production.models import ProductionProgram

    result: dict[str, Any] = {"ok": False, "created": False, "error": ""}
    uid = (rec.program_uid or "").strip()
    plan_number = (rec.plan_number or "").strip()
    if not plan_number:
        result["error"] = "شماره برنامه خالی است."
        return result

    # Repair accidental Gregorian storage on the archive row (years ≥ 1600).
    dirty_fields: list[str] = []
    for field in (
        "plan_date",
        "mold_change_date",
        "plan_start_date",
        "actual_start_date",
        "actual_end_date",
    ):
        raw = getattr(rec, field, None)
        fixed = coerce_to_jalali_storage(raw)
        if raw is not None and fixed is not None and fixed != raw:
            setattr(rec, field, fixed)
            dirty_fields.append(field)
    if dirty_fields:
        rec.save(update_fields=[*dirty_fields, "updated_at"])

    if live_uids is None:
        live_uids = _live_program_uids()
    if uid and uid in live_uids:
        prog = _find_program_by_uid(uid)
        if prog is not None:
            _apply_program_state_from_history(rec, prog)
            _sync_history_quantities_to_program(rec, prog, user=user)
            result["ok"] = True
            result["program_id"] = prog.pk
            result["plan_id"] = prog.item.plan_id
            result["error"] = "live"
            return result

    product = resolve_product(code=rec.product_code, name=rec.product_name)
    machine = resolve_machine(unit_number=rec.unit_number, machine_number=rec.machine_number)
    if not product:
        result["error"] = f"کالای «{rec.product_code or rec.product_name}» در کاتالوگ یافت نشد."
        return result
    if not machine:
        result["error"] = (
            f"دستگاه «{rec.machine_number}» واحد «{rec.unit_number}» یافت نشد."
        )
        return result

    plan = WeeklyPlan.objects.filter(program_number=plan_number).first()
    if not plan:
        plan_date = _to_jdate(rec.plan_date) or jdatetime.date.today()
        # date must be unique
        if WeeklyPlan.objects.filter(date=plan_date).exclude(program_number=plan_number).exists():
            plan_date = _next_free_plan_date(plan_date)
        plan = WeeklyPlan.objects.create(
            program_number=plan_number,
            date=plan_date,
            status=WeeklyPlan.Status.APPROVED,
            created_by=user,
            approved_by=user,
        )
        result["created"] = True
    else:
        # Keep plan date in sync when archive has a usable شمسی date
        jd = _to_jdate(rec.plan_date)
        if jd and plan.date != jd:
            conflict = (
                WeeklyPlan.objects.filter(date=jd)
                .exclude(pk=plan.pk)
                .exists()
            )
            if not conflict:
                plan.date = jd
                plan.save(update_fields=["date"])

    mold_change = _to_jdate(rec.plan_start_date or rec.mold_change_date) or plan.date
    weekday = mold_change.weekday() if hasattr(mold_change, "weekday") else Weekday.SHANBE

    item = None
    if uid:
        item = (
            WeeklyPlanItem.objects.filter(plan=plan, lines__uid=uid)
            .distinct()
            .first()
        )
    if item is None:
        item = WeeklyPlanItem.objects.create(
            plan=plan,
            subgroup=product.subgroup,
            unit=machine.unit,
            machine=machine,
            product=product,
            mold_change_weekday=weekday,
            mold_change_date=mold_change,
            active_cavities=int(rec.active_cavities or 1),
            sequence=int(rec.sequence or 1),
        )
        WeeklyPlanLine.objects.create(
            item=item,
            quantity=int(rec.planned_qty or 0),
            cycle=int(rec.planned_cycle or 0),
            active_cavities=int(rec.active_cavities or 1),
            uid=uid,
        )
        result["created"] = True
    else:
        item.machine = machine
        item.unit = machine.unit
        item.product = product
        item.subgroup = product.subgroup
        item.mold_change_date = mold_change
        item.mold_change_weekday = weekday
        item.active_cavities = int(rec.active_cavities or item.active_cavities or 1)
        if rec.sequence:
            item.sequence = int(rec.sequence)
        item.save()
        line = item.lines.order_by("id").first()
        if line:
            if rec.planned_qty is not None:
                line.quantity = int(rec.planned_qty)
            if rec.planned_cycle is not None:
                line.cycle = int(rec.planned_cycle)
            if rec.active_cavities is not None:
                line.active_cavities = int(rec.active_cavities)
            if uid and not line.uid:
                line.uid = uid
            line.save()

    program, created_prog = ProductionProgram.objects.get_or_create(item=item)
    _apply_program_state_from_history(rec, program)
    _sync_history_quantities_to_program(rec, program, user=user)
    if created_prog:
        result["created"] = True

    result["ok"] = True
    result["plan_id"] = plan.pk
    result["program_id"] = program.pk
    return result


def sync_all_history_to_planning(*, user=None) -> dict[str, int]:
    """Create/update planning rows for every archive history record (by plan number)."""
    from production.models import ProductionHistoryRecord

    stats = {"ok": 0, "failed": 0, "skipped": 0}
    live_uids = _live_program_uids()
    for rec in ProductionHistoryRecord.objects.all().iterator(chunk_size=200):
        if not (rec.plan_number or "").strip():
            stats["skipped"] += 1
            continue
        out = sync_history_record_to_planning(rec, user=user, live_uids=live_uids)
        if out.get("ok"):
            stats["ok"] += 1
            if out.get("error") != "live" and (rec.program_uid or "").strip():
                live_uids.add((rec.program_uid or "").strip())
        else:
            stats["failed"] += 1
            register_alarm(
                title="همگام‌سازی سابقه با برنامه‌ریزی ناموفق",
                message=out.get("error") or "خطای نامشخص",
                suggestion="کد کالا و شماره دستگاه/واحد را در کاتالوگ بررسی کنید.",
                severity=SystemAlarm.Severity.SERIOUS,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"program_uid": rec.program_uid, "plan_number": rec.plan_number},
                dedupe=True,
            )
    return stats


def ensure_history_synced_to_planning(*, user=None) -> dict[str, int]:
    """Sync only archive rows not yet present in planning (fast when already synced).

    Groups into WeeklyPlan by ``plan_number``. Safe to call from plan list.
    Also refreshes status/quantities for rows already linked when they are
    «در حال تولید».
    """
    from production.models import ProductionHistoryRecord, ProductionProgram

    stats = {"ok": 0, "failed": 0, "skipped": 0, "refreshed": 0}
    live_uids = _live_program_uids()
    planned_uids = _planning_line_uids()
    known = live_uids | planned_uids

    for rec in (
        ProductionHistoryRecord.objects.exclude(plan_number="")
        .order_by("plan_number", "program_uid", "id")
        .iterator(chunk_size=200)
    ):
        uid = (rec.program_uid or "").strip()
        inferred = infer_history_status(
            actual_start=rec.actual_start_date, actual_end=rec.actual_end_date
        )
        status_hint = _normalize_status_label(rec.status or "")
        is_active = inferred in ("running", "awaiting") or status_hint in (
            "running",
            "awaiting",
            "temp_stop",
        )

        if uid and uid in known:
            # Refresh live/running programs so ثبت و کنترل stays up to date
            if is_active:
                prog = _find_program_by_uid(uid)
                if prog is not None:
                    _apply_program_state_from_history(rec, prog)
                    _sync_history_quantities_to_program(rec, prog, user=user)
                    stats["refreshed"] += 1
                    continue
            stats["skipped"] += 1
            continue
        # Incomplete Excel rows cannot become planning items — skip quietly
        if not (rec.product_code or rec.product_name):
            stats["skipped"] += 1
            continue
        if rec.unit_number is None or not str(rec.machine_number or "").strip():
            stats["skipped"] += 1
            continue
        out = sync_history_record_to_planning(rec, user=user, live_uids=live_uids)
        if out.get("ok"):
            stats["ok"] += 1
            if uid:
                known.add(uid)
                if out.get("error") != "live":
                    planned_uids.add(uid)
                    live_uids.add(uid)
        else:
            stats["failed"] += 1
            # Avoid flooding alarms on every plan_list visit for the same bad row
            register_alarm(
                title="همگام‌سازی سابقه با برنامه‌ریزی ناموفق",
                message=out.get("error") or "خطای نامشخص",
                suggestion="کد کالا و شماره دستگاه/واحد را در کاتالوگ بررسی کنید.",
                severity=SystemAlarm.Severity.SERIOUS,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"program_uid": rec.program_uid, "plan_number": rec.plan_number},
                dedupe=True,
            )
    return stats


def ensure_running_history_in_production(*, user=None) -> dict[str, int]:
    """Push «در حال تولید» / awaiting archive rows into ثبت و کنترل تولید."""
    from production.models import ProductionHistoryRecord, ProductionProgram

    stats = {"ok": 0, "failed": 0, "skipped": 0, "refreshed": 0}
    live_uids = _live_program_uids()
    for rec in ProductionHistoryRecord.objects.exclude(plan_number="").iterator(
        chunk_size=200
    ):
        inferred = infer_history_status(
            actual_start=rec.actual_start_date, actual_end=rec.actual_end_date
        )
        status_hint = _normalize_status_label(rec.status or "")
        if inferred == "finished" or status_hint == "finished":
            stats["skipped"] += 1
            continue
        if not (rec.product_code or rec.product_name):
            stats["skipped"] += 1
            continue
        if rec.unit_number is None or not str(rec.machine_number or "").strip():
            stats["skipped"] += 1
            continue
        uid = (rec.program_uid or "").strip()
        if uid and uid in live_uids:
            prog = _find_program_by_uid(uid)
            if prog is not None and prog.status != ProductionProgram.Status.FINISHED:
                _apply_program_state_from_history(rec, prog)
                _sync_history_quantities_to_program(rec, prog, user=user)
                stats["refreshed"] += 1
            else:
                stats["skipped"] += 1
            continue
        out = sync_history_record_to_planning(rec, user=user, live_uids=live_uids)
        if out.get("ok"):
            stats["ok"] += 1
            if uid:
                live_uids.add(uid)
        else:
            stats["failed"] += 1
    return stats


def check_history_machine_conflicts() -> int:
    """Raise alarms for running conflicts between history and live molds.

    1) History (or live) row inferred running on a machine that already has
       another RUNNING program → alarm until one is finished.
    2) History awaiting (no actual start) while a RUNNING mold on same machine
       has a later start date → alarm.
    """
    from production.models import ProductionHistoryRecord, ProductionProgram

    created = 0

    running_by_machine: dict[int, list] = {}
    for prog in ProductionProgram.objects.filter(
        status=ProductionProgram.Status.RUNNING
    ).select_related("item__machine__unit", "item__product"):
        mid = prog.item.machine_id
        running_by_machine.setdefault(mid, []).append(prog)

    # Live programs inferred running via dates but status may differ — also check archives
    for rec in ProductionHistoryRecord.objects.all():
        status = infer_history_status(
            actual_start=rec.actual_start_date, actual_end=rec.actual_end_date
        )
        machine = resolve_machine(
            unit_number=rec.unit_number, machine_number=rec.machine_number
        )
        if not machine:
            continue
        uid = (rec.program_uid or "").strip()
        runners = running_by_machine.get(machine.pk, [])

        if status == "running":
            for prog in runners:
                other_uid = (prog.resolved_uid or "").strip()
                if other_uid and uid and other_uid == uid:
                    continue
                alarm = register_alarm(
                    title="تداخل: دو تولید هم‌زمان روی یک دستگاه",
                    message=(
                        f"در سوابق، شناسه «{uid or '—'}» با تاریخ راه‌اندازی واقعی "
                        f"به‌عنوان در حال تولید است و هم‌زمان برنامه «{other_uid}» "
                        f"روی {prog.machine_label} نیز در حال تولید است."
                    ),
                    suggestion="یکی از دو مورد را به اتمام تولید برسانید.",
                    severity=SystemAlarm.Severity.SERIOUS,
                    kind=SystemAlarm.Kind.PRODUCTION_CONFLICT,
                    details={
                        "history_uid": uid,
                        "live_uid": other_uid,
                        "machine_id": machine.pk,
                    },
                    dedupe=True,
                )
                if alarm:
                    created += 1

        if status == "awaiting" and runners:
            hist_ref = _to_gdate(rec.plan_start_date or rec.mold_change_date or rec.plan_date)
            for prog in runners:
                live_start = _to_gdate(prog.start_date)
                if hist_ref and live_start and live_start > hist_ref:
                    alarm = register_alarm(
                        title="تداخل: سابقه در انتظار با تولید جلوتر روی دستگاه",
                        message=(
                            f"سابقه اکسل «{uid or '—'}» هنوز راه‌اندازی واقعی ندارد "
                            f"(در انتظار تولید)، اما قالب «{prog.resolved_uid}» روی "
                            f"{prog.machine_label} با تاریخ شروع دیرتر در حال تولید است."
                        ),
                        suggestion="وضعیت سابقه یا برنامه زنده را اصلاح کنید.",
                        severity=SystemAlarm.Severity.SERIOUS,
                        kind=SystemAlarm.Kind.PRODUCTION_CONFLICT,
                        details={
                            "history_uid": uid,
                            "live_uid": prog.resolved_uid,
                            "machine_id": machine.pk,
                        },
                        dedupe=True,
                    )
                    if alarm:
                        created += 1

    # Also: two RUNNING programs on same machine (systemic)
    for mid, progs in running_by_machine.items():
        if len(progs) < 2:
            continue
        uids = ", ".join(p.resolved_uid for p in progs)
        register_alarm(
            title="چند برنامه در حال تولید روی یک دستگاه",
            message=f"دستگاه شناسه {mid}: {uids}",
            suggestion="فقط یک برنامه باید در حال تولید باشد؛ بقیه را متوقف یا تمام کنید.",
            severity=SystemAlarm.Severity.SERIOUS,
            kind=SystemAlarm.Kind.PRODUCTION_CONFLICT,
            details={"machine_id": mid, "uids": [p.resolved_uid for p in progs]},
            dedupe=True,
        )
        created += 1

    return created
