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
DESTINATION_INVENTORY_ORDERS = "inventory_orders"

LEVEL_HISTORY_LIST = "history_list"
LEVEL_HISTORY_DAILY = "history_daily"
LEVEL_PRODUCT_INFO = "product_info"
LEVEL_PRODUCT_BOM = "product_bom"
LEVEL_PRODUCT_CONSUMABLES = "product_consumables"
LEVEL_IO_ORDERS = "orders"
LEVEL_IO_STOCK = "stock"
LEVEL_IO_BOM = "bom"
LEVEL_IO_FORECAST = "forecast"


@dataclass
class DestField:
    key: str
    label: str
    type: str  # string | integer | date | decimal | quantity
    required: bool = False


MODE_TRANSFER = "transfer"
MODE_UPDATE = "update"


@dataclass
class TransferResult:
    destination_id: str
    level_id: str = ""
    mode: str = MODE_TRANSFER
    transferred: int = 0
    failed: int = 0
    skipped: int = 0
    alarms: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    # Cells that failed parsing/transfer: {row: 1-based data row, col: 0-based}
    error_cells: list[dict] = field(default_factory=list)
    table_deleted: bool = False
    redirect_url: str = ""
    # Chunked transfer progress (optional)
    total_rows: int = 0
    offset: int = 0
    next_offset: int = 0
    done: bool = True
    percent: int = 100


# Exact columns of «سوابق تولید» list (+ end date for status inference)
HISTORY_LIST_FIELDS: list[DestField] = [
    # شناسه برای کلید لیست لازم است؛ کد کالا اختیاری (در سطح روزانه هم هست).
    DestField("program_uid", "شناسه تعویض", "string", required=True),
    DestField("plan_number", "شماره برنامه", "string", required=True),
    DestField("plan_date", "تاریخ برنامه‌ریزی", "date"),
    DestField("unit_number", "شماره واحد", "integer"),
    DestField("machine_number", "شماره دستگاه", "string"),
    DestField("product_code", "کد کالا", "string"),
    DestField("product_name", "نام جنس", "string"),
    DestField("mold_number", "شماره قالب", "string"),
    DestField("unique_code", "کد یکتا", "string", required=True),
    DestField("status", "وضعیت", "string"),
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
    DestField("product_code", "کد کالا", "string"),
    DestField("status", "وضعیت", "string"),
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

IO_ORDER_FIELDS: list[DestField] = [
    DestField("order_ref", "شماره سفارش", "string"),
    DestField("product_code", "کد کالا", "string", required=True),
    DestField("product_name", "نام کالا", "string"),
    DestField("quantity", "مقدار سفارش", "integer", required=True),
    DestField("delivery_date", "تاریخ تحویل", "date"),
    DestField("priority", "اولویت (عدد کمتر = بالاتر)", "integer"),
    DestField("is_backlog", "سفارش معوق", "string"),
    DestField("customer_name", "مشتری", "string"),
    DestField("notes", "توضیحات", "string"),
]

IO_STOCK_FIELDS: list[DestField] = [
    DestField("product_code", "کد کالا", "string", required=True),
    DestField("product_name", "نام کالا", "string"),
    DestField("stock_finished", "موجودی محصول", "integer"),
    DestField("stock_unassembled", "موجودی مونتاژ‌نشده", "integer"),
    DestField("depot_ceiling", "سقف دپو", "integer"),
]

IO_FORECAST_FIELDS: list[DestField] = [
    DestField("product_code", "کد کالا", "string", required=True),
    DestField("product_name", "نام کالا", "string"),
    DestField("period_label", "دوره پیش‌بینی", "string"),
    DestField("quantity", "مقدار پیش‌بینی", "integer"),
    DestField("notes", "توضیحات", "string"),
]


def _fields_payload(fields: list[DestField]) -> list[dict[str, Any]]:
    return [
        {"key": f.key, "label": f.label, "type": f.type, "required": f.required}
        for f in fields
    ]


def list_destinations() -> list[dict[str, Any]]:
    """Static destination tree (labels from DestField literals). Used by harvest."""
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
        {
            "id": DESTINATION_INVENTORY_ORDERS,
            "label": "بررسی موجودی و سفارشات",
            "levels": [
                {
                    "id": LEVEL_IO_ORDERS,
                    "label": "سفارشات هفتگی و معوق",
                    "fields": _fields_payload(IO_ORDER_FIELDS),
                },
                {
                    "id": LEVEL_IO_STOCK,
                    "label": "موجودی و سقف دپو",
                    "fields": _fields_payload(IO_STOCK_FIELDS),
                },
                {
                    "id": LEVEL_IO_BOM,
                    "label": "ساختار BOM",
                    "fields": _fields_payload(PRODUCT_BOM_FIELDS),
                },
                {
                    "id": LEVEL_IO_FORECAST,
                    "label": "پیش‌بینی فروش (ذخیره — فعلاً بدون اجرا)",
                    "fields": _fields_payload(IO_FORECAST_FIELDS),
                },
            ],
        },
    ]


