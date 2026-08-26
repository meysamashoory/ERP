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
DESTINATION_PRODUCT_DATA = "product_data"

LEVEL_HISTORY_LIST = "history_list"
LEVEL_HISTORY_DAILY = "history_daily"
LEVEL_PRODUCT_INFO = "product_info"
LEVEL_PRODUCT_BOM = "product_bom"
LEVEL_PRODUCT_CONSUMABLES = "product_consumables"


@dataclass
class DestField:
    key: str
    label: str
    type: str  # string | integer | date | decimal | quantity
    required: bool = False


@dataclass
class TransferResult:
    destination_id: str
    level_id: str = ""
    transferred: int = 0
    failed: int = 0
    skipped: int = 0
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
    DestField("planned_qty", "مقدار تولید برنامه (عدد)", "quantity"),
    DestField("produced_qty", "مقدار تولید واقعی (عدد)", "quantity"),
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
    DestField("produced_qty", "مقدار تولید شده", "quantity"),
    DestField("scrap_qty", "ضایعات", "integer"),
    DestField("qty_deviation", "انحراف آمار تولید", "integer"),
    DestField("qty_reason", "علت انحراف آمار", "string"),
    DestField("time_deviation", "انحراف زمان تولید (ثانیه)", "integer"),
    DestField("time_reason", "علت انحراف زمان", "string"),
    DestField("notes", "توضیحات", "string"),
]

PRODUCT_INFO_FIELDS: list[DestField] = [
    DestField("code", "کد کالا", "string", required=True),
    DestField("name", "نام قطعه", "string", required=True),
    DestField("group_name", "گروه", "string"),
    DestField("subgroup_name", "زیرگروه", "string"),
    DestField("counting_unit", "واحد شمارش", "string"),
    DestField("unit_weight_grams", "وزن هر واحد (گرم)", "decimal"),
    DestField("per_carton", "تعداد در کارتن", "integer"),
    DestField("per_bag", "تعداد در کیسه", "integer"),
    DestField("depot_ceiling", "سقف دپو", "integer"),
    DestField("main_cavities", "حفره اصلی", "integer"),
    DestField("last_cycle", "آخرین سیکل", "integer"),
    DestField("stock_finished", "موجودی محصول", "integer"),
    DestField("stock_unassembled", "موجودی مونتاژ‌نشده", "integer"),
    DestField("reorder_level", "سطح سفارش مجدد", "integer"),
    DestField("needs_assembly", "نیاز به مونتاژ", "string"),
    DestField("needs_machining", "نیاز به تراشکاری", "string"),
    DestField("needs_facing", "نیاز به کفتراشی", "string"),
]

PRODUCT_BOM_FIELDS: list[DestField] = [
    DestField("parent_code", "کد محصول والد", "string", required=True),
    DestField("component_code", "کد جزء", "string"),
    DestField("component_name", "نام جزء", "string", required=True),
    DestField("quantity", "مقدار", "decimal"),
    DestField("unit", "واحد", "string"),
    DestField("notes", "توضیحات", "string"),
    DestField("order", "ترتیب", "integer"),
]

PRODUCT_CONSUMABLE_FIELDS: list[DestField] = [
    DestField("product_code", "کد محصول", "string", required=True),
    DestField("material_code", "کد ماده", "string"),
    DestField("material_name", "نام ماده", "string", required=True),
    DestField("quantity_per_unit", "مقدار به ازای واحد محصول", "decimal"),
    DestField("unit", "واحد", "string"),
    DestField("notes", "توضیحات", "string"),
    DestField("order", "ترتیب", "integer"),
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
        },
        {
            "id": DESTINATION_PRODUCT_DATA,
            "label": "دیتای محصولات",
            "levels": [
                {
                    "id": LEVEL_PRODUCT_INFO,
                    "label": "اطلاعات محصول",
                    "fields": _fields_payload(PRODUCT_INFO_FIELDS),
                },
                {
                    "id": LEVEL_PRODUCT_BOM,
                    "label": "ساختار BOM",
                    "fields": _fields_payload(PRODUCT_BOM_FIELDS),
                },
                {
                    "id": LEVEL_PRODUCT_CONSUMABLES,
                    "label": "مواد مصرفی",
                    "fields": _fields_payload(PRODUCT_CONSUMABLE_FIELDS),
                },
            ],
        },
    ]


def _fields_for(destination_id: str, level_id: str) -> list[DestField]:
    if destination_id == DESTINATION_PRODUCTION_HISTORY:
        if level_id == LEVEL_HISTORY_DAILY:
            return HISTORY_DAILY_FIELDS
        return HISTORY_LIST_FIELDS
    if destination_id == DESTINATION_PRODUCT_DATA:
        if level_id == LEVEL_PRODUCT_BOM:
            return PRODUCT_BOM_FIELDS
        if level_id == LEVEL_PRODUCT_CONSUMABLES:
            return PRODUCT_CONSUMABLE_FIELDS
        return PRODUCT_INFO_FIELDS
    return []


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
        return None, f"فیلد «{label}»: مقدار «{raw}» عدد صحیح معتبر نیست."


