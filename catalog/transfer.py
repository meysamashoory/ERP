"""Transfer imported Excel tables into system destinations with column mapping."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from catalog.alarms import register_alarm
from catalog.models import ExcelTable, SystemAlarm
from django.urls import reverse

DESTINATION_PRODUCTION_HISTORY = "production_history"

LEVEL_HISTORY_LIST = "history_list"
LEVEL_HISTORY_DAILY = "history_daily"


@dataclass
class DestField:
    key: str
    label: str
    type: str  # string | integer | date | decimal
    required: bool = False


@dataclass
class TransferResult:
    destination_id: str
    level_id: str = ""
    transferred: int = 0
    failed: int = 0
    alarms: list[str] = field(default_factory=list)
    table_deleted: bool = False
    redirect_url: str = ""


# Exact columns of «سوابق تولید» list (+ end date for status inference)
HISTORY_LIST_FIELDS: list[DestField] = [
    DestField("program_uid", "شناسه تعویض", "string", required=True),
    DestField("plan_number", "شماره برنامه", "string", required=True),
    DestField("plan_date", "تاریخ برنامه‌ریزی", "date"),
    DestField("unit_number", "شماره واحد", "integer"),
    DestField("machine_number", "شماره دستگاه", "string"),
    DestField("product_code", "کد کالا", "string"),
    DestField("product_name", "نام جنس", "string"),
    DestField("mold_number", "شماره قالب", "string"),
    DestField("unique_code", "کد یکتا", "string"),
    DestField("plan_start_date", "تاریخ شروع برنامه", "date"),
    DestField("actual_start_date", "تاریخ شروع واقعی", "date"),
    DestField("actual_end_date", "تاریخ پایان تولید", "date"),
    DestField("planned_qty", "مقدار تولید برنامه (عدد)", "integer"),
    DestField("produced_qty", "مقدار تولید واقعی (عدد)", "integer"),
    DestField("planned_cycle", "سیکل تولید برنامه (ثانیه)", "integer"),
    DestField("last_cycle", "آخرین سیکل تولید (ثانیه)", "integer"),
    DestField("planned_hours", "ساعت تولید برنامه", "decimal"),
    DestField("active_cavities", "تعداد حفره فعال", "integer"),
    DestField("last_cavities", "آخرین وضعیت حفره", "integer"),
    DestField("scrap_qty", "ضایعات تولید", "integer"),
]

HISTORY_DAILY_FIELDS: list[DestField] = [
    DestField("program_uid", "شناسه تعویض", "string", required=True),
    DestField("work_date", "تاریخ سند", "date", required=True),
    DestField("produced_qty", "مقدار تولید شده", "integer"),
    DestField("scrap_qty", "ضایعات", "integer"),
    DestField("qty_deviation", "انحراف آمار تولید", "integer"),
    DestField("qty_reason", "علت انحراف آمار", "string"),
    DestField("time_deviation", "انحراف زمان تولید (ثانیه)", "integer"),
    DestField("time_reason", "علت انحراف زمان", "string"),
    DestField("notes", "توضیحات", "string"),
]


def _fields_payload(fields: list[DestField]) -> list[dict[str, Any]]:
    return [
        {"key": f.key, "label": f.label, "type": f.type, "required": f.required}
        for f in fields
    ]


def list_destinations() -> list[dict[str, Any]]:
    return [
        {
            "id": DESTINATION_PRODUCTION_HISTORY,
            "label": "سوابق تولید",
            "levels": [
                {
                    "id": LEVEL_HISTORY_LIST,
                    "label": "لیست سوابق تولید",
                    "fields": _fields_payload(HISTORY_LIST_FIELDS),
                },
                {
                    "id": LEVEL_HISTORY_DAILY,
                    "label": "اسناد روزانه",
                    "fields": _fields_payload(HISTORY_DAILY_FIELDS),
                },
            ],
        }
    ]


def _fields_for(destination_id: str, level_id: str) -> list[DestField]:
    if destination_id != DESTINATION_PRODUCTION_HISTORY:
        return []
    if level_id == LEVEL_HISTORY_DAILY:
        return HISTORY_DAILY_FIELDS
    return HISTORY_LIST_FIELDS


def _cell(row: list, index: int | None) -> str:
    if index is None or index < 0:
        return ""
    if index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    return str(value).strip()


def _parse_integer(raw: str, label: str) -> tuple[int | None, str | None]:
    if raw == "":
        return None, None
    cleaned = raw.replace(",", "").replace("٬", "").replace(" ", "")
    try:
        return int(float(cleaned)), None
    except (TypeError, ValueError):
        return None, f"مقدار «{raw}» برای «{label}» عدد صحیح نیست."


def _parse_decimal(raw: str, label: str) -> tuple[Any, str | None]:
    if raw == "":
        return None, None
    cleaned = raw.replace(",", "").replace("٬", "").replace(" ", "")
    try:
        return Decimal(cleaned), None
    except Exception:  # noqa: BLE001
        return None, f"مقدار «{raw}» برای «{label}» عدد اعشاری نیست."


def _parse_date(raw: str, label: str) -> tuple[date | None, str | None]:
    if raw == "":
        return None, None
    text = raw.strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        try:
            serial = int(float(text))
            if 20000 <= serial <= 80000:
                from datetime import timedelta

                return date(1899, 12, 30) + timedelta(days=serial), None
        except (TypeError, ValueError, OverflowError):
            pass
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    try:
        import jdatetime

        parts = re.split(r"[/.\-]", text)
        if len(parts) == 3:
            y, m, d = (int(p) for p in parts)
            if y > 1500:
                return jdatetime.date(y, m, d).togregorian(), None
    except Exception:  # noqa: BLE001
        pass
    return None, f"مقدار «{raw}» برای «{label}» تاریخ معتبر نیست."


def _parse_string(raw: str, label: str) -> tuple[str, str | None]:
    return raw, None


_PARSERS: dict[str, Callable[[str, str], tuple[Any, str | None]]] = {
    "string": _parse_string,
    "integer": _parse_integer,
    "date": _parse_date,
    "decimal": _parse_decimal,
}


def _normalize_mapping(
    mapping: dict[str, Any],
    fields: list[DestField],
    header_count: int,
) -> tuple[dict[str, int | None], list[str]]:
    out: dict[str, int | None] = {}
    errors: list[str] = []
    for f in fields:
        raw = mapping.get(f.key)
        if raw is None or raw == "" or raw == -1 or raw == "-1":
            out[f.key] = None
            if f.required:
                errors.append(f"ستون مقصد «{f.label}» الزامی است و باید به یک ستون اکسل نگاشت شود.")
            continue
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            errors.append(f"نگاشت ستون «{f.label}» نامعتبر است.")
            out[f.key] = None
            continue
        if idx < 0 or idx >= header_count:
            errors.append(f"شاخص ستون اکسل برای «{f.label}» خارج از محدوده است.")
            out[f.key] = None
            continue
        out[f.key] = idx
    return out, errors


def _row_alarm(result: TransferResult, *, table: ExcelTable, row_i: int, msg: str) -> None:
    result.failed += 1
    result.alarms.append(msg)
    register_alarm(
        title="خطا در انتقال داده اکسل",
        message=msg,
        suggestion="نگاشت ستون‌ها و قالب داده را بررسی کنید.",
        severity=SystemAlarm.Severity.SERIOUS,
        kind=SystemAlarm.Kind.DATA_TRANSFER,
        details={"table_id": table.pk, "row": row_i},
        dedupe=False,
    )


def _parse_row(
    row: list,
    col_map: dict[str, int | None],
    fields: list[DestField],
) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, Any] = {}
    errors: list[str] = []
    for f in fields:
        raw = _cell(row, col_map.get(f.key))
        if raw == "":
            if f.required:
                errors.append(f"«{f.label}» خالی است.")
            continue
        parsed, err = _PARSERS[f.type](raw, f.label)
        if err:
            errors.append(err)
        else:
            values[f.key] = parsed
    return values, errors


def _transfer_history_list(*, table: ExcelTable, col_map: dict[str, int | None], user) -> TransferResult:
    from production.models import ProductionHistoryRecord, ProductionProgram
    from production.sync import check_history_machine_conflicts, sync_history_record_to_planning

    result = TransferResult(destination_id=DESTINATION_PRODUCTION_HISTORY, level_id=LEVEL_HISTORY_LIST)
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []

    live_uids = set()
    for p in ProductionProgram.objects.select_related("item").all():
        uid = (p.resolved_uid or "").strip()
        if uid:
            live_uids.add(uid)
    hist_uids = set(ProductionHistoryRecord.objects.values_list("program_uid", flat=True))

    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار نامعتبر.")
            continue
        values, row_errors = _parse_row(row, col_map, HISTORY_LIST_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}»: " + "؛ ".join(row_errors),
            )
            continue
        uid = str(values.get("program_uid") or "").strip()
        if not uid:
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: شناسه تعویض الزامی است.")
            continue

        if uid in live_uids:
            # Update live program's linked history snapshot is skip — live is source.
            # Still try to keep an archive mirror updated for Excel fields if exists.
            pass

        defaults = {k: v for k, v in values.items() if k != "program_uid"}
        defaults.setdefault("scrap_qty", 0)
        defaults.setdefault("produced_qty", 0)

        rec = ProductionHistoryRecord.objects.filter(program_uid=uid).first()
        if rec:
            for key, val in defaults.items():
                setattr(rec, key, val)
            rec.source_table_name = table.name
            rec.transferred_by = user
            rec.save()
        else:
            rec = ProductionHistoryRecord.objects.create(
                program_uid=uid,
                source_table_name=table.name,
                transferred_by=user,
                extra={"excel_headers": headers, "excel_row_index": row_i},
                **{k: defaults[k] for k in defaults},
            )
            hist_uids.add(uid)

        sync_out = sync_history_record_to_planning(rec, user=user)
        if not sync_out.get("ok") and sync_out.get("error") not in ("", "live"):
            result.alarms.append(f"ردیف {row_i}: همگام‌سازی برنامه‌ریزی — {sync_out.get('error')}")
            register_alarm(
                title="همگام‌سازی سابقه با برنامه‌ریزی",
                message=f"ردیف {row_i}: {sync_out.get('error')}",
                suggestion="کالا و دستگاه را در داده‌های سیستم بررسی کنید.",
                severity=SystemAlarm.Severity.SERIOUS,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"uid": uid, "row": row_i},
                dedupe=False,
            )
        result.transferred += 1

    check_history_machine_conflicts()
    return result


def _transfer_history_daily(*, table: ExcelTable, col_map: dict[str, int | None], user) -> TransferResult:
    from production.models import ProductionHistoryRecord

    result = TransferResult(destination_id=DESTINATION_PRODUCTION_HISTORY, level_id=LEVEL_HISTORY_DAILY)
    rows = table.rows if isinstance(table.rows, list) else []

    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار نامعتبر.")
            continue
        values, row_errors = _parse_row(row, col_map, HISTORY_DAILY_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i}: " + "؛ ".join(row_errors),
            )
            continue
        uid = str(values.get("program_uid") or "").strip()
        rec = ProductionHistoryRecord.objects.filter(program_uid=uid).first()
        if not rec:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i}: شناسه «{uid}» در سوابق یافت نشد (ابتدا سطح لیست را منتقل کنید).",
            )
            continue
        extra = rec.extra if isinstance(rec.extra, dict) else {}
        entries = list(extra.get("day_entries") or [])
        work = values.get("work_date")
        work_s = work.isoformat() if hasattr(work, "isoformat") else str(work or "")
        produced = int(values.get("produced_qty") or 0)
        scrap = int(values.get("scrap_qty") or 0)
        snap = {
            "date": work_s,
            "date_display": work_s,
            "produced": produced,
            "scrap": scrap,
            "qty_deviation": int(values.get("qty_deviation") or 0),
            "qty_reason": values.get("qty_reason") or "—",
            "time_deviation": int(values.get("time_deviation") or 0),
            "time_reason": values.get("time_reason") or "—",
            "description": values.get("notes") or "—",
        }
        # replace same date if present
        entries = [e for e in entries if not (isinstance(e, dict) and e.get("date") == work_s)]
        entries.append(snap)
        entries.sort(key=lambda e: str((e or {}).get("date") or ""))
        extra["day_entries"] = entries
        rec.extra = extra
        # refresh aggregates
        rec.produced_qty = sum(int(e.get("produced") or 0) for e in entries if isinstance(e, dict))
        rec.scrap_qty = sum(int(e.get("scrap") or 0) for e in entries if isinstance(e, dict))
        rec.transferred_by = user
        rec.source_table_name = table.name
        rec.save()
        result.transferred += 1

    return result


_HANDLERS = {
    (DESTINATION_PRODUCTION_HISTORY, LEVEL_HISTORY_LIST): _transfer_history_list,
    (DESTINATION_PRODUCTION_HISTORY, LEVEL_HISTORY_DAILY): _transfer_history_daily,
}


def transfer_excel_table(
    *,
    table: ExcelTable,
    destination_id: str,
    mapping: dict[str, Any],
    user,
    level_id: str = LEVEL_HISTORY_LIST,
) -> TransferResult:
    """Transfer table rows into destination. Does NOT delete the Excel table."""
    destinations = {d["id"]: d for d in list_destinations()}
    if destination_id not in destinations:
        raise ValueError("مقصد انتقال نامعتبر است.")

    dest = destinations[destination_id]
    levels = {lv["id"]: lv for lv in dest.get("levels") or []}
    if not level_id:
        level_id = next(iter(levels), LEVEL_HISTORY_LIST)
    if level_id not in levels:
        raise ValueError("سطح انتقال نامعتبر است.")

    fields = _fields_for(destination_id, level_id)
    headers = table.headers if isinstance(table.headers, list) else []
    col_map, map_errors = _normalize_mapping(mapping, fields, len(headers))
    if map_errors:
        raise ValueError(" ".join(map_errors))

    handler = _HANDLERS.get((destination_id, level_id))
    if not handler:
        raise ValueError("هندلر انتقال یافت نشد.")

    result = handler(table=table, col_map=col_map, user=user)
    result.redirect_url = reverse("excel_detail", args=[table.upload_id]) if table.upload_id else reverse("excel_list")
    result.table_deleted = False

    if result.failed:
        register_alarm(
            title=f"خلاصه انتقال جدول «{table.name}»",
            message=(
                f"انتقال به «{dest['label']} / {levels[level_id]['label']}»: "
                f"{result.transferred} موفق، {result.failed} ناموفق."
            ),
            suggestion="جزئیات ردیف‌های ناموفق را در آلارم‌های سیستم ببینید.",
            severity=SystemAlarm.Severity.SERIOUS,
            kind=SystemAlarm.Kind.DATA_TRANSFER,
            details={
                "table_name": table.name,
                "transferred": result.transferred,
                "failed": result.failed,
                "level": level_id,
            },
            dedupe=False,
        )

    return result