# Dialog / page chrome for Excel transfer — harvested into SystemNamingKey.
TRANSFER_UI_LABELS: dict[str, str] = {
    "transfer.ui.dialog.title_transfer": "انتقال داده جدول",
    "transfer.ui.dialog.title_update": "بروزرسانی داده جدول",
    "transfer.ui.dialog.hint_transfer": (
        "بخش مقصد و سطح را انتخاب کنید؛ سرستون‌های همان سطح نمایش داده می‌شوند. "
        "هر ستون اکسل فقط به یک فیلد نگاشت می‌شود. جدول پس از انتقال حذف نمی‌شود."
    ),
    "transfer.ui.dialog.hint_update": (
        "فقط ردیف‌های از قبل موجود در سامانه اصلاح می‌شوند؛ ردیف جدید اضافه نمی‌شود. "
        "نگاشت ستون‌ها مانند انتقال است و جدول اکسل حذف نمی‌شود."
    ),
    "transfer.ui.dialog.errors_title": "جزئیات خطای انتقال",
    "transfer.ui.label.destination": "بخش مقصد",
    "transfer.ui.label.level": "انتخاب سطح",
    "transfer.ui.col.dest_field": "ستون مقصد سامانه",
    "transfer.ui.col.type": "نوع",
    "transfer.ui.col.excel_col": "ستون متناظر اکسل",
    "transfer.ui.btn.transfer": "انتقال",
    "transfer.ui.btn.update": "بروزرسانی",
    "transfer.ui.btn.cancel": "انصراف",
    "transfer.ui.btn.close": "بستن",
    "transfer.ui.btn.open_transfer": "انتقال داده",
    "transfer.ui.btn.open_update": "بروزرسانی",
    "transfer.ui.page.tables_heading": "جداول فایل",
    "transfer.ui.import.dialog_pick_table": "انتخاب Table برای ورود",
    "transfer.ui.import.dialog_view_table": "مشاهده و انتخاب Table",
    "transfer.ui.import.dialog_view_sheet": "مشاهده و انتخاب Sheet",
}


def list_destinations_for_ui() -> list[dict[str, Any]]:
    """Destinations with naming-registry labels; inactive dest/level/field omitted."""
    from catalog.models import SystemNamingKey

    base = list_destinations()
    keys: list[str] = []
    for dest in base:
        dest_id = dest["id"]
        keys.append(f"transfer.dest.{dest_id}")
        for level in dest.get("levels") or []:
            level_id = level["id"]
            keys.append(f"transfer.level.{dest_id}.{level_id}")
            for field in level.get("fields") or []:
                keys.append(f"transfer.field.{dest_id}.{level_id}.{field['key']}")

    rows = {
        r.key: r
        for r in SystemNamingKey.objects.filter(key__in=keys).only("key", "label", "is_active")
    }

    def _resolve(key: str, default: str) -> tuple[bool, str]:
        row = rows.get(key)
        if row is None:
            return True, default
        return bool(row.is_active), (row.label or default)

    out: list[dict[str, Any]] = []
    for dest in base:
        dest_id = dest["id"]
        dest_ok, dest_label = _resolve(f"transfer.dest.{dest_id}", dest["label"])
        if not dest_ok:
            continue
        levels_out: list[dict[str, Any]] = []
        for level in dest.get("levels") or []:
            level_id = level["id"]
            level_ok, level_label = _resolve(
                f"transfer.level.{dest_id}.{level_id}", level["label"]
            )
            if not level_ok:
                continue
            fields_out: list[dict[str, Any]] = []
            for field in level.get("fields") or []:
                fkey = field["key"]
                field_ok, field_label = _resolve(
                    f"transfer.field.{dest_id}.{level_id}.{fkey}", field["label"]
                )
                if not field_ok:
                    continue
                fields_out.append({**field, "label": field_label})
            levels_out.append({**level, "label": level_label, "fields": fields_out})
        if levels_out:
            out.append({**dest, "label": dest_label, "levels": levels_out})
    return out


def transfer_ui_labels_resolved() -> dict[str, str]:
    """Resolved chrome labels for the transfer/import dialogs."""
    from catalog.models import SystemNamingKey

    keys = list(TRANSFER_UI_LABELS.keys())
    rows = {
        r.key: r
        for r in SystemNamingKey.objects.filter(key__in=keys).only("key", "label", "is_active")
    }
    out: dict[str, str] = {}
    for key, default in TRANSFER_UI_LABELS.items():
        row = rows.get(key)
        if row is not None and not row.is_active:
            # Hidden chrome still needs a fallback string in the DOM; keep default.
            out[key] = default
            continue
        out[key] = (row.label if row and row.label else default)
    # Short aliases used by JS / templates
    return {
        "title_transfer": out["transfer.ui.dialog.title_transfer"],
        "title_update": out["transfer.ui.dialog.title_update"],
        "hint_transfer": out["transfer.ui.dialog.hint_transfer"],
        "hint_update": out["transfer.ui.dialog.hint_update"],
        "errors_title": out["transfer.ui.dialog.errors_title"],
        "label_destination": out["transfer.ui.label.destination"],
        "label_level": out["transfer.ui.label.level"],
        "col_dest_field": out["transfer.ui.col.dest_field"],
        "col_type": out["transfer.ui.col.type"],
        "col_excel_col": out["transfer.ui.col.excel_col"],
        "btn_transfer": out["transfer.ui.btn.transfer"],
        "btn_update": out["transfer.ui.btn.update"],
        "btn_cancel": out["transfer.ui.btn.cancel"],
        "btn_close": out["transfer.ui.btn.close"],
        "btn_open_transfer": out["transfer.ui.btn.open_transfer"],
        "btn_open_update": out["transfer.ui.btn.open_update"],
        "tables_heading": out["transfer.ui.page.tables_heading"],
        "import_pick_table": out["transfer.ui.import.dialog_pick_table"],
        "import_view_table": out["transfer.ui.import.dialog_view_table"],
        "import_view_sheet": out["transfer.ui.import.dialog_view_sheet"],
    }


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
    if destination_id == DESTINATION_INVENTORY_ORDERS:
        if level_id == LEVEL_IO_STOCK:
            return IO_STOCK_FIELDS
        if level_id == LEVEL_IO_BOM:
            return PRODUCT_BOM_FIELDS
        if level_id == LEVEL_IO_FORECAST:
            return IO_FORECAST_FIELDS
        return IO_ORDER_FIELDS
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