def _parse_decimal(raw: str, label: str) -> tuple[Any, str | None]:
    if raw == "":
        return None, None
    cleaned = raw.replace(",", "").replace("٬", "").replace(" ", "")
    try:
        return Decimal(cleaned), None
    except Exception:  # noqa: BLE001
        return None, f"فیلد «{label}»: مقدار «{raw}» عدد اعشاری معتبر نیست."


def _normalize_digits(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to ASCII."""
    from catalog.qty_parse import normalize_digits

    return normalize_digits(text)


def _parse_date(raw: str, label: str) -> tuple[date | None, str | None]:
    """Parse Excel/Jalali/Gregorian date strings into a Gregorian ``date``.

    Supports:
    - Excel serials (e.g. ``46257`` → 2026-08-23 / شمسی 1405/06/01)
    - Jalali ``YYYY/MM/DD`` with years 1200–1500 (e.g. ``1405/06/01``)
    - Gregorian ISO / slash / dash forms
    - Datetime strings with a time component
    """
    if raw == "":
        return None, None
    text = _normalize_digits(str(raw).strip())
    # Drop time portion: "2026-08-23 00:00:00" / ISO
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    text = text.strip()

    # Excel serial number (value behind formats like [$-fa-IR,96]yyyy/mm/dd)
    if re.fullmatch(r"\d+(\.\d+)?", text):
        try:
            serial = int(float(text))
            if 20000 <= serial <= 100000:
                from datetime import timedelta

                return date(1899, 12, 30) + timedelta(days=serial), None
            # Compact YYYYMMDD (Jalali or Gregorian)
            if len(text) == 8 and text.isdigit():
                y, m, d = int(text[:4]), int(text[4:6]), int(text[6:8])
                if 1200 <= y <= 1500:
                    import jdatetime

                    return jdatetime.date(y, m, d).togregorian(), None
                if 1600 <= y <= 2100:
                    return date(y, m, d), None
        except (TypeError, ValueError, OverflowError):
            pass

    parts = re.split(r"[/.\-]", text)
    if len(parts) == 3:
        try:
            a, b, c = (int(p) for p in parts)
        except ValueError:
            a = b = c = -1
        if a >= 0:
            # Year-first: YYYY/MM/DD
            if a >= 1000:
                y, m, d = a, b, c
                try:
                    # Persian calendar years (e.g. 1405) must NOT be read as Gregorian
                    if 1200 <= y <= 1500:
                        import jdatetime

                        return jdatetime.date(y, m, d).togregorian(), None
                    if 1600 <= y <= 2100:
                        return date(y, m, d), None
                except Exception as exc:  # noqa: BLE001
                    return None, (
                        f"فیلد «{label}»: تاریخ «{raw}» نامعتبر است "
                        f"(سال {y} به‌عنوان شمسی/میلادی قابل تبدیل نیست: {exc})."
                    )
            # Day-first: DD/MM/YYYY
            if c >= 1000:
                d, m, y = a, b, c
                try:
                    if 1200 <= y <= 1500:
                        import jdatetime

                        return jdatetime.date(y, m, d).togregorian(), None
                    if 1600 <= y <= 2100:
                        return date(y, m, d), None
                except Exception as exc:  # noqa: BLE001
                    return None, (
                        f"فیلد «{label}»: تاریخ «{raw}» نامعتبر است ({exc})."
                    )

    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            # Guard: year in Jalali range must go through jdatetime (already handled);
            # if we reach here with 1200–1500 it slipped through — convert.
            if 1200 <= parsed.year <= 1500:
                import jdatetime

                return jdatetime.date(parsed.year, parsed.month, parsed.day).togregorian(), None
            return parsed, None
        except ValueError:
            continue

    return None, (
        f"فیلد «{label}»: مقدار «{raw}» تاریخ معتبر نیست "
        f"(سریال اکسل مثل 46257، شمسی مثل 1405/06/01 یا میلادی مثل 2026-08-23)."
    )


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
    """Map destination fields to Excel columns.

    Unmapped / empty mapping is allowed (including formerly-required fields);
    those fields simply stay empty during transfer.
    """
    out: dict[str, int | None] = {}
    errors: list[str] = []
    for f in fields:
        raw = mapping.get(f.key)
        if raw is None or raw == "" or raw == -1 or raw == "-1":
            out[f.key] = None
            continue
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            errors.append(f"فیلد «{f.label}»: نگاشت ستون اکسل نامعتبر است.")
            out[f.key] = None
            continue
        if idx < 0 or idx >= header_count:
            errors.append(
                f"فیلد «{f.label}»: ستون اکسل انتخاب‌شده خارج از محدوده جدول است "
                f"(شاخص {idx}، تعداد ستون‌ها {header_count})."
            )
            out[f.key] = None
            continue
        out[f.key] = idx
    return out, errors


def _row_alarm(
    result: TransferResult,
    *,
    table: ExcelTable,
    row_i: int,
    msg: str,
    field_label: str = "",
) -> None:
    result.failed += 1
    result.alarms.append(msg)
    register_alarm(
        title="خطا در انتقال داده اکسل",
        message=msg,
        suggestion=(
            f"مقدار فیلد «{field_label}» را در ردیف {row_i} جدول «{table.name}» اصلاح کنید."
            if field_label
            else f"ردیف {row_i} جدول «{table.name}» و نگاشت ستون‌ها را بررسی کنید."
        ),
        severity=SystemAlarm.Severity.SERIOUS,
        kind=SystemAlarm.Kind.DATA_TRANSFER,
        details={"table_id": table.pk, "row": row_i, "field": field_label},
        dedupe=False,
    )


def _parse_row(
    row: list,
    col_map: dict[str, int | None],
    fields: list[DestField],
) -> tuple[dict[str, Any], list[str]]:
    """Parse mapped cells. Empty cells are skipped (not errors)."""
    from catalog.qty_parse import (
        apply_production_type_to_name,
        extract_qty_and_production_type,
    )

    values: dict[str, Any] = {}
    errors: list[str] = []
    prod_type = ""
    for f in fields:
        # Unmapped destination field → leave empty, no error
        if col_map.get(f.key) is None:
            continue
        raw = _cell(row, col_map.get(f.key))
        # Empty Excel cell → leave empty, no error
        if raw == "":
            continue
        if f.type == "quantity":
            qty, ptype, err = extract_qty_and_production_type(raw)
            if err:
                errors.append(f"فیلد «{f.label}»: {err}")
            else:
                values[f.key] = qty
                if ptype:
                    prod_type = ptype
            continue
        parsed, err = _PARSERS[f.type](raw, f.label)
        if err:
            errors.append(err)
        else:
            values[f.key] = parsed

    if prod_type:
        name = str(values.get("product_name") or "").strip()
        if name:
            values["product_name"] = apply_production_type_to_name(name, prod_type)
        values["_production_type"] = prod_type
    return values, errors


def _format_row_errors(row_i: int, table_name: str, errors: list[str]) -> str:
    return f"ردیف {row_i} جدول «{table_name}» — " + " | ".join(errors)


def transfer_result_message(result: TransferResult) -> str:
    """Human message: never claim full success when failures exist."""
    parts = []
    if result.transferred:
        parts.append(f"{result.transferred} ردیف منتقل شد")
    if result.failed:
        parts.append(f"{result.failed} ردیف با خطا")
    if result.skipped:
        parts.append(f"{result.skipped} ردیف خالی/بدون شناسه رد شد")
    if not parts:
        return "هیچ ردیفی برای انتقال یافت نشد."
    if result.failed and not result.transferred:
        return "انتقال ناموفق بود: " + "؛ ".join(parts) + "."
    if result.failed:
        return "انتقال ناقص انجام شد: " + "؛ ".join(parts) + "."
    if result.skipped and result.transferred:
        return "انتقال انجام شد: " + "؛ ".join(parts) + "."
    return "انتقال با موفقیت انجام شد: " + "؛ ".join(parts) + "."


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
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        # Completely blank row → skip silently
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors = _parse_row(row, col_map, HISTORY_LIST_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=row_errors[0].split("»")[0].replace("فیلد «", "") if "فیلد «" in row_errors[0] else "",
            )
            continue
        uid = str(values.get("program_uid") or "").strip()
        if not uid:
            # Empty identity: skip without treating as hard error
            result.skipped += 1
            continue

        if uid in live_uids:
            # Update live program's linked history snapshot is skip — live is source.
            # Still try to keep an archive mirror updated for Excel fields if exists.
            pass

        defaults = {
            k: v
            for k, v in values.items()
            if k not in ("program_uid", "_production_type")
        }
        defaults.setdefault("scrap_qty", 0)
        defaults.setdefault("produced_qty", 0)

        # Keep catalog product display name in sync when code is known
        code = str(defaults.get("product_code") or "").strip()
        new_name = str(defaults.get("product_name") or "").strip()
        if code and new_name:
            from catalog.models import Product

            Product.objects.filter(code=code).update(name=new_name)

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
            # Sync warning — row data was still stored in history
            warn = (
                f"ردیف {row_i} جدول «{table.name}» — فیلد همگام‌سازی برنامه‌ریزی: "
                f"{sync_out.get('error')}"
            )
            result.alarms.append(warn)
            register_alarm(
                title="همگام‌سازی سابقه با برنامه‌ریزی",
                message=warn,
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
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors = _parse_row(row, col_map, HISTORY_DAILY_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
            )
            continue
        uid = str(values.get("program_uid") or "").strip()
        if not uid:
            result.skipped += 1
            continue
        work = values.get("work_date")
        if not work:
            result.skipped += 1
            continue
        rec = ProductionHistoryRecord.objects.filter(program_uid=uid).first()
        if not rec:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=(
                    f"ردیف {row_i} جدول «{table.name}» — فیلد «شناسه تعویض»: "
                    f"مقدار «{uid}» در سوابق یافت نشد (ابتدا سطح لیست سوابق را منتقل کنید)."
                ),
                field_label="شناسه تعویض",
            )
            continue
        extra = rec.extra if isinstance(rec.extra, dict) else {}
        entries = list(extra.get("day_entries") or [])
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
        entries = [e for e in entries if not (isinstance(e, dict) and e.get("date") == work_s)]
        entries.append(snap)
        entries.sort(key=lambda e: str((e or {}).get("date") or ""))
        extra["day_entries"] = entries
        rec.extra = extra
        rec.produced_qty = sum(int(e.get("produced") or 0) for e in entries if isinstance(e, dict))
        rec.scrap_qty = sum(int(e.get("scrap") or 0) for e in entries if isinstance(e, dict))
        rec.transferred_by = user
        rec.source_table_name = table.name
        rec.save()
        result.transferred += 1

    return result


def _transfer_product_info(*, table: ExcelTable, col_map: dict[str, int | None], user) -> TransferResult:
    from catalog.product_data import upsert_product_from_values

    result = TransferResult(destination_id=DESTINATION_PRODUCT_DATA, level_id=LEVEL_PRODUCT_INFO)
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors = _parse_row(row, col_map, PRODUCT_INFO_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
            )
            continue
        if not str(values.get("code") or "").strip():
            result.skipped += 1
            continue
        if not str(values.get("name") or "").strip():
            values["name"] = values["code"]
        try:
            upsert_product_from_values(values)
            result.transferred += 1
        except Exception as exc:  # noqa: BLE001
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}» — فیلد «کد کالا»: {exc}",
                field_label="کد کالا",
            )
    return result


def _transfer_product_bom(*, table: ExcelTable, col_map: dict[str, int | None], user) -> TransferResult:
    from catalog.product_data import upsert_bom_from_values

    result = TransferResult(destination_id=DESTINATION_PRODUCT_DATA, level_id=LEVEL_PRODUCT_BOM)
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors = _parse_row(row, col_map, PRODUCT_BOM_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
            )
            continue
        if not str(values.get("parent_code") or "").strip():
            result.skipped += 1
            continue
        if not str(values.get("component_name") or values.get("component_code") or "").strip():
            result.skipped += 1
            continue
        try:
            upsert_bom_from_values(values)
            result.transferred += 1
        except Exception as exc:  # noqa: BLE001
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}» — فیلد «کد محصول والد»: {exc}",
                field_label="کد محصول والد",
            )
    return result


def _transfer_product_consumables(*, table: ExcelTable, col_map: dict[str, int | None], user) -> TransferResult:
    from catalog.product_data import upsert_consumable_from_values

    result = TransferResult(
        destination_id=DESTINATION_PRODUCT_DATA, level_id=LEVEL_PRODUCT_CONSUMABLES
    )
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors = _parse_row(row, col_map, PRODUCT_CONSUMABLE_FIELDS)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
            )
            continue
        if not str(values.get("product_code") or "").strip():
            result.skipped += 1
            continue
        if not str(values.get("material_name") or values.get("material_code") or "").strip():
            result.skipped += 1
            continue
        try:
            upsert_consumable_from_values(values)
            result.transferred += 1
        except Exception as exc:  # noqa: BLE001
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}» — فیلد «کد محصول»: {exc}",
                field_label="کد محصول",
            )
    return result


_HANDLERS = {
    (DESTINATION_PRODUCTION_HISTORY, LEVEL_HISTORY_LIST): _transfer_history_list,
    (DESTINATION_PRODUCTION_HISTORY, LEVEL_HISTORY_DAILY): _transfer_history_daily,
    (DESTINATION_PRODUCT_DATA, LEVEL_PRODUCT_INFO): _transfer_product_info,
    (DESTINATION_PRODUCT_DATA, LEVEL_PRODUCT_BOM): _transfer_product_bom,
    (DESTINATION_PRODUCT_DATA, LEVEL_PRODUCT_CONSUMABLES): _transfer_product_consumables,
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
