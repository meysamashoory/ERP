"""Transfer imported Excel tables into system destinations with column mapping."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from catalog.alarms import register_alarm
from catalog.models import ExcelTable, SystemAlarm

DESTINATION_PRODUCTION_HISTORY = "production_history"


@dataclass
class DestField:
    key: str
    label: str
    type: str  # string | integer | date
    required: bool = False


@dataclass
class TransferResult:
    destination_id: str
    transferred: int = 0
    failed: int = 0
    alarms: list[str] = field(default_factory=list)
    table_deleted: bool = False
    redirect_url: str = ""


PRODUCTION_HISTORY_FIELDS: list[DestField] = [
    DestField("program_uid", "شناسه تعویض", "string", required=True),
    DestField("plan_number", "شماره برنامه", "string"),
    DestField("plan_date", "تاریخ برنامه‌ریزی", "date"),
    DestField("mold_change_date", "تاریخ تعویض قالب", "date"),
    DestField("unit_number", "شماره واحد", "integer"),
    DestField("machine_number", "شماره دستگاه", "string"),
    DestField("product_code", "کد کالا", "string"),
    DestField("product_name", "نام جنس", "string"),
    DestField("mold_name", "نام قالب", "string"),
    DestField("mold_number", "شماره قالب", "string"),
    DestField("unique_code", "کد یکتا", "string"),
    DestField("material", "مواد", "string"),
    DestField("color", "رنگ", "string"),
    DestField("sequence", "ترتیب روی دستگاه", "integer"),
    DestField("plan_start_date", "تاریخ شروع برنامه", "date"),
    DestField("actual_start_date", "تاریخ شروع واقعی", "date"),
    DestField("planned_qty", "مقدار تولید برنامه", "integer"),
    DestField("produced_qty", "مقدار تولید واقعی", "integer"),
    DestField("planned_cycle", "سیکل تولید برنامه", "integer"),
    DestField("last_cycle", "آخرین سیکل تولید", "integer"),
    DestField("planned_hours", "ساعت تولید برنامه", "decimal"),
    DestField("active_cavities", "تعداد حفره فعال", "integer"),
    DestField("last_cavities", "آخرین وضعیت حفره", "integer"),
    DestField("scrap_qty", "ضایعات تولید", "integer"),
    DestField("status", "وضعیت", "string"),
    DestField("notes", "توضیحات", "string"),
]


def list_destinations() -> list[dict[str, Any]]:
    return [
        {
            "id": DESTINATION_PRODUCTION_HISTORY,
            "label": "سوابق تولید",
            "fields": [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type,
                    "required": f.required,
                }
                for f in PRODUCTION_HISTORY_FIELDS
            ],
        }
    ]


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


def _parse_date(raw: str, label: str) -> tuple[date | None, str | None]:
    if raw == "":
        return None, None
    text = raw.strip()
    # Excel serial as whole number / float string
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
    # Jalali YYYY/MM/DD
    try:
        import jdatetime

        parts = re.split(r"[/.\-]", text)
        if len(parts) == 3:
            y, m, d = (int(p) for p in parts)
            if y > 1500:  # jalali years
                return jdatetime.date(y, m, d).togregorian(), None
    except Exception:  # noqa: BLE001
        pass
    return None, f"مقدار «{raw}» برای «{label}» تاریخ معتبر نیست (مثال: 1403/01/15 یا 2024-04-03)."


def _parse_string(raw: str, label: str) -> tuple[str, str | None]:
    return raw, None


def _parse_decimal(raw: str, label: str) -> tuple[Any, str | None]:
    if raw == "":
        return None, None
    cleaned = raw.replace(",", "").replace("٬", "").replace(" ", "")
    try:
        from decimal import Decimal

        return Decimal(cleaned), None
    except Exception:  # noqa: BLE001
        return None, f"مقدار «{raw}» برای «{label}» عدد اعشاری نیست."


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
    """Map dest field key → excel column index (or None)."""
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


def _transfer_production_history(
    *,
    table: ExcelTable,
    col_map: dict[str, int | None],
    user,
) -> TransferResult:
    from production.models import ProductionHistoryRecord, ProductionProgram

    result = TransferResult(destination_id=DESTINATION_PRODUCTION_HISTORY)
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    existing_live_uids = set()
    for p in ProductionProgram.objects.select_related("item").all():
        uid = (p.resolved_uid or "").strip()
        if uid:
            existing_live_uids.add(uid)
    existing_hist_uids = set(
        ProductionHistoryRecord.objects.values_list("program_uid", flat=True)
    )

    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            result.failed += 1
            msg = f"ردیف {row_i}: ساختار ردیف نامعتبر است."
            result.alarms.append(msg)
            register_alarm(
                title="خطا در انتقال داده اکسل",
                message=msg,
                suggestion="ردیف را در فایل اکسل اصلاح و دوباره وارد کنید.",
                severity=SystemAlarm.Severity.SERIOUS,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"table_id": table.pk, "row": row_i},
                dedupe=False,
            )
            continue

        values: dict[str, Any] = {}
        row_errors: list[str] = []
        for f in PRODUCTION_HISTORY_FIELDS:
            raw = _cell(row, col_map.get(f.key))
            if raw == "":
                if f.required:
                    row_errors.append(f"«{f.label}» خالی است.")
                continue
            parser = _PARSERS[f.type]
            parsed, err = parser(raw, f.label)
            if err:
                row_errors.append(err)
            else:
                values[f.key] = parsed

        if row_errors:
            result.failed += 1
            msg = f"ردیف {row_i} جدول «{table.name}»: " + "؛ ".join(row_errors)
            result.alarms.append(msg)
            register_alarm(
                title="مغایرت نوع داده در انتقال اکسل",
                message=msg,
                suggestion="نگاشت ستون‌ها و قالب داده را بررسی کنید.",
                severity=SystemAlarm.Severity.SERIOUS,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"table_id": table.pk, "row": row_i, "errors": row_errors},
                dedupe=False,
            )
            continue

        uid = str(values.get("program_uid") or "").strip()
        if not uid:
            result.failed += 1
            msg = f"ردیف {row_i}: شناسه برنامه الزامی است."
            result.alarms.append(msg)
            register_alarm(
                title="خطا در انتقال داده اکسل",
                message=msg,
                suggestion="ستون شناسه برنامه را نگاشت کنید.",
                severity=SystemAlarm.Severity.SERIOUS,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"table_id": table.pk, "row": row_i},
                dedupe=False,
            )
            continue

        if uid in existing_live_uids:
            # Live planning/production already owns this UID — skip duplicate archive row.
            result.failed += 1
            msg = (
                f"ردیف {row_i}: شناسه «{uid}» هم‌اکنون در برنامه‌ریزی/ثبت تولید وجود دارد؛ "
                "ردیف آرشیو تکراری ایجاد نشد (داده زنده مرجع است)."
            )
            result.alarms.append(msg)
            register_alarm(
                title="شناسه تکراری در انتقال به سوابق",
                message=msg,
                suggestion="در صورت نیاز، همان برنامه را از ثبت تولید به‌روز کنید.",
                severity=SystemAlarm.Severity.ADVISORY,
                kind=SystemAlarm.Kind.DATA_TRANSFER,
                details={"table_id": table.pk, "row": row_i, "uid": uid},
                dedupe=False,
            )
            continue

        if uid in existing_hist_uids:
            # Update existing archive row
            rec = ProductionHistoryRecord.objects.filter(program_uid=uid).first()
            if rec is None:
                result.failed += 1
                continue
            for key, val in values.items():
                if key == "program_uid":
                    continue
                setattr(rec, key, val)
            if rec.scrap_qty is None:
                rec.scrap_qty = 0
            if rec.produced_qty is None:
                rec.produced_qty = 0
            if not rec.plan_start_date and values.get("mold_change_date"):
                rec.plan_start_date = values.get("mold_change_date")
            rec.source_table_name = table.name
            rec.transferred_by = user
            rec.save()
            result.transferred += 1
            continue

        create_kwargs = {
            "program_uid": uid,
            "source_table_name": table.name,
            "transferred_by": user,
            "extra": {"excel_headers": headers, "excel_row_index": row_i},
        }
        for f in PRODUCTION_HISTORY_FIELDS:
            if f.key == "program_uid":
                continue
            if f.key in values:
                create_kwargs[f.key] = values[f.key]
        create_kwargs.setdefault("scrap_qty", 0)
        create_kwargs.setdefault("produced_qty", 0)
        if "plan_start_date" not in create_kwargs and values.get("mold_change_date"):
            create_kwargs["plan_start_date"] = values.get("mold_change_date")
        ProductionHistoryRecord.objects.create(**create_kwargs)
        existing_hist_uids.add(uid)
        result.transferred += 1

    return result


_HANDLERS = {
    DESTINATION_PRODUCTION_HISTORY: _transfer_production_history,
}


def transfer_excel_table(
    *,
    table: ExcelTable,
    destination_id: str,
    mapping: dict[str, Any],
    user,
) -> TransferResult:
    """Transfer table rows into destination, then delete the Excel table."""
    from django.urls import reverse

    destinations = {d["id"]: d for d in list_destinations()}
    if destination_id not in destinations:
        raise ValueError("مقصد انتقال نامعتبر است.")

    fields = (
        PRODUCTION_HISTORY_FIELDS
        if destination_id == DESTINATION_PRODUCTION_HISTORY
        else []
    )
    headers = table.headers if isinstance(table.headers, list) else []
    col_map, map_errors = _normalize_mapping(mapping, fields, len(headers))
    if map_errors:
        raise ValueError(" ".join(map_errors))

    handler = _HANDLERS[destination_id]
    result = handler(table=table, col_map=col_map, user=user)

    upload = table.upload
    table_name = table.name
    table_id = table.pk
    table.delete()
    result.table_deleted = True

    if upload and not upload.tables.exists():
        upload.delete()
        result.redirect_url = reverse("excel_list")
    else:
        result.redirect_url = reverse("excel_detail", args=[upload.pk]) if upload else reverse("excel_list")

    if result.failed:
        register_alarm(
            title=f"خلاصه انتقال جدول «{table_name}»",
            message=(
                f"انتقال به «{destinations[destination_id]['label']}» انجام شد: "
                f"{result.transferred} موفق، {result.failed} ناموفق. "
                f"جدول اکسل حذف شد (شناسه قبلی جدول: {table_id})."
            ),
            suggestion="جزئیات ردیف‌های ناموفق را در آلارم‌های سیستم ببینید.",
            severity=SystemAlarm.Severity.SERIOUS,
            kind=SystemAlarm.Kind.DATA_TRANSFER,
            details={
                "table_name": table_name,
                "transferred": result.transferred,
                "failed": result.failed,
            },
            dedupe=False,
        )

    return result