def _extract_number_token(raw: str) -> str | None:
    """First integer/decimal token from mixed text like «۲۰ ساعت» or ``12.5 kg``."""
    text = _normalize_digits(str(raw or "")).strip()
    if not text:
        return None
    text = (
        text.replace("٬", "")
        .replace(",", "")
        .replace("٫", ".")
        .replace("\u200c", "")
    )
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return match.group(0) if match else None


def _parse_integer(raw: str, label: str) -> tuple[int | None, str | None]:
    if raw == "":
        return None, None
    cleaned = _normalize_digits(raw).replace(",", "").replace("٬", "").replace(" ", "")
    try:
        return int(float(cleaned)), None
    except (TypeError, ValueError):
        token = _extract_number_token(raw)
        if token is not None:
            try:
                return int(float(token)), None
            except (TypeError, ValueError):
                pass
        return None, f"فیلد «{label}»: مقدار «{raw}» عدد صحیح معتبر نیست."


def _parse_decimal(raw: str, label: str) -> tuple[Any, str | None]:
    if raw == "":
        return None, None
    cleaned = (
        _normalize_digits(raw)
        .replace(",", "")
        .replace("٬", "")
        .replace("٫", ".")
        .replace(" ", "")
    )
    try:
        return Decimal(cleaned), None
    except Exception:  # noqa: BLE001
        token = _extract_number_token(raw)
        if token is not None:
            try:
                return Decimal(token), None
            except Exception:  # noqa: BLE001
                pass
        return None, f"فیلد «{label}»: مقدار «{raw}» عدد اعشاری معتبر نیست."


def _excel_col_hint(
    col_map: dict[str, int | None],
    headers: list | None,
    field_key: str,
) -> str:
    """Human hint naming the mapped Excel header / column index."""
    idx = col_map.get(field_key)
    if idx is None:
        return ""
    try:
        idx_i = int(idx)
    except (TypeError, ValueError):
        return ""
    header = ""
    if isinstance(headers, list) and 0 <= idx_i < len(headers):
        header = str(headers[idx_i] or "").strip()
    if header:
        return f" (ستون اکسل «{header}» / ستون {idx_i + 1})"
    return f" (ستون اکسل شماره {idx_i + 1})"


def _normalize_digits(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to ASCII."""
    from catalog.qty_parse import normalize_digits

    return normalize_digits(text)


def _parse_date(raw: str, label: str) -> tuple[date | None, str | None]:
    """Parse Excel/Jalali/Gregorian date strings into Jalali-encoded ``date``.

    History ``DateField``s store شمسی Y/M/D as ``date(1405, 6, 1)`` so the UI
    shows ``1405/06/01`` (not میلادی). Gregorian inputs and Excel serials are
    converted to their Jalali equivalent before storage.

    Supports:
    - Excel serials (e.g. ``46257`` → شمسی ``1405/06/01``)
    - Jalali ``YYYY/MM/DD`` with years 1200–1500 (e.g. ``1405/06/01``)
    - Gregorian ISO / slash / dash forms (converted to شمسی)
    - Datetime strings with a time component
    """
    from catalog.jalali_dates import (
        coerce_to_jalali_storage,
        excel_serial_to_gregorian,
        is_gregorian_year,
        is_jalali_year,
        jalali_to_storage,
    )
    import jdatetime

    if raw == "":
        return None, None
    text = _normalize_digits(str(raw).strip())
    # Drop time portion: "2026-08-23 00:00:00" / ISO
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    text = text.strip()

    def _ok(j: jdatetime.date) -> tuple[date, None]:
        return jalali_to_storage(j), None

    # Excel serial number (value behind formats like [$-fa-IR,96]yyyy/mm/dd)
    if re.fullmatch(r"\d+(\.\d+)?", text):
        try:
            serial = int(float(text))
            if 20000 <= serial <= 100000:
                g = excel_serial_to_gregorian(serial)
                if g is not None:
                    return _ok(jdatetime.date.fromgregorian(date=g))
            # Compact YYYYMMDD (Jalali or Gregorian)
            if len(text) == 8 and text.isdigit():
                y, m, d = int(text[:4]), int(text[4:6]), int(text[6:8])
                if is_jalali_year(y):
                    return _ok(jdatetime.date(y, m, d))
                if is_gregorian_year(y):
                    return _ok(jdatetime.date.fromgregorian(date=date(y, m, d)))
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
                    if is_jalali_year(y):
                        return _ok(jdatetime.date(y, m, d))
                    if is_gregorian_year(y):
                        return _ok(jdatetime.date.fromgregorian(date=date(y, m, d)))
                except Exception as exc:  # noqa: BLE001
                    return None, (
                        f"فیلد «{label}»: تاریخ «{raw}» نامعتبر است "
                        f"(سال {y} به‌عنوان شمسی/میلادی قابل تبدیل نیست: {exc})."
                    )
            # Day-first: DD/MM/YYYY
            if c >= 1000:
                d, m, y = a, b, c
                try:
                    if is_jalali_year(y):
                        return _ok(jdatetime.date(y, m, d))
                    if is_gregorian_year(y):
                        return _ok(jdatetime.date.fromgregorian(date=date(y, m, d)))
                except Exception as exc:  # noqa: BLE001
                    return None, (
                        f"فیلد «{label}»: تاریخ «{raw}» نامعتبر است ({exc})."
                    )

    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            stored = coerce_to_jalali_storage(parsed)
            if stored is not None:
                return stored, None
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
    error_cols: list[int] | None = None,
) -> None:
    result.failed += 1
    result.alarms.append(msg)
    seen = {(c.get("row"), c.get("col")) for c in result.error_cells}
    for col in error_cols or []:
        try:
            ci = int(col)
        except (TypeError, ValueError):
            continue
        if ci < 0:
            continue
        key = (row_i, ci)
        if key in seen:
            continue
        seen.add(key)
        result.error_cells.append({"row": row_i, "col": ci})
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


def _apply_unit_machine_from_label(values: dict[str, Any], raw: str) -> None:
    """Fill unit_number / machine_number from combined Excel labels when missing."""
    from catalog.qty_parse import parse_unit_machine_label

    unit, machine = parse_unit_machine_label(raw)
    if unit is not None and values.get("unit_number") is None:
        values["unit_number"] = unit
    if machine is not None and not str(values.get("machine_number") or "").strip():
        values["machine_number"] = machine


def _parse_row(
    row: list,
    col_map: dict[str, int | None],
    fields: list[DestField],
    headers: list | None = None,
) -> tuple[dict[str, Any], list[str], list[int]]:
    """Parse mapped cells. Empty cells are skipped (not errors).

    Returns (values, errors, error_col_indexes).
    """
    from catalog.qty_parse import (
        apply_production_type_to_name,
        extract_qty_and_production_type,
        parse_unit_machine_label,
    )

    values: dict[str, Any] = {}
    errors: list[str] = []
    error_cols: list[int] = []
    prod_type = ""

    def _mark_col(f_key: str) -> None:
        idx = col_map.get(f_key)
        if idx is not None and idx not in error_cols:
            error_cols.append(idx)

    for f in fields:
        # Unmapped destination field → leave empty, no error
        if col_map.get(f.key) is None:
            continue
        raw = _cell(row, col_map.get(f.key))
        # Empty Excel cell → leave empty, no error
        if raw == "":
            continue
        col_hint = _excel_col_hint(col_map, headers, f.key)
        if f.type == "quantity":
            qty, ptype, err = extract_qty_and_production_type(raw)
            if err:
                errors.append(f"فیلد «{f.label}»{col_hint}: {err}")
                _mark_col(f.key)
            else:
                values[f.key] = qty
                if ptype:
                    prod_type = ptype
            continue
        if f.key in {"unit_number", "machine_number"}:
            # Combined labels like «دستگاه 6 واحد1» or «6/1» may be mapped to either column
            unit, machine = parse_unit_machine_label(raw)
            has_label = ("دستگاه" in raw) or ("واحد" in raw)
            combined = unit is not None and machine is not None
            if (has_label or combined) and (unit is not None or machine is not None):
                _apply_unit_machine_from_label(values, raw)
                continue
            if f.key == "unit_number":
                parsed, err = _parse_integer(raw, f.label)
                if err:
                    # Re-attach excel column hint after parser label message
                    if err.startswith(f"فیلد «{f.label}»"):
                        err = err.replace(f"فیلد «{f.label}»", f"فیلد «{f.label}»{col_hint}", 1)
                    errors.append(err)
                    _mark_col(f.key)
                elif parsed is not None:
                    values["unit_number"] = parsed
            else:
                # machine_number: keep digits when possible, else raw string
                if machine is not None:
                    values["machine_number"] = machine
                else:
                    values["machine_number"] = raw
            continue
        parsed, err = _PARSERS[f.type](raw, f.label)
        if err:
            if err.startswith(f"فیلد «{f.label}»"):
                err = err.replace(f"فیلد «{f.label}»", f"فیلد «{f.label}»{col_hint}", 1)
            errors.append(err)
            _mark_col(f.key)
        else:
            values[f.key] = parsed

    if prod_type:
        name = str(values.get("product_name") or "").strip()
        if name:
            values["product_name"] = apply_production_type_to_name(name, prod_type)
        values["_production_type"] = prod_type
    return values, errors, error_cols


def _normalize_temp_stop_dates(values: dict[str, Any]) -> None:
    """توقف موقت must not keep an end date (that would mark the mold finished)."""
    from production.sync import _normalize_status_label

    status_raw = str(values.get("status") or "").strip()
    if not status_raw:
        return
    if _normalize_status_label(status_raw) == "temp_stop":
        values["actual_end_date"] = None



def _format_row_errors(row_i: int, table_name: str, errors: list[str]) -> str:
    return f"ردیف {row_i} جدول «{table_name}» — " + " | ".join(errors)


def _first_field_label(errors: list[str]) -> str:
    for err in errors or []:
        m = re.search(r"فیلد «([^»]+)»", str(err))
        if m:
            return m.group(1)
    return ""


def _classify_alarm(msg: str) -> tuple[str, str, str]:
    """Return (category_key, title, explanation) for a raw alarm line."""
    text = msg or ""
    if "ساختار ردیف نامعتبر" in text:
        return (
            "row_structure",
            "ساختار ردیف نامعتبر",
            "بعضی ردیف‌های اکسل به‌صورت آرایهٔ معتبر خوانده نشده‌اند. "
            "فایل را دوباره ذخیره کنید یا ردیف‌های خراب/ادغام‌شده را اصلاح کنید.",
        )
    if "نگاشت ستون" in text or "خارج از محدوده جدول" in text:
        return (
            "column_mapping",
            "مشکل نگاشت ستون اکسل",
            "ستون انتخاب‌شده برای یک فیلد مقصد اشتباه یا خارج از محدوده جدول است. "
            "در دیالوگ انتقال، نگاشت هر فیلد را با سرستون درست اکسل دوباره تنظیم کنید.",
        )
    if "تاریخ" in text and ("نامعتبر" in text or "معتبر نیست" in text):
        return (
            "invalid_date",
            "تاریخ نامعتبر",
            "مقدار تاریخ در اکسل قابل تبدیل نیست. فرمت پیشنهادی جلالی مانند "
            "۱۴۰۳/۰۱/۱۵ یا معادل میلادی معتبر است؛ سلول‌های متنیِ اشتباه یا خالیِ اجباری را اصلاح کنید.",
        )
    if "عدد صحیح معتبر نیست" in text:
        return (
            "invalid_integer",
            "عدد صحیح نامعتبر",
            "فیلدهای عددی صحیح (مثل تعداد، شماره واحد، حفره) باید فقط رقم باشند. "
            "متن، فاصله، یا برچسب ترکیبی را از سلول حذف کنید؛ برای «دستگاه/واحد» از برچسب استاندارد استفاده کنید.",
        )
    if "عدد اعشاری معتبر نیست" in text:
        return (
            "invalid_decimal",
            "عدد اعشاری / وزن نامعتبر",
            "مقادیر اعشاری یا وزن باید عدد باشند (ممیز نقطه یا اسلش فارسی قابل قبول است). "
            "واحد یا متن اضافه داخل سلول را جدا کنید. نام فیلد مقصد و ستون اکسل در نمونه‌ها آمده است.",
        )
    if "مقدار" in text and ("عدد" in text or "کمیت" in text or "quantity" in text.lower()):
        return (
            "invalid_quantity",
            "مقدار تولید نامعتبر",
            "ستون مقدار تولید باید عدد باشد؛ در صورت داشتن پسوند نوع تولید، "
            "فرمتی مانند «۱۲۰ تزریق» قابل قبول است. متن بدون عدد را اصلاح کنید.",
        )
    if "بدون شناسه" in text or (
        "شناسه تعویض" in text and ("یافت" in text or "وجود" in text or "ندارد" in text)
    ):
        return (
            "missing_uid",
            "شناسه تعویض خالی یا ناموجود",
            "ردیف‌هایی که شناسهٔ تعویض ندارند یا شناسه در سامانه پیدا نمی‌شود منتقل نمی‌شوند. "
            "ستون شناسه را نگاشت کنید و برای بروزرسانی فقط ردیف‌های از قبل موجود را بفرستید.",
        )
    if "کد کالا" in text or "کد محصول" in text or "کد محصول والد" in text:
        return (
            "product_code",
            "مشکل کد کالا / محصول",
            "کد کالا در ردیف خالی، تکراریِ نامعتبر، یا با دادهٔ موجود ناسازگار است. "
            "ابتدا کالا را در «دیتای محصولات» بسازید یا کد اکسل را با کد سامانه یکسان کنید.",
        )
    if "همگام‌سازی برنامه‌ریزی" in text:
        return (
            "planning_sync",
            "خطا در همگام‌سازی با برنامه‌ریزی",
            "سابقه منتقل شد ولی ساخت/به‌روزرسانی برنامهٔ هفتگی برای برخی ردیف‌ها شکست خورد. "
            "آلارم سیستم و شماره برنامه را بررسی کنید.",
        )
    if "فیلد «" in text and ("معتبر نیست" in text or "نامعتبر" in text):
        return (
            "field_value",
            "مقدار فیلد نامعتبر",
            "یک یا چند سلول با نوع فیلد مقصد سازگار نیستند. "
            "متن خطا را برای نام فیلد ببینید و مقدار همان ستون اکسل را اصلاح کنید.",
        )
    return (
        "other",
        "سایر خطاهای ردیف",
        "خطاهایی که در دسته‌های بالا جا نگرفتند. جزئیات هر ردیف را در فهرست نمونه‌ها یا آلارم‌های سیستم ببینید.",
    )


def group_transfer_alarms(
    alarms: list[str],
    *,
    max_examples: int = 3,
) -> list[dict[str, Any]]:
    """Collapse many similar Excel-transfer alarms into a few explained groups."""
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in alarms or []:
        msg = str(raw or "").strip()
        if not msg:
            continue
        key, title, explanation = _classify_alarm(msg)
        if key not in buckets:
            buckets[key] = {
                "key": key,
                "title": title,
                "explanation": explanation,
                "count": 0,
                "examples": [],
                "rows": [],
                "fields": [],
                "excel_columns": [],
            }
            order.append(key)
        bucket = buckets[key]
        bucket["count"] += 1
        m = re.search(r"ردیف\s+(\d+)", msg)
        if m:
            row_n = int(m.group(1))
            if row_n not in bucket["rows"]:
                bucket["rows"].append(row_n)
        for field_name in re.findall(r"فیلد «([^»]+)»", msg):
            if field_name and field_name not in bucket["fields"]:
                bucket["fields"].append(field_name)
        for col_name in re.findall(r"ستون اکسل «([^»]+)»", msg):
            if col_name and col_name not in bucket["excel_columns"]:
                bucket["excel_columns"].append(col_name)
        if len(bucket["examples"]) < max_examples:
            bucket["examples"].append(msg)
    groups = [buckets[k] for k in order]
    for g in groups:
        rows = g["rows"]
        if rows:
            shown = "، ".join(str(n) for n in rows[:12])
            more = f" و {len(rows) - 12} ردیف دیگر" if len(rows) > 12 else ""
            g["rows_label"] = f"ردیف‌های درگیر: {shown}{more}"
        else:
            g["rows_label"] = ""
        fields = g["fields"]
        excel_cols = g["excel_columns"]
        parts: list[str] = []
        if fields:
            parts.append("فیلد مقصد: " + "، ".join(fields[:8]))
        if excel_cols:
            parts.append("ستون اکسل: " + "، ".join(excel_cols[:8]))
        g["fields_label"] = " | ".join(parts)
        if fields:
            # Put column/field names in the group title so the alert is actionable
            shown_fields = "، ".join(fields[:3])
            more_f = f" و {len(fields) - 3} فیلد دیگر" if len(fields) > 3 else ""
            g["title"] = f"{g['title']} ({shown_fields}{more_f})"
            g["explanation"] = (
                f"{g['explanation']} "
                f"فیلدهای درگیر: { '، '.join(fields) }."
                + (f" ستون‌های اکسل: { '، '.join(excel_cols) }." if excel_cols else "")
            )
    return groups


def transfer_result_message(result: TransferResult) -> str:
    """Human message: never claim full success when failures exist."""
    is_update = result.mode == MODE_UPDATE
    verb_done = "بروزرسانی شد" if is_update else "منتقل شد"
    verb_noun = "بروزرسانی" if is_update else "انتقال"
    parts = []
    if result.transferred:
        parts.append(f"{result.transferred} ردیف {verb_done}")
    if result.failed:
        parts.append(f"{result.failed} ردیف با خطا")
    if result.skipped:
        if is_update:
            parts.append(f"{result.skipped} ردیف بدون سابقه موجود / خالی رد شد")
        else:
            parts.append(f"{result.skipped} ردیف خالی/بدون شناسه رد شد")
    if not parts:
        return f"هیچ ردیفی برای {verb_noun} یافت نشد."
    if result.failed and not result.transferred:
        base = f"{verb_noun} ناموفق بود: " + "؛ ".join(parts) + "."
    elif result.failed:
        base = f"{verb_noun} ناقص انجام شد: " + "؛ ".join(parts) + "."
    elif result.skipped and result.transferred:
        base = f"{verb_noun} انجام شد: " + "؛ ".join(parts) + "."
    else:
        base = f"{verb_noun} با موفقیت انجام شد: " + "؛ ".join(parts) + "."

    if result.failed and result.alarms:
        groups = group_transfer_alarms(result.alarms)
        if groups:
            bits = [f"{g['title']} ({g['count']} مورد)" for g in groups[:5]]
            base += " انواع خطای ردیف: " + "؛ ".join(bits) + "."
    if getattr(result, "conflicts", None):
        base += (
            f" همچنین {len(result.conflicts)} تداخل تولید "
            f"(در حال تولید/توقف موقت روی یک دستگاه) شناسایی شد — "
            f"ردیف‌های سالم منتقل شده‌اند و جدا از خطا قابل مشاهده‌اند."
        )
    return base


def _transfer_history_list(
    *,
    table: ExcelTable,
    col_map: dict[str, int | None],
    user,
    mode: str = MODE_TRANSFER,
    offset: int = 0,
    limit: int | None = None,
) -> TransferResult:
    from production.models import ProductionHistoryRecord, ProductionProgram
    from production.sync import check_history_machine_conflicts, sync_history_record_to_planning

    result = TransferResult(
        destination_id=DESTINATION_PRODUCTION_HISTORY,
        level_id=LEVEL_HISTORY_LIST,
        mode=mode,
    )
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    total = len(rows)
    offset = max(0, int(offset or 0))
    if limit is None:
        chunk_rows = rows[offset:]
        next_offset = total
        done = True
    else:
        limit = max(1, min(int(limit), 200))
        chunk_rows = rows[offset : offset + limit]
        next_offset = offset + len(chunk_rows)
        done = next_offset >= total
    result.total_rows = total
    result.offset = offset
    result.next_offset = next_offset
    result.done = done
    result.percent = 100 if total == 0 else min(100, int(round(100 * next_offset / total)))

    live_uids = set()
    for p in ProductionProgram.objects.select_related("item").all():
        uid = (p.resolved_uid or "").strip()
        if uid:
            live_uids.add(uid)

    for local_i, row in enumerate(chunk_rows):
        row_i = offset + local_i + 1
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        # Completely blank row → skip silently
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, HISTORY_LIST_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        uid = str(values.get("program_uid") or "").strip()
        if not uid:
            # Empty identity: skip without treating as hard error
            result.skipped += 1
            continue

        unique_code = str(values.get("unique_code") or "").strip()
        if not unique_code:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=(
                    f"ردیف {row_i} جدول «{table.name}» — فیلد «کد یکتا» خالی است؛ "
                    f"انتقال به سوابق تولید مجاز نیست."
                ),
                field_label="کد یکتا",
                error_cols=(
                    [col_map["unique_code"]]
                    if col_map.get("unique_code") is not None
                    else []
                ),
            )
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
        _normalize_temp_stop_dates(defaults)

        # Keep catalog product display name in sync when code is known
        code = str(defaults.get("product_code") or "").strip()
        new_name = str(defaults.get("product_name") or "").strip()
        if code and new_name:
            from catalog.models import Product

            Product.objects.filter(code=code).update(name=new_name)

        # Normalize plan number for stable grouping in planning
        if "plan_number" in defaults and defaults["plan_number"] is not None:
            from production.sync import normalize_plan_number

            defaults["plan_number"] = normalize_plan_number(defaults["plan_number"])

        rec = ProductionHistoryRecord.objects.filter(program_uid=uid).first()
        if rec:
            for key, val in defaults.items():
                setattr(rec, key, val)
            rec.source_table_name = table.name
            rec.transferred_by = user
            rec.save()
        elif mode == MODE_UPDATE:
            # بروزرسانی: فقط ردیف‌های موجود؛ بدون افزودن جدید
            result.skipped += 1
            continue
        else:
            rec = ProductionHistoryRecord.objects.create(
                program_uid=uid,
                source_table_name=table.name,
                transferred_by=user,
                extra={"excel_headers": headers, "excel_row_index": row_i},
                **{k: defaults[k] for k in defaults},
            )

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

    if done:
        from production.conflicts import conflicts_as_dicts
        from production.sync import ensure_running_history_in_production

        ensure_running_history_in_production(user=user)
        check_history_machine_conflicts()
        result.conflicts = conflicts_as_dicts()
    return result


def _transfer_history_daily(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from production.models import ProductionHistoryRecord
    from production.sync import (
        _normalize_status_label,
        sync_history_record_to_planning,
    )

    result = TransferResult(
        destination_id=DESTINATION_PRODUCTION_HISTORY,
        level_id=LEVEL_HISTORY_DAILY,
        mode=mode,
    )
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []

    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, HISTORY_DAILY_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
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
            if mode == MODE_UPDATE:
                result.skipped += 1
                continue
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

        # سطح دوم: کد کالا و وضعیت روی خود سابقه هم به‌روز می‌شود
        code = str(values.get("product_code") or "").strip()
        if code:
            rec.product_code = code
        status_raw = str(values.get("status") or "").strip()
        if status_raw:
            rec.status = status_raw
            normalized = _normalize_status_label(status_raw)
            # Keep date-based inference consistent when status says finished/running
            if normalized == "finished" and not rec.actual_end_date and work:
                rec.actual_end_date = work
            if normalized == "running" and not rec.actual_start_date and work:
                rec.actual_start_date = work
            if normalized == "temp_stop":
                # توقف موقت is still occupying — clear end date so hub keeps it.
                rec.actual_end_date = None
                if not rec.actual_start_date and work:
                    rec.actual_start_date = work

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
            "program_uid": uid,
            "product_code": rec.product_code or code or "",
            "status": rec.status or status_raw or "",
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

        # Push running quantities into ثبت و کنترل تولید
        sync_history_record_to_planning(rec, user=user)
        result.transferred += 1

    from production.sync import ensure_running_history_in_production

    ensure_running_history_in_production(user=user)
    return result


def _transfer_product_info(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from catalog.product_data import upsert_product_from_values

    result = TransferResult(
        destination_id=DESTINATION_PRODUCT_DATA, level_id=LEVEL_PRODUCT_INFO, mode=mode
    )
    update_only = mode == MODE_UPDATE
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, PRODUCT_INFO_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        if not str(values.get("code") or "").strip():
            result.skipped += 1
            continue
        if not str(values.get("name") or "").strip():
            values["name"] = values["code"]
        try:
            product = upsert_product_from_values(values, update_only=update_only)
            if product is None:
                result.skipped += 1
                continue
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


def _transfer_product_bom(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from catalog.product_data import upsert_bom_from_values

    result = TransferResult(
        destination_id=DESTINATION_PRODUCT_DATA, level_id=LEVEL_PRODUCT_BOM, mode=mode
    )
    update_only = mode == MODE_UPDATE
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, PRODUCT_BOM_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        if not str(values.get("parent_code") or "").strip():
            result.skipped += 1
            continue
        if not str(values.get("component_name") or values.get("component_code") or "").strip():
            result.skipped += 1
            continue
        try:
            line = upsert_bom_from_values(values, update_only=update_only)
            if line is None:
                result.skipped += 1
                continue
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


def _transfer_product_consumables(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from catalog.product_data import upsert_consumable_from_values

    result = TransferResult(
        destination_id=DESTINATION_PRODUCT_DATA,
        level_id=LEVEL_PRODUCT_CONSUMABLES,
        mode=mode,
    )
    update_only = mode == MODE_UPDATE
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, PRODUCT_CONSUMABLE_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        if not str(values.get("product_code") or "").strip():
            result.skipped += 1
            continue
        if not str(values.get("material_name") or values.get("material_code") or "").strip():
            result.skipped += 1
            continue
        try:
            row_obj = upsert_consumable_from_values(values, update_only=update_only)
            if row_obj is None:
                result.skipped += 1
                continue
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


def _transfer_io_orders(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from planning.inventory_orders import upsert_order_from_values

    result = TransferResult(
        destination_id=DESTINATION_INVENTORY_ORDERS,
        level_id=LEVEL_IO_ORDERS,
        mode=mode,
    )
    update_only = mode == MODE_UPDATE
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, IO_ORDER_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        try:
            obj = upsert_order_from_values(
                values, update_only=update_only, source_table=table.name or ""
            )
            if obj is None:
                result.skipped += 1
                continue
            result.transferred += 1
        except Exception as exc:  # noqa: BLE001
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}» — {exc}",
                field_label="کد کالا",
            )
    return result


def _transfer_io_stock(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from planning.inventory_orders import upsert_stock_from_values

    result = TransferResult(
        destination_id=DESTINATION_INVENTORY_ORDERS,
        level_id=LEVEL_IO_STOCK,
        mode=mode,
    )
    update_only = mode == MODE_UPDATE
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, IO_STOCK_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        # Normalize code key for upsert helper
        if values.get("product_code") and not values.get("code"):
            values["code"] = values["product_code"]
        try:
            obj = upsert_stock_from_values(values, update_only=update_only)
            if obj is None:
                result.skipped += 1
                continue
            result.transferred += 1
        except Exception as exc:  # noqa: BLE001
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}» — {exc}",
                field_label="کد کالا",
            )
    return result


def _transfer_io_forecast(
    *, table: ExcelTable, col_map: dict[str, int | None], user, mode: str = MODE_TRANSFER
) -> TransferResult:
    from planning.inventory_orders import upsert_forecast_from_values

    result = TransferResult(
        destination_id=DESTINATION_INVENTORY_ORDERS,
        level_id=LEVEL_IO_FORECAST,
        mode=mode,
    )
    update_only = mode == MODE_UPDATE
    headers = table.headers if isinstance(table.headers, list) else []
    rows = table.rows if isinstance(table.rows, list) else []
    for row_i, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            _row_alarm(result, table=table, row_i=row_i, msg=f"ردیف {row_i}: ساختار ردیف نامعتبر است.")
            continue
        if not any(str(c).strip() for c in row if c is not None):
            result.skipped += 1
            continue
        values, row_errors, error_cols = _parse_row(row, col_map, IO_FORECAST_FIELDS, headers)
        if row_errors:
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=_format_row_errors(row_i, table.name, row_errors),
                field_label=_first_field_label(row_errors),
                error_cols=error_cols,
            )
            continue
        try:
            obj = upsert_forecast_from_values(
                values, update_only=update_only, source_table=table.name or ""
            )
            if obj is None:
                result.skipped += 1
                continue
            result.transferred += 1
        except Exception as exc:  # noqa: BLE001
            _row_alarm(
                result,
                table=table,
                row_i=row_i,
                msg=f"ردیف {row_i} جدول «{table.name}» — {exc}",
                field_label="کد کالا",
            )
    return result


_HANDLERS = {
    (DESTINATION_PRODUCTION_HISTORY, LEVEL_HISTORY_LIST): _transfer_history_list,
    (DESTINATION_PRODUCTION_HISTORY, LEVEL_HISTORY_DAILY): _transfer_history_daily,
    (DESTINATION_PRODUCT_DATA, LEVEL_PRODUCT_INFO): _transfer_product_info,
    (DESTINATION_PRODUCT_DATA, LEVEL_PRODUCT_BOM): _transfer_product_bom,
    (DESTINATION_PRODUCT_DATA, LEVEL_PRODUCT_CONSUMABLES): _transfer_product_consumables,
    (DESTINATION_INVENTORY_ORDERS, LEVEL_IO_ORDERS): _transfer_io_orders,
    (DESTINATION_INVENTORY_ORDERS, LEVEL_IO_STOCK): _transfer_io_stock,
    (DESTINATION_INVENTORY_ORDERS, LEVEL_IO_BOM): _transfer_product_bom,
    (DESTINATION_INVENTORY_ORDERS, LEVEL_IO_FORECAST): _transfer_io_forecast,
}


def transfer_excel_table(
    *,
    table: ExcelTable,
    destination_id: str,
    mapping: dict[str, Any],
    user,
    level_id: str = LEVEL_HISTORY_LIST,
    mode: str = MODE_TRANSFER,
    offset: int = 0,
    limit: int | None = None,
) -> TransferResult:
    """Transfer or update table rows into destination. Does NOT delete the Excel table.

    mode=transfer: create missing records and update existing ones.
    mode=update: only patch existing records; never insert new ones.
    Optional offset/limit enable chunked transfer with progress percent.
    """
    if mode not in (MODE_TRANSFER, MODE_UPDATE):
        raise ValueError("حالت عملیات نامعتبر است (انتقال یا بروزرسانی).")

    destinations = {d["id"]: d for d in list_destinations_for_ui()}
    if destination_id not in destinations:
        raise ValueError("مقصد انتقال نامعتبر است یا پنهان شده است.")

    dest = destinations[destination_id]
    levels = {lv["id"]: lv for lv in dest.get("levels") or []}
    if not level_id:
        level_id = next(iter(levels), LEVEL_HISTORY_LIST)
    if level_id not in levels:
        raise ValueError("سطح انتقال نامعتبر است یا پنهان شده است.")

    # Only map onto fields that remain active in the naming registry
    ui_fields = levels[level_id].get("fields") or []
    allowed_keys = {f["key"] for f in ui_fields}
    fields = [f for f in _fields_for(destination_id, level_id) if f.key in allowed_keys]
    # Apply resolved labels onto DestField copies for error messages
    label_by_key = {f["key"]: f["label"] for f in ui_fields}
    fields = [
        DestField(key=f.key, label=label_by_key.get(f.key, f.label), type=f.type, required=f.required)
        for f in fields
    ]
    headers = table.headers if isinstance(table.headers, list) else []
    col_map, map_errors = _normalize_mapping(mapping, fields, len(headers))
    if map_errors:
        raise ValueError(" ".join(map_errors))

    handler = _HANDLERS.get((destination_id, level_id))
    if not handler:
        raise ValueError("هندلر انتقال یافت نشد.")

    kwargs = {"table": table, "col_map": col_map, "user": user, "mode": mode}
    if handler is _transfer_history_list:
        kwargs["offset"] = offset
        kwargs["limit"] = limit
    result = handler(**kwargs)
    result.mode = mode
    if destination_id == DESTINATION_INVENTORY_ORDERS:
        result.redirect_url = reverse("inventory_orders")
        result.destination_id = DESTINATION_INVENTORY_ORDERS
        result.level_id = level_id
    else:
        result.redirect_url = (
            reverse("excel_detail", args=[table.upload_id])
            if table.upload_id
            else reverse("excel_list")
        )
    result.table_deleted = False

    action_label = "بروزرسانی" if mode == MODE_UPDATE else "انتقال"
    if result.failed:
        register_alarm(
            title=f"خلاصه {action_label} جدول «{table.name}»",
            message=(
                f"{action_label} به «{dest['label']} / {levels[level_id]['label']}»: "
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
                "mode": mode,
            },
            dedupe=False,
        )

    return result
